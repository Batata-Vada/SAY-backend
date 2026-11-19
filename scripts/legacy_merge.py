"""Operator-assisted migration to retain historic uid after verified CF OIDC login.

WARNING: Matching a handle is NOT proof a legacy SAY account belongs to the same
person. Only operate after manually verifying ownership of the old SAY data.
"""
from database.db import db
from models.users import User
from models.session import Session
from models.codeforces_account import CodeforcesAccount
from models.codeforces_oidc_identity import CodeforcesOidcIdentity
from models.codeforces_submission import CodeforcesSubmission
from models.codeforces_sync_request import CodeforcesSyncRequest
from models.user_problem_progress import UserProblemProgress
from models.user_topic_mastery import UserTopicMastery, UserDifficultyReadiness
from models.recommendation_log import RecommendationLog
from models.submission import Submission
from models.user_profile import UserProfile
from models.user_education import UserEducation
from models.forum import ForumThread,ForumReply,ForumVote


def merge_empty_verified_identity_into_legacy(legacy_uid:int,verified_uid:int):
    if type(legacy_uid) is not int or type(verified_uid) is not int or legacy_uid==verified_uid:
        raise ValueError('Provide two different numeric SAY uid values')
    old=db.session.get(User,legacy_uid)
    new=db.session.get(User,verified_uid)
    ident=CodeforcesOidcIdentity.query.filter_by(uid=verified_uid).one_or_none()
    if not old or not new or not ident:raise ValueError('Legacy or verified identity does not exist')
    if CodeforcesOidcIdentity.query.filter_by(uid=legacy_uid).first():
        raise ValueError('Legacy uid already has an OIDC identity')
    old_acc=CodeforcesAccount.query.filter_by(uid=legacy_uid,unlinked_at=None).one_or_none()
    new_acc=CodeforcesAccount.query.filter_by(uid=verified_uid,unlinked_at=None).one_or_none()
    if not old_acc or not new_acc or old_acc.handle.casefold()!=ident.handle.casefold() or new_acc.handle.casefold()!=ident.handle.casefold():
        raise ValueError('Both active linked Codeforces handles must match the verified OIDC identity')
    for model,field in [(Submission,'uid'),(UserProblemProgress,'uid'),(UserTopicMastery,'uid'),
                        (UserDifficultyReadiness,'uid'),(RecommendationLog,'uid'),(ForumThread,'author_uid'),
                        (ForumReply,'author_uid'),(ForumVote,'uid'),(UserEducation,'user_id'),
                        (UserProfile,'user_id'),(CodeforcesSyncRequest,'uid')]:
        if db.session.query(model).filter(getattr(model,field)==verified_uid).first():
            raise ValueError('Verified uid has existing data; manual database migration is required: '+model.__tablename__)
    if CodeforcesSubmission.query.filter_by(codeforces_account_id=new_acc.id).first():
        raise ValueError('Verified account has imported submissions; requires a more careful merge')
    if CodeforcesAccount.query.filter_by(uid=verified_uid).count()!=1:
        raise ValueError('Verified uid has other historical account links')
    # Revoke newly issued sessions; user signs in again after reassignment.
    Session.query.filter_by(uid=verified_uid).delete(synchronize_session=False)
    db.session.delete(new_acc)
    db.session.flush()
    ident.uid=legacy_uid
    old_acc.ownership_verified=True
    db.session.flush()
    db.session.delete(new)
    db.session.commit()
    return {'retained_uid':legacy_uid,'verified_subject':ident.subject,'handle':ident.handle,
            'note':'All sessions from the temporary verified account were revoked. Log in again.'}
