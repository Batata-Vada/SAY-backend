"""Checks main/config patches do not introduce duplicated blueprints."""
import subprocess,sys
from pathlib import Path

def test_patcher_idempotence(tmp_path):
    root=Path(__file__).resolve().parents[1]
    (tmp_path/'patches').mkdir()
    (tmp_path/'patches'/'apply_oidc_forum.py').write_text((root/'patches'/'apply_oidc_forum.py').read_text())
    (tmp_path/'user_profile').mkdir()
    (tmp_path/'user_profile'/'routes.py').write_text('def serialize_profile(user_profile):\n    return {\n        "id": user_profile.id,\n    }\n\ndef get_public_profile(username):\n    response={\n        "name": user.name,\n    }\n')
    (tmp_path/'main.py').write_text('''from auth.routes import auth
from user_education.routes import education
from models.user_education import UserEducation
from analytics.mastery import rebuild_user_skills, SkillEstimateError

def create_app():
    CORS(app, supports_credentials=False)
    app.register_blueprint(education, url_prefix="/education")
    return app
''')
    (tmp_path/'config.py').write_text('import os\nfrom confighelper import env_bool\nclass Config:\n    DEBUG = False\n')
    for _ in range(2):
        subprocess.run([sys.executable,str(tmp_path/'patches'/'apply_oidc_forum.py')],check=True)
    text=(tmp_path/'main.py').read_text()
    assert text.count('    app.register_blueprint(cf_oidc)')==1
    assert text.count('    app.register_blueprint(forum)')==1
    assert text.count('    app.register_blueprint(say_profile)')==1
    assert text.count('def adopt_legacy_oidc(')==1
    assert text.count('supports_credentials=True')==1
    assert 'X-SAY-CSRF' in text or 'allow_headers=' not in text
    assert (tmp_path/'config.py').read_text().count('CODEFORCES_OIDC_CLIENT_ID = ')==1
