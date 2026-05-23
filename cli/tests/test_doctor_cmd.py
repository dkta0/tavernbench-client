"""
Regression tests for tavernbench_cli/doctor_cmd.py — specifically the
real_home() vs Path.home() distinction and the fix_home_symlink() logic.

Bug: doctor --fix was creating symlinks inside the profile home
($HOME = ~/.hermes/profiles/coder/home) instead of the real home
(from passwd).  fix_home_symlink() now uses real_home() which resolves
via pwd.getpwuid(os.getuid()).pw_dir, not $HOME.
"""
from __future__ import annotations

import os
import pwd
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# Ensure the package under test is importable
sys.path.insert(0, str(Path(__file__).parent.parent))
from tavernbench_cli import doctor_cmd


# ---------------------------------------------------------------------------
# real_home() unit tests
# ---------------------------------------------------------------------------

class TestRealHome:
    def test_matches_passwd(self):
        """real_home() must match the passwd entry for the current user."""
        expected = Path(pwd.getpwuid(os.getuid()).pw_dir)
        assert doctor_cmd.real_home() == expected

    def test_ignores_home_env(self, tmp_path):
        """real_home() must NOT be affected by a modified $HOME."""
        fake_home = str(tmp_path / "fake_home")
        with mock.patch.dict(os.environ, {"HOME": fake_home}):
            result = doctor_cmd.real_home()
        # Should still equal the passwd entry, not fake_home
        expected = Path(pwd.getpwuid(os.getuid()).pw_dir)
        assert result == expected

    def test_profile_home_follows_env(self, tmp_path):
        """profile_home() should follow $HOME (it uses Path.home())."""
        fake_home = str(tmp_path / "fake_home")
        with mock.patch.dict(os.environ, {"HOME": fake_home}):
            result = doctor_cmd.profile_home()
        assert result == Path(fake_home)


# ---------------------------------------------------------------------------
# fix_home_symlink() regression tests
# ---------------------------------------------------------------------------

