"""Compatibility responses: password-based authentication is intentionally disabled."""
from flask import Blueprint

auth = Blueprint('auth',__name__)

@auth.route('/login',methods=['POST'])
@auth.route('/register',methods=['POST'])
@auth.route('/change-password',methods=['PUT'])
def retired_password_auth():
    return {'message':'SAY uses Codeforces OpenID Connect exclusively',
            'login_url':'/auth/codeforces/login'},410

@auth.route('/login',methods=['GET'])
def login_redirect():
    from flask import redirect
    return redirect('/auth/codeforces/login',302)
