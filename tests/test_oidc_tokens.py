"""Pure security regression tests; no Flask dependencies."""
import importlib.util
from pathlib import Path
import time
import pytest
import jwt

path=Path(__file__).resolve().parents[1]/'auth'/'oidc_tokens.py'
spec=importlib.util.spec_from_file_location('oidc_tokens_to_test',path)
tokens=importlib.util.module_from_spec(spec)
spec.loader.exec_module(tokens)
SECRET='test-client-secret-'.ljust(48,'z')


def signed(**changes):
    now=int(time.time())
    fields={'iss':tokens.ISSUER,'aud':'client123','sub':'stable-123',
            'iat':now,'exp':now+300,'handle':'macyapp','rating':1452}
    fields.update(changes)
    return jwt.encode(fields,SECRET,algorithm='HS256')


def test_verified_identity_and_rating():
    assert tokens.verify_codeforces_id_token(signed(),'client123',SECRET,'abc')=={
        'issuer':'https://codeforces.com','subject':'stable-123','handle':'macyapp','contest_rating':1452}


def test_wrong_secret_rejected():
    with pytest.raises(tokens.IdentityTokenError):
        tokens.verify_codeforces_id_token(signed(),'client123','another-secret'.ljust(48,'x'),'abc')


def test_wrong_audience_rejected():
    with pytest.raises(tokens.IdentityTokenError):
        tokens.verify_codeforces_id_token(signed(),'some-other-client',SECRET,'abc')


def test_wrong_issuer_rejected():
    with pytest.raises(tokens.IdentityTokenError):
        tokens.verify_codeforces_id_token(signed(iss='https://attacker.example'),'client123',SECRET,'abc')


def test_expired_token_rejected():
    now=int(time.time())
    with pytest.raises(tokens.IdentityTokenError):
        tokens.verify_codeforces_id_token(signed(iat=now-900,exp=now-800),'client123',SECRET,'abc')


def test_nonce_checked_when_present():
    with pytest.raises(tokens.IdentityTokenError):
        tokens.verify_codeforces_id_token(signed(nonce='wrong'),'client123',SECRET,'abc')


def test_optional_rating_never_used_for_identity():
    data=tokens.verify_codeforces_id_token(signed(rating=None),'client123',SECRET,'abc')
    assert data['contest_rating'] is None and data['subject']=='stable-123'
