"""SAY problem discussions: user-scoped authors, replies, votes and soft deletion."""
from __future__ import annotations
from datetime import datetime,timezone,timedelta
from flask import Blueprint,request
from sqlalchemy import func
from database.db import db
from middleware.auth import login_required
from models.users import User
from models.user_profile import UserProfile
from models.problem import Problem
from models.forum import ForumThread,ForumReply,ForumVote
from models.codeforces_account import CodeforcesAccount
from models.user_problem_progress import UserProblemProgress

forum=Blueprint('forum',__name__)


def _pagination():
    try:
        limit=int(request.args.get('limit','20'))
        offset=int(request.args.get('offset','0'))
    except (TypeError,ValueError):return None
    return (limit,offset) if 1<=limit<=50 and 0<=offset<=1000000 else None


def _text(data,name,minlen,maxlen):
    val=data.get(name)
    if not isinstance(val,str) or not minlen<=len(val.strip())<=maxlen:
        raise ValueError(f'{name} must be {minlen}..{maxlen} characters')
    return val.strip()


def _author(uid):
    user=db.session.get(User,uid)
    p=UserProfile.query.filter_by(user_id=uid).first()
    return {'uid':uid,'username':user.name if user else 'deleted_user',
            'display_name':p.display_name if p and p.display_name else (user.name if user else 'deleted_user'),
            'avatar_url':f'/api/avatars/{p.avatar_filename}' if p and p.avatar_filename else None}


def _solved(uid,problem_id):
    acct=CodeforcesAccount.query.filter_by(uid=uid,unlinked_at=None).first()
    if not acct:return False
    p=UserProblemProgress.query.filter_by(uid=uid,source_account_id=acct.id,problem_id=problem_id).first()
    return bool(p and p.is_solved)


def _reveal(uid,problem_id,author_uid):
    return request.args.get('reveal_spoilers','false').lower()=='true' or uid==author_uid or _solved(uid,problem_id)


def _thread_data(t,uid):
    visible=not t.spoiler or _reveal(uid,t.problem_id,t.author_uid)
    votes=db.session.execute(db.select(func.coalesce(func.sum(ForumVote.value),0)).where(ForumVote.thread_id==t.id)).scalar_one()
    return {'id':t.id,'problem_id':t.problem_id,'title':t.title if visible and not t.is_deleted else '[Hidden or deleted]',
            'body':t.body if visible and not t.is_deleted else None,'spoiler':t.spoiler,
            'hidden_spoiler':t.spoiler and not visible,'is_deleted':t.is_deleted,'is_locked':t.is_locked,
            'score':int(votes),'author':_author(t.author_uid),'created_at':t.created_at.isoformat(),
            'updated_at':t.updated_at.isoformat()}


def _reply_data(r,t,uid):
    visible=not r.spoiler or _reveal(uid,t.problem_id,r.author_uid)
    return {'id':r.id,'thread_id':r.thread_id,'parent_id':r.parent_id,
            'body':r.body if visible and not r.is_deleted else None,
            'spoiler':r.spoiler,'hidden_spoiler':r.spoiler and not visible,
            'is_deleted':r.is_deleted,'author':_author(r.author_uid),
            'created_at':r.created_at.isoformat(),'updated_at':r.updated_at.isoformat()}


def _rate_limited(model,uid,cap):
    now=datetime.now(timezone.utc)-timedelta(minutes=1)
    return db.session.execute(db.select(func.count()).select_from(model).where(model.author_uid==uid,model.created_at>=now)).scalar_one()>=cap


@forum.get('/api/problems/<int:problem_id>/forum/threads')
@login_required
def list_threads(user,problem_id):
    paging=_pagination()
    if not paging:return {'message':'limit must be 1..50; offset must be nonnegative'},400
    p=db.session.get(Problem,problem_id)
    if not p or p.platform!='CODEFORCES':return {'message':'Codeforces problem not found'},404
    query=db.select(ForumThread).where(ForumThread.problem_id==problem_id)
    rows=db.session.execute(query.order_by(ForumThread.created_at.desc(),ForumThread.id.desc()).limit(paging[0]).offset(paging[1])).scalars().all()
    total=db.session.execute(db.select(func.count()).select_from(ForumThread).where(ForumThread.problem_id==problem_id)).scalar_one()
    return {'problem':{'id':p.id,'external_id':p.external_id,'title':p.title},
            'viewer_has_solved':_solved(user.uid,problem_id),'total':total,
            'threads':[_thread_data(t,user.uid) for t in rows]},200


