"""Idempotent patch to current SAY main.py + config.py. Always inspect git diff.

This patch is intentionally small so Step 9 CLI/blueprints are not overwritten.
"""
from pathlib import Path

root=Path(__file__).resolve().parents[1]
main=root/'main.py'
config=root/'config.py'
source=main.read_text()


def insert_once(src,line,anchor):
    if line in src:return src
    if anchor not in src:raise RuntimeError(f'Cannot find anchor {anchor!r} in main.py; patch manually')
    return src.replace(anchor,anchor+line,1)

source=insert_once(source,'from auth.oidc import cf_oidc\n','from auth.routes import auth\n')
source=insert_once(source,'from forum.routes import forum\nfrom say_profile.routes import say_profile\n','from user_education.routes import education\n')
source=insert_once(source,'from models.codeforces_oidc_identity import CodeforcesOidcIdentity, OidcLoginState\nfrom models.forum import ForumThread, ForumReply, ForumVote\n','from models.user_education import UserEducation\n')
source=insert_once(source,'from scripts.legacy_merge import merge_empty_verified_identity_into_legacy\n','from analytics.mastery import rebuild_user_skills, SkillEstimateError\n')
source=insert_once(source,'    app.register_blueprint(cf_oidc)\n    app.register_blueprint(forum)\n    app.register_blueprint(say_profile)\n','    app.register_blueprint(education, url_prefix="/education")\n')
if 'supports_credentials=False' not in source and 'supports_credentials=True' not in source:
    raise RuntimeError('Cannot find CORS credential setting')
source=source.replace('supports_credentials=False','supports_credentials=True')
# Browser preflight must permit the anti-CSRF request header.
source=source.replace('allow_headers=["Content-Type", "Authorization"]',
                      'allow_headers=["Content-Type", "Authorization", "X-SAY-CSRF"]')
cli='''    @app.cli.command("adopt-legacy-oidc")
    @click.option("--legacy-uid",required=True,type=click.IntRange(min=1))
    @click.option("--verified-uid",required=True,type=click.IntRange(min=1))
    @click.option("--confirm-reviewed-ownership",is_flag=True,required=True)
    def adopt_legacy_oidc(legacy_uid,verified_uid,confirm_reviewed_ownership):
        """ONE-TIME: move a verified identity to a reviewed historical SAY uid."""
        try:
            result=merge_empty_verified_identity_into_legacy(legacy_uid,verified_uid)
        except ValueError as exc:
            db.session.rollback()
            raise click.ClickException(str(exc)) from exc
        click.echo(json.dumps(result,indent=2))

'''
if 'def adopt_legacy_oidc(' not in source:
    if '    return app\n' not in source:raise RuntimeError('Expected return app location not found')
    source=source.replace('    return app\n',cli+'    return app\n',1)
main.write_text(source)

settings='''
    # Codeforces OIDC: credentials issued in https://codeforces.com/settings/api
    CODEFORCES_OIDC_CLIENT_ID = os.getenv("CODEFORCES_OIDC_CLIENT_ID", "")
    CODEFORCES_OIDC_CLIENT_SECRET = os.getenv("CODEFORCES_OIDC_CLIENT_SECRET", "")
    CODEFORCES_OIDC_REDIRECT_URI = os.getenv("CODEFORCES_OIDC_REDIRECT_URI", "http://localhost:5001/auth/codeforces/callback")
    SAY_FRONTEND_URL = os.getenv("SAY_FRONTEND_URL", "http://localhost:3000")
    SAY_SESSION_COOKIE = "say_session"
    SAY_COOKIE_SECURE = env_bool("SAY_COOKIE_SECURE", False)  # True under HTTPS in production
    MAX_CONTENT_LENGTH = 3 * 1024 * 1024
'''
c=config.read_text()
if 'CODEFORCES_OIDC_CLIENT_ID = ' not in c:
    if 'class Config:' not in c:raise RuntimeError('Cannot find Config class')
    c=c.replace('class Config:', 'class Config:'+settings,1)
config.write_text(c)
print('Patched main.py and config.py; verify with git diff and flask routes.')

# Keep existing SAY profile endpoints compatible while exposing uploaded SAY avatars.
profile_routes=root/'user_profile'/'routes.py'
if profile_routes.is_file():
    x=profile_routes.read_text()
    if '"avatar_url":' not in x:
        marker='        "id": user_profile.id,\n'
        if marker not in x:raise RuntimeError('Profile serializer anchor changed; update manually')
        x=x.replace(marker,marker+'        "display_name": user_profile.display_name,\n        "bio": user_profile.bio or "",\n        "avatar_url": f"/api/avatars/{user_profile.avatar_filename}" if user_profile.avatar_filename else None,\n',1)
        profile_routes.write_text(x)
    # public profile returns SAY avatar and display name without Codeforces artwork
    x=profile_routes.read_text()
    if '"avatar_url":' not in x[x.find('def get_public_profile'):]:
        marker='        "name": user.name,\n'
        if marker not in x:raise RuntimeError('Public profile anchor changed')
        x=x.replace(marker,marker+'        "display_name": user_profile.display_name if user_profile and user_profile.display_name else user.name,\n        "avatar_url": f"/api/avatars/{user_profile.avatar_filename}" if user_profile and user_profile.avatar_filename else None,\n',1)
        profile_routes.write_text(x)
