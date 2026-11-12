"""Codeforces account linking is allowed only through verified OIDC authentication."""
from flask import Blueprint
from middleware.auth import login_required
from models.codeforces_account import CodeforcesAccount
from models.codeforces_oidc_identity import CodeforcesOidcIdentity

codeforces = Blueprint('codeforces', __name__, url_prefix='/api/codeforces')

@codeforces.get('/account')
@login_required
def get_account(user):
    account = CodeforcesAccount.query.filter_by(uid=user.uid, unlinked_at=None).first()
    identity = CodeforcesOidcIdentity.query.filter_by(uid=user.uid).first()
    if not account or not identity:
        return {'message': 'No verified Codeforces identity'}, 404
    return {'account':account.to_dict(), 'contest_rating':identity.contest_rating}, 200

@codeforces.post('/account')
@login_required
def reject_manual_relink(user):
    return {'message':'Codeforces accounts are linked only through verified OIDC login'}, 410
