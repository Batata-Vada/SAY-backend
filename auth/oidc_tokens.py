"""Verify Codeforces ID tokens. Discovery advertises HS256 and client_secret_post.

Never substitute public user.info or a handle for a cryptographically proven OIDC subject.
"""
from __future__ import annotations
import jwt

ISSUER = 'https://codeforces.com'


class IdentityTokenError(ValueError):
    pass


def verify_codeforces_id_token(id_token: str, client_id: str, client_secret: str, nonce: str) -> dict:
    if not isinstance(id_token, str) or not id_token:
        raise IdentityTokenError('Missing ID token')
    try:
        claims = jwt.decode(
            id_token, client_secret, algorithms=['HS256'], audience=client_id,
            issuer=ISSUER, leeway=30, options={'require': ['iss','sub','aud','exp','iat']},
        )
    except jwt.PyJWTError as exc:
        raise IdentityTokenError('Invalid Codeforces ID token') from exc
    subject = claims.get('sub')
    handle = claims.get('handle')
    if not isinstance(subject, str) or not (1 <= len(subject) <= 255):
        raise IdentityTokenError('Invalid subject in ID token')
    if not isinstance(handle, str) or not (1 <= len(handle) <= 64):
        raise IdentityTokenError('Invalid handle in ID token')
    # Nonce is not included among Codeforces's advertised supported claims.
    # Validate it if issued, while state+one-use server-side code exchange protect the flow.
    returned_nonce = claims.get('nonce')
    if returned_nonce is not None and returned_nonce != nonce:
        raise IdentityTokenError('OIDC nonce mismatch')
    rating = claims.get('rating')
    if type(rating) is not int or rating < 0 or rating > 5000:
        rating = None
    return {'issuer':ISSUER,'subject':subject,'handle':handle,'contest_rating':rating}