@forum.post('/api/problems/<int:problem_id>/forum/threads')
@login_required
def create_thread(user,problem_id):
    p=db.session.get(Problem,problem_id)
    if not p or p.platform!='CODEFORCES':return {'message':'Codeforces problem not found'},404
    data=request.get_json(silent=True)
    if not isinstance(data,dict):return {'message':'JSON object required'},400
    try:
        title=_text(data,'title',3,160)
        body=_text(data,'body',1,10000)
    except ValueError as exc:return {'message':str(exc)},400
    if type(data.get('spoiler',False)) is not bool:return {'message':'spoiler must be boolean'},400
    if _rate_limited(ForumThread,user.uid,5):return {'message':'Too many new threads; retry later'},429
    t=ForumThread(problem_id=problem_id,author_uid=user.uid,title=title,body=body,spoiler=data.get('spoiler',False))
    db.session.add(t);db.session.commit()
    return {'thread':_thread_data(t,user.uid)},201


@forum.get('/api/forum/threads/<int:thread_id>')
@login_required
def get_thread(user,thread_id):
    t=db.session.get(ForumThread,thread_id)
    return ({'thread':_thread_data(t,user.uid)},200) if t else ({'message':'Thread not found'},404)


@forum.patch('/api/forum/threads/<int:thread_id>')
@login_required
def edit_thread(user,thread_id):
    t=db.session.get(ForumThread,thread_id)
    if not t or t.is_deleted:return {'message':'Thread not found'},404
    if t.author_uid!=user.uid and user.privilege!='admin':return {'message':'Not your thread'},403
    data=request.get_json(silent=True)
    if not isinstance(data,dict) or not data or not set(data).issubset({'title','body','spoiler','is_locked'}):
        return {'message':'Invalid changes'},400
    try:
        for field,minlen,maxlen in [('title',3,160),('body',1,10000)]:
            if field in data:setattr(t,field,_text(data,field,minlen,maxlen))
    except ValueError as exc:return {'message':str(exc)},400
    if 'spoiler' in data:
        if type(data['spoiler']) is not bool:return {'message':'spoiler must be boolean'},400
        t.spoiler=data['spoiler']
    if 'is_locked' in data:
        if user.privilege!='admin':return {'message':'Moderator access required'},403
        if type(data['is_locked']) is not bool:return {'message':'is_locked must be boolean'},400
        t.is_locked=data['is_locked']
    db.session.commit()
    return {'thread':_thread_data(t,user.uid)},200


@forum.delete('/api/forum/threads/<int:thread_id>')
@login_required
def delete_thread(user,thread_id):
    t=db.session.get(ForumThread,thread_id)
    if not t:return {'message':'Thread not found'},404
    if t.author_uid!=user.uid and user.privilege!='admin':return {'message':'Not your thread'},403
    t.is_deleted=True;t.body='';db.session.commit()
    return {'message':'Thread removed'},200


@forum.get('/api/forum/threads/<int:thread_id>/replies')
@login_required
def list_replies(user,thread_id):
    t=db.session.get(ForumThread,thread_id)
    if not t:return {'message':'Thread not found'},404
    paging=_pagination()
    if not paging:return {'message':'Invalid pagination'},400
    rows=db.session.execute(db.select(ForumReply).where(ForumReply.thread_id==t.id).order_by(ForumReply.created_at,ForumReply.id).limit(paging[0]).offset(paging[1])).scalars().all()
    total=db.session.execute(db.select(func.count()).select_from(ForumReply).where(ForumReply.thread_id==t.id)).scalar_one()
    return {'thread_id':t.id,'total':total,'replies':[_reply_data(r,t,user.uid) for r in rows]},200


