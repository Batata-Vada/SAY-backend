"""SAY session security: only sessions created by verified Codeforces OIDC."""
import hashlib
import hmac
import secrets
from functools import wraps
from flask import current_app, request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from database.db import db
from models.session import Session
from models.users import User
from models.codeforces_oidc_identity import CodeforcesOidcIdentity

_SALT = 'say-api-session-v1'
_UNSAFE = {'POST','PUT','PATCH','DELETE'}


def token_digest(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def _serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'],salt=_SALT)


def issue_session_token(uid):
    return _serializer().dumps({'uid':uid,'nonce':secrets.token_urlsafe(24)})


def bearer_token():
    header = request.headers.get('Authorization','').strip()
    if header.lower().startswith('bearer '):
        return header[7:].strip()
    if header and ' ' not in header:
        return header
    return None


def _token_and_source():
    bearer = bearer_token()
    if bearer:
        return bearer,'bearer'
    return request.cookies.get(current_app.config.get('SAY_SESSION_COOKIE','say_session')),'cookie'


def _session_from_request():
    token, source = _token_and_source()
    if not token:
        return None,None,None
    try:
        payload = _serializer().loads(token,max_age=int(current_app.config['SESSION_MAX_AGE_SECONDS']))
    except (BadSignature, TypeError, ValueError):
        return None,None,None
    if not isinstance(payload,dict) or type(payload.get('uid')) is not int:
        return None,None,None
    s = Session.query.filter_by(uid=payload['uid'],token=token_digest(token),auth_provider='CODEFORCES_OIDC').first()
    if not s:
        return None,None,None
    identity = CodeforcesOidcIdentity.query.filter_by(uid=payload['uid']).first()
    if identity is None:
        return None,None,None
    return db.session.get(User,payload['uid']),token,source


def current_user():
    user,_,_ = _session_from_request()
    return user


def csrf_for_token(token):
    digest = token_digest(token)
    secret = current_app.config['SECRET_KEY'].encode('utf8')
    return hmac.new(secret,('say-csrf:'+digest).encode('ascii'),hashlib.sha256).hexdigest()


def _authorized():
    user, token, source = _session_from_request()
    if user is None:
        return None,({'message':'Codeforces login required'},401)
    if source == 'cookie' and request.method in _UNSAFE:
        provided = request.headers.get('X-SAY-CSRF','')
        if not hmac.compare_digest(provided,csrf_for_token(token)):
            return None,({'message':'Missing or invalid X-SAY-CSRF header'},403)
    return user,None


def login_required(fn):
    @wraps(fn)
    def wrapper(*args,**kwargs):
        user,error = _authorized()
        return error if error else fn(user,*args,**kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args,**kwargs):
        user,error = _authorized()
        if error:return error
        if user.privilege!='admin':return {'message':'Admin access required'},403
        return fn(user,*args,**kwargs)
    return wrapper
