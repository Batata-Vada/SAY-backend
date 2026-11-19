"""Run in SAY .venv. Uses temporary in-memory SQLite and mocked Codeforces token endpoint.

IMPORTANT: db.create_all() is for isolated tests only, NEVER production migrations.
"""
import os
os.environ.setdefault('SECRET_KEY','this-is-a-test-only-secret-not-for-production-xzy')
os.environ.setdefault('CODEFORCES_OIDC_CLIENT_ID','test-client')
os.environ.setdefault('CODEFORCES_OIDC_CLIENT_SECRET','test-client-secret-long-enough-for-hs256-security')
os.environ.setdefault('CODEFORCES_OIDC_REDIRECT_URI','http://localhost:5001/auth/codeforces/callback')
os.environ.setdefault('SAY_FRONTEND_URL','http://localhost:3000')
from urllib.parse import parse_qs,urlsplit
from datetime import datetime,timezone,timedelta
import hashlib
import time
import pytest
import jwt
pytest.importorskip('flask_sqlalchemy')
from database.db import db
from main import create_app
from models.codeforces_oidc_identity import OidcLoginState,CodeforcesOidcIdentity
from models.codeforces_account import CodeforcesAccount
from models.problem import Problem
from models.session import Session

@pytest.fixture
def app(tmp_path):
    a=create_app({'TESTING':True,'SECRET_KEY':'this-is-a-test-only-secret-not-for-production-xzy',
       'SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(tmp_path/'app.db'),
       'CODEFORCES_OIDC_CLIENT_ID':'test-client',
       'CODEFORCES_OIDC_CLIENT_SECRET':'test-client-secret-long-enough-for-hs256-security',
       'CODEFORCES_OIDC_REDIRECT_URI':'http://localhost:5001/auth/codeforces/callback',
       'SAY_FRONTEND_URL':'http://localhost:3000',
       'SAY_COOKIE_SECURE':False,'CORS_ORIGINS':['http://localhost:3000']})
    a.instance_path=str(tmp_path/'instance')
    with a.app_context():
        db.create_all()
        db.session.add(Problem(id=42,platform='CODEFORCES',external_id='1900:A',
         title='Sample Codeforces Problem',url='https://codeforces.com/problemset/problem/1900/A',
         contest_id='1900',problem_index='A',tags_raw=['greedy'],stats_raw={},metadata_raw={}))
        db.session.commit()
    yield a
    with a.app_context():
        db.session.remove()
        db.drop_all()


class FakeResponse:
    def __init__(self,token):self.token=token
    def raise_for_status(self):pass
    def json(self):return {'id_token':self.token,'access_token':'unused'}


def login_as(app,client,monkeypatch,sub,handle,rating=1410):
    r=client.get('/auth/codeforces/login')
    assert r.status_code==302
    args=parse_qs(urlsplit(r.headers['Location']).query)
    state=args['state'][0]
    with app.app_context():
        rec=db.session.get(OidcLoginState,hashlib.sha256(state.encode()).hexdigest())
        nonce=rec.nonce
    now=int(time.time())
    jwt_token=jwt.encode({'iss':'https://codeforces.com','sub':sub,'aud':'test-client',
          'iat':now,'exp':now+300,'handle':handle,'rating':rating,'nonce':nonce},
          'test-client-secret-long-enough-for-hs256-security',algorithm='HS256')
    monkeypatch.setattr('auth.oidc.requests.post',lambda *args,**kwargs:FakeResponse(jwt_token))
    callback=client.get('/auth/codeforces/callback',query_string={'code':'test','state':state})
    assert callback.status_code==302
    return state


def test_only_oidc_can_authenticate(app,monkeypatch):
    client=app.test_client()
    assert client.post('/login',json={'name':'x','password':'secret'}).status_code==410
    assert client.get('/auth/session').status_code==401
    state=login_as(app,client,monkeypatch,'stable-person','handle_one',1666)
    assert client.get('/auth/session').json['codeforces']['rating']==1666
    assert client.get('/auth/codeforces/callback',query_string={'code':'replay','state':state}).status_code==400
    assert client.get('/api/me/codeforces-rating').json['handle']=='handle_one'
    with app.app_context():
        assert CodeforcesOidcIdentity.query.count()==1
        assert CodeforcesAccount.query.count()==1
        assert CodeforcesAccount.query.first().ownership_verified
        assert Session.query.first().auth_provider=='CODEFORCES_OIDC'
    csrf=client.get('/auth/csrf').json['csrf_token']
    assert client.post('/api/codeforces/account',json={'handle':'attacker'}).status_code==403
    assert client.post('/api/codeforces/account',json={'handle':'attacker'},headers={'X-SAY-CSRF':csrf}).status_code==410


def test_forum_problem_identity_authorship_and_spoilers(app,monkeypatch):
    a=app.test_client()
    login_as(app,a,monkeypatch,'subject-a','handle_a')
    csrf_a=a.get('/auth/csrf').json['csrf_token']
    assert a.post('/api/problems/42/forum/threads',json={'title':'Please help','body':'Idea'}).status_code==403
    made=a.post('/api/problems/42/forum/threads',headers={'X-SAY-CSRF':csrf_a},
       json={'title':'Please help','body':'Sort then iterate','spoiler':True})
    assert made.status_code==201
    tid=made.json['thread']['id']
    assert made.json['thread']['author']['avatar_url'] is None
    assert made.json['thread']['body']=='Sort then iterate'
    b=app.test_client()
    login_as(app,b,monkeypatch,'subject-b','handle_b')
    read=b.get('/api/forum/threads/'+str(tid))
    assert read.json['thread']['body'] is None
    assert read.json['thread']['hidden_spoiler'] is True
    assert b.get('/api/forum/threads/'+str(tid)+'?reveal_spoilers=true').json['thread']['body']=='Sort then iterate'
    csrf_b=b.get('/auth/csrf').json['csrf_token']
    assert b.patch('/api/forum/threads/'+str(tid),headers={'X-SAY-CSRF':csrf_b},json={'title':'Hijack'}).status_code==403
    reply=b.post(f'/api/forum/threads/{tid}/replies',headers={'X-SAY-CSRF':csrf_b},json={'body':'Think greedy.'})
    assert reply.status_code==201
    vote=b.put(f'/api/forum/threads/{tid}/vote',headers={'X-SAY-CSRF':csrf_b},json={'value':1})
    assert vote.json['thread']['score']==1
    assert b.get('/api/problems/42/forum/threads').json['total']==1
    assert b.get('/api/me/say-profile').status_code==200


def test_verified_subject_not_handle_is_identity(app,monkeypatch):
    client=app.test_client()
    login_as(app,client,monkeypatch,'stable-sub','handle_old')
    uid=client.get('/auth/session').json['uid']
    login_as(app,client,monkeypatch,'stable-sub','handle_new')
    assert client.get('/auth/session').json['uid']==uid
    assert client.get('/api/codeforces/account').json['account']['handle']=='handle_new'
    with app.app_context():
        assert CodeforcesOidcIdentity.query.count()==1
        assert CodeforcesAccount.query.count()==1


def test_logout_revokes_cookie_session(app,monkeypatch):
    client=app.test_client()
    login_as(app,client,monkeypatch,'logged-in','handles')
    csrf=client.get('/auth/csrf').json['csrf_token']
    assert client.post('/auth/logout',headers={'X-SAY-CSRF':csrf}).status_code==200
    assert client.get('/auth/session').status_code==401