@forum.post('/api/forum/threads/<int:thread_id>/replies')
@login_required
def create_reply(user,thread_id):
    t=db.session.get(ForumThread,thread_id)
    if not t or t.is_deleted:return {'message':'Thread not found'},404
    if t.is_locked:return {'message':'Thread is locked'},409
    data=request.get_json(silent=True)
    if not isinstance(data,dict):return {'message':'JSON object required'},400
    try:body=_text(data,'body',1,10000)
    except ValueError as exc:return {'message':str(exc)},400
    if type(data.get('spoiler',False)) is not bool:return {'message':'spoiler must be boolean'},400
    parent=data.get('parent_id')
    if parent is not None:
        if type(parent) is not int:return {'message':'parent_id must be an integer'},400
        parent_row=db.session.get(ForumReply,parent)
        if not parent_row or parent_row.thread_id!=t.id:return {'message':'Parent reply is not in this thread'},400
    if _rate_limited(ForumReply,user.uid,15):return {'message':'Too many replies; retry later'},429
    r=ForumReply(thread_id=t.id,parent_id=parent,author_uid=user.uid,body=body,spoiler=data.get('spoiler',False))
    db.session.add(r);db.session.commit()
    return {'reply':_reply_data(r,t,user.uid)},201


@forum.patch('/api/forum/replies/<int:reply_id>')
@login_required
def edit_reply(user,reply_id):
    r=db.session.get(ForumReply,reply_id)
    if not r or r.is_deleted:return {'message':'Reply not found'},404
    if r.author_uid!=user.uid and user.privilege!='admin':return {'message':'Not your reply'},403
    t=db.session.get(ForumThread,r.thread_id)
    data=request.get_json(silent=True)
    if not isinstance(data,dict) or not data or not set(data).issubset({'body','spoiler'}):return {'message':'Invalid changes'},400
    if 'body' in data:
        try:r.body=_text(data,'body',1,10000)
        except ValueError as exc:return {'message':str(exc)},400
    if 'spoiler' in data:
        if type(data['spoiler']) is not bool:return {'message':'spoiler must be boolean'},400
        r.spoiler=data['spoiler']
    db.session.commit()
    return {'reply':_reply_data(r,t,user.uid)},200


@forum.delete('/api/forum/replies/<int:reply_id>')
@login_required
def delete_reply(user,reply_id):
    r=db.session.get(ForumReply,reply_id)
    if not r:return {'message':'Reply not found'},404
    if r.author_uid!=user.uid and user.privilege!='admin':return {'message':'Not your reply'},403
    r.is_deleted=True;r.body='';db.session.commit()
    return {'message':'Reply removed'},200


@forum.put('/api/forum/threads/<int:thread_id>/vote')
@login_required
def vote_thread(user,thread_id):
    t=db.session.get(ForumThread,thread_id)
    if not t or t.is_deleted:return {'message':'Thread not found'},404
    data=request.get_json(silent=True)
    value=data.get('value') if isinstance(data,dict) else None
    if type(value) is not int or value not in (-1,0,1):return {'message':'value must be -1, 0 or 1'},400
    row=db.session.get(ForumVote,(user.uid,thread_id))
    if value==0:
        if row:db.session.delete(row)
    elif row:row.value=value
    else:db.session.add(ForumVote(uid=user.uid,thread_id=thread_id,value=value))
    db.session.commit()
    return {'thread':_thread_data(t,user.uid)},200


@forum.get('/api/problems/codeforces/<int:contest_id>/<string:index>')
@login_required
def resolve_codeforces_problem(user,contest_id,index):
    """Resolve stable external Codeforces identity to SAY's canonical problem ID."""
    if contest_id<1 or not index.isalnum() or len(index)>20:
        return {'message':'Invalid Codeforces problem identity'},400
    problem=Problem.query.filter_by(platform='CODEFORCES',external_id=f'{contest_id}:{index}').first()
    if not problem:return {'message':'Problem not in SAY catalog; sync the Codeforces problem catalog'},404
    return {'problem_id':problem.id,'external_id':problem.external_id,'title':problem.title,
            'url':problem.url,'rating':problem.codeforces_rating,
            'forum_url':f'/api/problems/{problem.id}/forum/threads'},200
