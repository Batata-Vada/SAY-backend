"""Codeforces OIDC browser flow; the only way to mint new SAY login sessions.

GET /auth/codeforces/login -> codeforces.com/oauth/authorize
GET /auth/codeforces/callback -> one-use code exchange, validated ID token,
                                 HttpOnly SAY session cookie, frontend redirect
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
import hashlib
import secrets
from urllib.parse import urlencode
import requests
from flask import Blueprint, current_app, make_response, redirect, request
from sqlalchemy.exc import IntegrityError
from database.db import db
from auth.oidc_tokens import verify_codeforces_id_token, IdentityTokenError, ISSUER
from middleware.auth import issue_session_token, token_digest, login_required, _session_from_request, csrf_for_token
from models.codeforces_oidc_identity import CodeforcesOidcIdentity, OidcLoginState
from models.codeforces_account import CodeforcesAccount
from models.session import Session
from models.users import User
from codeforces.client import CodeforcesClient, CodeforcesUnavailable, CodeforcesUserNotFound

cf_oidc = Blueprint('cf_oidc', __name__)


def _cfg():
    client_id = current_app.config.get('CODEFORCES_OIDC_CLIENT_ID','')
    secret = current_app.config.get('CODEFORCES_OIDC_CLIENT_SECRET','')
    redirect_uri = current_app.config.get('CODEFORCES_OIDC_REDIRECT_URI','')
    frontend = current_app.config.get('SAY_FRONTEND_URL','').rstrip('/')
    if not (client_id and secret and redirect_uri and frontend):
        raise RuntimeError('Configure Codeforces OIDC app, callback and frontend URL')
    is_dev = redirect_uri.startswith('http://localhost:') or redirect_uri.startswith('http://127.0.0.1:')
    if not redirect_uri.startswith('https://') and not is_dev:
        raise RuntimeError('OIDC callback requires HTTPS outside localhost')
    if not is_dev and not current_app.config.get('SAY_COOKIE_SECURE',False):
        raise RuntimeError('SAY_COOKIE_SECURE=true is required outside localhost')
    return client_id,secret,redirect_uri,frontend


def _digest(s):
    return hashlib.sha256(s.encode('ascii')).hexdigest()


def _cookie_options():
    return dict(httponly=True,secure=bool(current_app.config.get('SAY_COOKIE_SECURE',False)),samesite='Lax',path='/')


def _log_oidc_cookie(event, max_age, cookie_set):
    options=_cookie_options()
    current_app.logger.info(
        'Codeforces OIDC %s host=%s cookie_name=say_oidc_state '
        'set=%s httponly=%s secure=%s samesite=%s path=%s domain=%s max_age=%s',
        event,request.host,cookie_set,options['httponly'],options['secure'],options['samesite'],
        options['path'],None,max_age)


@cf_oidc.get('/auth/codeforces/login')
def codeforces_login():
    client_id,_,callback,_ = _cfg()
    state=secrets.token_urlsafe(32)
    nonce=secrets.token_urlsafe(32)
    current_app.logger.info('Codeforces OIDC login state generated')
    now=datetime.now(timezone.utc)
    # Expire/reject browser login attempts; state is never accepted from JSON input.
    # Bound the state table: consumed or expired requests can be discarded.
    db.session.execute(db.delete(OidcLoginState).where(OidcLoginState.expires_at < now))
    db.session.add(OidcLoginState(state_digest=_digest(state),nonce=nonce,expires_at=now+timedelta(minutes=10)))
    db.session.commit()
    current_app.logger.info('Codeforces OIDC login state record committed')
    params={'client_id':client_id,'redirect_uri':callback,'response_type':'code',
            'scope':'openid','state':state,'nonce':nonce}
    resp=redirect('https://codeforces.com/oauth/authorize?'+urlencode(params),code=302)
    resp.set_cookie('say_oidc_state',state,max_age=600,**_cookie_options())
    cookie_set=any(value.startswith('say_oidc_state=') for value in resp.headers.getlist('Set-Cookie'))
    _log_oidc_cookie('login response cookie',600,cookie_set)
    resp.headers['Cache-Control']='no-store'
    return resp


def _new_name(subject):
    # No Codeforces handle is automatically made into a SAY profile identifier.
    base='say_'+hashlib.sha256(subject.encode()).hexdigest()[:16]
    if User.query.filter_by(name=base).first() is None:
        return base
    for _ in range(5):
        value='say_'+secrets.token_hex(12)
        if User.query.filter_by(name=value).first() is None:
            return value
    raise RuntimeError('Could not assign SAY username')


def _upsert_verified_identity(identity):
    """Only called after cryptographic token verification. Never merge by handle."""
    now=datetime.now(timezone.utc)
    row=CodeforcesOidcIdentity.query.filter_by(issuer=identity['issuer'],subject=identity['subject']).first()
    if row is None:
        user=User(name=_new_name(identity['subject']),email=None,password=None,privilege='user')
        db.session.add(user)
        db.session.flush()
        row=CodeforcesOidcIdentity(uid=user.uid,issuer=identity['issuer'],subject=identity['subject'],
                                    handle=identity['handle'],created_at=now,last_login_at=now)
        db.session.add(row)
    else:
        user=db.session.get(User,row.uid)
        if user is None:
            raise RuntimeError('Identity points to deleted SAY account')
    row.handle=identity['handle']
    row.contest_rating=identity['contest_rating']
    row.rating_updated_at=now
    row.last_login_at=now
    active=CodeforcesAccount.query.filter_by(uid=user.uid,unlinked_at=None).first()
    if active is None:
        active=CodeforcesAccount(uid=user.uid,handle=identity['handle'],ownership_verified=True,
                                  linked_at=now,unlinked_at=None,last_synced_at=None,sync_status='PENDING',
                                  registration_time_seconds=None)
        db.session.add(active)
    else:
        if active.handle!=identity['handle']:
            # Keep account ID and history, but require a fresh import for changed handle.
            active.handle=identity['handle']
            active.last_synced_at=None
            active.sync_status='PENDING'
        active.ownership_verified=True
    return user


@cf_oidc.get('/auth/codeforces/callback')
def codeforces_callback():
    try:
        client_id, client_secret, callback, frontend=_cfg()
    except RuntimeError:
        return {'message':'OIDC is not configured'},503
    supplied_state=request.args.get('state','')
    cookie_state=request.cookies.get('say_oidc_state','')
    state_present=bool(supplied_state)
    cookie_present=bool(cookie_state)
    state_matches=bool(state_present and cookie_present and secrets.compare_digest(supplied_state,cookie_state))
    current_app.logger.info(
        'Codeforces OIDC callback state query_present=%s cookie_present=%s values_match=%s host=%s',
        state_present,cookie_present,state_matches,request.host)
    if not state_present or not cookie_present or not state_matches:
        return {'message':'OIDC state mismatch; restart login'},400
    if not request.args.get('code') or request.args.get('error'):
        return {'message':'Codeforces authentication was cancelled or denied'},400
    attempt=db.session.get(OidcLoginState,_digest(supplied_state))
    now=datetime.now(timezone.utc)
    expired=bool(attempt and (attempt.expires_at.replace(tzinfo=timezone.utc) if attempt.expires_at.tzinfo is None else attempt.expires_at) < now)
    current_app.logger.info(
        'Codeforces OIDC callback database attempt found=%s used=%s expired=%s',
        bool(attempt),bool(attempt and attempt.used_at is not None),expired)
    if not attempt or attempt.used_at is not None or expired:
        return {'message':'OIDC login attempt expired or already used'},400
    # Commit consumption *before* external calls so callbacks cannot be replayed.
    nonce=attempt.nonce
    attempt.used_at=now
    db.session.commit()
    try:
        response=requests.post('https://codeforces.com/oauth/token',data={
            'grant_type':'authorization_code','code':request.args['code'],
            'redirect_uri':callback,'client_id':client_id,'client_secret':client_secret,
        },timeout=15,headers={'Accept':'application/json'})
        response.raise_for_status()
        payload=response.json()
        if not isinstance(payload,dict):
            raise ValueError('Codeforces returned a non-object token response')
        verified=verify_codeforces_id_token(payload.get('id_token'),client_id,client_secret,nonce)
    except (requests.RequestException,ValueError,KeyError,IdentityTokenError):
        current_app.logger.warning('Codeforces OIDC code exchange or token validation failed')
        return {'message':'Codeforces authentication failed; restart login'},401
    try:
        user=_upsert_verified_identity(verified)
        # Existing password-created sessions are not valid OIDC sessions.
        token=issue_session_token(user.uid)
        db.session.add(Session(uid=user.uid,token=token_digest(token),auth_provider='CODEFORCES_OIDC'))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        current_app.logger.exception('Identity conflict; manual reconciliation needed')
        return {'message':'Account identity conflict; contact SAY administrator'},409
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Could not create Codeforces OIDC SAY session')
        return {'message':'Unable to finish login'},500
    resp=redirect(frontend+'/settings?login=success',302)
    resp.set_cookie(current_app.config.get('SAY_SESSION_COOKIE','say_session'),token,
                    max_age=int(current_app.config['SESSION_MAX_AGE_SECONDS']),**_cookie_options())
    resp.delete_cookie('say_oidc_state',path='/')
    resp.headers['Cache-Control']='no-store'
    return resp


@cf_oidc.get('/auth/session')
@login_required
def session_info(user):
    identity=CodeforcesOidcIdentity.query.filter_by(uid=user.uid).one()
    return {'authenticated':True,'uid':user.uid,'say_username':user.name,
            'codeforces':identity.public(),'privilege':user.privilege},200


@cf_oidc.get('/auth/csrf')
@login_required
def csrf_info(user):
    _,token,_=_session_from_request()
    resp=make_response({'csrf_token':csrf_for_token(token)},200)
    resp.headers['Cache-Control']='no-store'
    return resp


@cf_oidc.post('/auth/logout')
@cf_oidc.post('/logout')
@login_required
def logout(user):
    _,token,_=_session_from_request()
    existing=Session.query.filter_by(uid=user.uid,token=token_digest(token)).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
    resp=make_response({'message':'Logged out'},200)
    resp.delete_cookie(current_app.config.get('SAY_SESSION_COOKIE','say_session'),path='/')
    resp.headers['Cache-Control']='no-store'
    return resp


@cf_oidc.get('/api/me/codeforces-rating')
@login_required
def contest_rating(user):
    identity=CodeforcesOidcIdentity.query.filter_by(uid=user.uid).one()
    last=identity.rating_updated_at
    if last and last.tzinfo is None:
        last=last.replace(tzinfo=timezone.utc)
    needs_refresh=request.args.get('refresh','false').lower()=='true' and (
        last is None or datetime.now(timezone.utc)-last>timedelta(hours=1))
    if needs_refresh:
        try:
            data=CodeforcesClient().user_info(identity.handle)
        except (CodeforcesUnavailable,CodeforcesUserNotFound):
            return {'message':'Codeforces rating refresh unavailable'},503
        # Handle is only fetched for an OIDC-bound identity, never supplied by caller.
        rating=data.get('rating')
        identity.contest_rating=rating if type(rating) is int and 0 <= rating <= 5000 else None
        identity.rating_updated_at=datetime.now(timezone.utc)
        db.session.commit()
    return identity.public(),200
