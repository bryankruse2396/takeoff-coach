"""Site settings come from .env (never committed), or from the environment."""
from coach.config import _read_env_file


def test_env_file_is_read(tmp_path):
    p = tmp_path / ".env"
    p.write_text('# a comment\n\nSUPABASE_URL="https://x.supabase.co"\nSUPABASE_PUBLISHABLE_KEY = sb_publishable_abc\n')
    assert _read_env_file(str(p)) == {"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_abc"}


def test_missing_env_file_gives_nothing(tmp_path):
    assert _read_env_file(str(tmp_path / "nope")) == {}


def test_coach_without_settings_says_what_to_do(monkeypatch):
    import pytest
    from coach import cloud
    monkeypatch.setattr(cloud, "SITE_URL", "")
    with pytest.raises(cloud.SiteError, match="env.example"):
        cloud.Cloud()._http("GET", "/x")
