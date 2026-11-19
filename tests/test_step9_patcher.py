"""Pure stdlib Step 9 patcher tests (no Flask requirements)."""
import importlib.util
from pathlib import Path


PATCHER = Path(__file__).resolve().parents[1] / "patches" / "apply_step9.py"
spec = importlib.util.spec_from_file_location("step9_patcher", PATCHER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_main_patcher_twice_does_not_duplicate_blueprints():
    before = (
        "from analytics.routes import analytics\n"
        "from models.user_topic_mastery import UserTopicMastery, UserDifficultyReadiness\n"
        "from codeforces.submission_sync import sync_codeforces_submissions\n"
        "def create_app():\n"
        "    app.register_blueprint(analytics)\n"
        "    @app.cli.command(\"grant-admin\")\n"
    )
    updated = module.patch_main(before)
    assert module.patch_main(updated) == updated
    assert updated.count("app.register_blueprint(codeforces_api)") == 1
    assert updated.count("app.register_blueprint(recommendation_api)") == 1
    assert updated.count('@app.cli.command("process-cf-sync-queue")') == 1


def test_codeforces_patcher_preserves_existing_link_handler():
    before = (
        "        active = _active_account(user.uid)\n"
        "        if active and not confirm_relink:\n"
        "            return {}, 409\n"
    )
    updated = module.patch_cf(before)
    assert module.patch_cf(updated) == updated
    assert "active = _active_account(user.uid)" in updated
    assert "CodeforcesSyncRequest" in updated


def test_config_patcher_idempotent():
    before = 'import os\nclass Config:\n    SECRET_KEY = os.getenv("SECRET_KEY")\n'
    updated = module.patch_config(before)
    assert module.patch_config(updated) == updated
    assert "RECOMMENDATION_WEIGHTS" in updated
    assert "RECOMMENDATION_CANDIDATE_POOL_CAP" in updated
