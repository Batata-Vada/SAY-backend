"""SAY profile data only. Neither avatar nor display name comes from Codeforces."""
from __future__ import annotations
import io
import re
import uuid
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from flask import Blueprint, current_app, request, send_from_directory
from database.db import db
from middleware.auth import login_required
from models.user_profile import UserProfile

say_profile=Blueprint('say_profile',__name__)
_FILENAME=re.compile(r'[0-9a-f]{32}\.webp\Z')


def _profile(uid):
    profile=UserProfile.query.filter_by(user_id=uid).first()
    if not profile:
        profile=UserProfile(user_id=uid)
        db.session.add(profile)
    return profile


def _data(p):
    return {'display_name':p.display_name,'bio':p.bio,
            'avatar_url':f'/api/avatars/{p.avatar_filename}' if p.avatar_filename else None}


@say_profile.get('/api/me/say-profile')
@login_required
def get_profile(user):
    p=_profile(user.uid)
    db.session.commit()
    return {'profile':_data(p)},200


@say_profile.patch('/api/me/say-profile')
@login_required
def update_profile(user):
    data=request.get_json(silent=True)
    if not isinstance(data,dict) or not data or not set(data).issubset({'display_name','bio'}):
        return {'message':'Only SAY display_name and bio may be updated here'},400
    changes={}
    for field,maxlen in (('display_name',100),('bio',2000)):
        if field in data:
            if data[field] is not None and not isinstance(data[field],str):
                return {'message':field+' must be a string or null'},400
            val=(data[field] or '').strip()
            if len(val)>maxlen:
                return {'message':f'{field} is too long'},400
            changes[field]=val or None
    p=_profile(user.uid)
    for field,value in changes.items():setattr(p,field,value)
    db.session.commit()
    return {'profile':_data(p)},200


def _avatar_dir():
    return Path(current_app.instance_path)/'uploads'/'avatars'


@say_profile.post('/api/me/avatar')
@login_required
def upload_avatar(user):
    upload=request.files.get('file')
    if not upload:
        return {'message':'Upload a multipart file named file'},400
    raw=upload.read(2*1024*1024+1)
    if len(raw)>2*1024*1024:
        return {'message':'Avatar exceeds 2 MB'},413
    try:
        Image.MAX_IMAGE_PIXELS=8_000_000
        with Image.open(io.BytesIO(raw)) as img:
            img.verify()
        with Image.open(io.BytesIO(raw)) as img:
            if img.format not in {'PNG','JPEG','WEBP'}:
                return {'message':'Allowed avatar formats: PNG, JPEG, WEBP'},400
            img=img.convert('RGB')
            img.thumbnail((512,512))
            buf=io.BytesIO()
            img.save(buf,format='WEBP',quality=83,method=4)
    except (UnidentifiedImageError,ValueError,OSError,Image.DecompressionBombError):
        return {'message':'Invalid avatar image'},400
    directory=_avatar_dir()
    directory.mkdir(parents=True,exist_ok=True)
    name=uuid.uuid4().hex+'.webp'
    path=directory/name
    path.write_bytes(buf.getvalue())
    p=_profile(user.uid)
    prior=p.avatar_filename
    p.avatar_filename=name
    try:db.session.commit()
    except Exception:
        db.session.rollback()
        path.unlink(missing_ok=True)
        raise
    if prior and _FILENAME.fullmatch(prior):
        (directory/prior).unlink(missing_ok=True)
    return {'avatar_url':_data(p)['avatar_url']},201


@say_profile.get('/api/avatars/<string:filename>')
def avatar(filename):
    if not _FILENAME.fullmatch(filename):
        return {'message':'Not found'},404
    return send_from_directory(_avatar_dir(),filename,mimetype='image/webp',max_age=3600)