class TestFixHomeSymlink:
    def _run_fix(self, real: Path, profile: Path):
        """Patch real_home and profile_home, then call fix_home_symlink."""
        with mock.patch.object(doctor_cmd, "real_home", return_value=real), \
             mock.patch.object(doctor_cmd, "profile_home", return_value=profile):
            return doctor_cmd.fix_home_symlink()

    # --- same home → no-op ---

    def test_same_home_no_change(self, tmp_path):
        """When real home == profile home, no symlink is created."""
        home = tmp_path / "home"
        home.mkdir()
        changed, msg = self._run_fix(home, home)
        assert not changed
        assert "no symlink needed" in msg

    # --- profile config exists, real config absent → create symlink ---

    def test_creates_symlink_in_real_home(self, tmp_path):
        """Symlink is created in real home, NOT in profile home."""
        real = tmp_path / "real_home"
        profile = tmp_path / "profile_home"
        real.mkdir(parents=True)
        profile.mkdir(parents=True)

        # Simulate profile config existing
        profile_cfg = profile / ".config" / "tavernbench"
        profile_cfg.mkdir(parents=True)
        (profile_cfg / "config.toml").write_text('[auth]\napi_key = "tb_test"\n')

        changed, msg = self._run_fix(real, profile)

        assert changed, f"expected change, got: {msg}"
        symlink = real / ".config" / "tavernbench"
        assert symlink.is_symlink(), "symlink not created in real home"
        assert symlink.resolve() == profile_cfg.resolve(), \
            f"symlink points to wrong dir: {symlink.resolve()}"

    def test_symlink_goes_to_real_not_profile(self, tmp_path):
        """Regression: symlink must be in real home, never in profile home."""
        real = tmp_path / "real_home"
        profile = tmp_path / "profile_home"
        real.mkdir(parents=True)
        profile.mkdir(parents=True)

        profile_cfg = profile / ".config" / "tavernbench"
        profile_cfg.mkdir(parents=True)

        self._run_fix(real, profile)

        # The symlink must NOT appear inside the profile home
        bad_symlink = profile / ".config" / "tavernbench"
        assert not bad_symlink.is_symlink() or bad_symlink.is_dir(), \
            "symlink was incorrectly placed inside profile home (the original bug)"

        # It must appear inside the real home
        good_symlink = real / ".config" / "tavernbench"
        assert good_symlink.exists() or good_symlink.is_symlink(), \
            "symlink was not created in real home"

    # --- profile config absent → create real dir ---

    def test_creates_real_dir_when_profile_config_missing(self, tmp_path):
        """If profile config doesn't exist, create the real config dir directly."""
        real = tmp_path / "real_home"
        profile = tmp_path / "profile_home"
        real.mkdir(parents=True)
        profile.mkdir(parents=True)

        # profile_cfg does NOT exist
        changed, msg = self._run_fix(real, profile)

        assert changed
        real_cfg = real / ".config" / "tavernbench"
        assert real_cfg.is_dir()
        assert not real_cfg.is_symlink()

    # --- idempotency ---

    def test_idempotent_second_call(self, tmp_path):
        """Calling fix twice should not fail or create duplicate symlinks."""
        real = tmp_path / "real_home"
        profile = tmp_path / "profile_home"
        real.mkdir(parents=True)
        profile.mkdir(parents=True)

        profile_cfg = profile / ".config" / "tavernbench"
        profile_cfg.mkdir(parents=True)

        self._run_fix(real, profile)
        changed2, msg2 = self._run_fix(real, profile)

        assert not changed2, "second call should report no change"
        assert "already in place" in msg2 or "already exists" in msg2

    # --- real dir already exists (not a symlink) → do nothing ---

    def test_existing_real_dir_not_overwritten(self, tmp_path):
        """If real config dir exists and is not a symlink, leave it alone."""
        real = tmp_path / "real_home"
        profile = tmp_path / "profile_home"
        real.mkdir(parents=True)
        profile.mkdir(parents=True)

        real_cfg = real / ".config" / "tavernbench"
        real_cfg.mkdir(parents=True)
        profile_cfg = profile / ".config" / "tavernbench"
        profile_cfg.mkdir(parents=True)

        changed, msg = self._run_fix(real, profile)
        assert not changed
        assert "already exists" in msg
        assert not real_cfg.is_symlink()


# ---------------------------------------------------------------------------
# check_api_key tests
# ---------------------------------------------------------------------------

class TestCheckApiKey:
    def test_returns_false_when_no_key(self):
        with mock.patch("tavernbench_cli.config.get_api_key", return_value=None):
            ok, msg = doctor_cmd.check_api_key()
        assert not ok
        assert "tavernbench auth" in msg

    def test_returns_true_when_key_present(self):
        with mock.patch("tavernbench_cli.config.get_api_key", return_value="tb_testkey1234"):
            ok, msg = doctor_cmd.check_api_key()
        assert ok
        assert "tb_tes" in msg


# ---------------------------------------------------------------------------
# run() integration smoke test
# ---------------------------------------------------------------------------

class TestRun:
    def test_run_no_fix_returns_int(self, capsys):
        """run() should not raise and should return an int exit code."""
        with mock.patch.object(doctor_cmd, "check_api_key", return_value=(True, "ok")), \
             mock.patch.object(doctor_cmd, "check_server", return_value=(True, "ok")), \
             mock.patch.object(doctor_cmd, "check_mcp_registered", return_value=(True, "ok")):
            rc = doctor_cmd.run(fix=False)
        assert rc == 0

    def test_run_with_fix_calls_fix_home_symlink(self, capsys):
        with mock.patch.object(doctor_cmd, "check_api_key", return_value=(False, "no key")), \
             mock.patch.object(doctor_cmd, "check_server", return_value=(True, "ok")), \
             mock.patch.object(doctor_cmd, "check_mcp_registered", return_value=(True, "ok")), \
             mock.patch.object(doctor_cmd, "fix_home_symlink", return_value=(False, "no-op")) as mock_fix:
            rc = doctor_cmd.run(fix=True)
        mock_fix.assert_called_once()
        assert rc == 1  # one check failed
