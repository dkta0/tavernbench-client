"""
Tests for the TavernBench MCP server (mcp/server.py).

All 5 tools are tested without a live server — the WS/HTTP fallback paths are
exercised so the tests are fully offline.
"""
from __future__ import annotations

import json
import os
import sys
import uuid

import pytest

# ---------------------------------------------------------------------------
# Path setup — ensure mcp/ and sdk/ are importable from tests/
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
_MCP_DIR = os.path.join(_REPO, "mcp")
_SDK_DIR = os.path.join(_REPO, "sdk")
_CLI_DIR = os.path.join(_REPO, "cli")

for _p in [_CLI_DIR, _SDK_DIR]:
    if _p not in sys.path:
        sys.path.insert(0, _p)
# sdk must come BEFORE cli/ so 'tavernbench' resolves to sdk/tavernbench (has client.py).
# Re-order: remove both, then insert sdk at 0, cli after.
for _p in [_CLI_DIR, _SDK_DIR]:
    while _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, _CLI_DIR)
sys.path.insert(0, _SDK_DIR)

# Clear any cached 'tavernbench' module(s) so importlib picks up sdk/tavernbench
# (has client.py) rather than cli/tavernbench (config only).  This matters when
# test_auth.py runs first and caches the cli version.
for _key in list(sys.modules.keys()):
    if _key == "tavernbench" or _key.startswith("tavernbench."):
        del sys.modules[_key]

if _MCP_DIR not in sys.path:
    sys.path.insert(0, _MCP_DIR)

# Import server module by file path to avoid shadowing the 'mcp' pip package
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("mcp_server", os.path.join(_MCP_DIR, "server.py"))
mcp_server = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(mcp_server)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _jloads(s: str) -> dict | list:
    return json.loads(s)


def _fresh_run(ranked: bool = False, scenario: str = "") -> dict:
    """Call tavernbench_start_run and return the parsed result."""
    result = _jloads(mcp_server.tavernbench_start_run(scenario_id=scenario, ranked=ranked))
    return result


# ---------------------------------------------------------------------------
# list_scenarios
# ---------------------------------------------------------------------------

class TestListScenarios:
    def test_returns_list(self):
        raw = mcp_server.tavernbench_list_scenarios()
        data = _jloads(raw)
        # Either a real list from the server or the offline default
        assert isinstance(data, list) or (isinstance(data, dict) and "error" in data)

    def test_offline_fallback_contains_tavern_hall(self, monkeypatch):
        """When the server is unreachable, a default scenario list is returned."""
        import urllib.request
        def _fail(*a, **kw):
            raise OSError("offline")
        monkeypatch.setattr(urllib.request, "urlopen", _fail)

        data = _jloads(mcp_server.tavernbench_list_scenarios())
        assert isinstance(data, list)
        assert len(data) >= 1
        ids = [s["id"] for s in data]
        assert "tavern_hall" in ids

    def test_scenario_shape(self, monkeypatch):
        import urllib.request
        def _fail(*a, **kw):
            raise OSError("offline")
        monkeypatch.setattr(urllib.request, "urlopen", _fail)

        data = _jloads(mcp_server.tavernbench_list_scenarios())
        for scenario in data:
            assert "id" in scenario
            assert "name" in scenario
            assert "description" in scenario
            assert "difficulty" in scenario


# ---------------------------------------------------------------------------
# start_run
# ---------------------------------------------------------------------------

class TestStartRun:
    def test_returns_required_keys(self):
        result = _fresh_run()
        assert "run_id" in result
        assert "brief" in result
        assert "observation" in result
        assert "ranked_pending" in result

    def test_run_id_is_uuid(self):
        result = _fresh_run()
        # must be parseable as UUID
        uuid.UUID(result["run_id"])

    def test_casual_ranked_pending_false(self):
        result = _fresh_run(ranked=False)
        assert result["ranked_pending"] is False

    def test_ranked_ranked_pending_true(self):
        result = _fresh_run(ranked=True)
        assert result["ranked_pending"] is True

    def test_run_registered(self):
        result = _fresh_run()
        assert result["run_id"] in mcp_server.RUN_REGISTRY

    def test_custom_scenario_id_stored(self):
        result = _fresh_run(scenario="custom_zone")
        run = mcp_server.RUN_REGISTRY[result["run_id"]]
        assert run["zone_id"] == "custom_zone"

    def test_default_scenario_is_tavern_hall(self):
        result = _fresh_run(scenario="")
        run = mcp_server.RUN_REGISTRY[result["run_id"]]
        assert run["zone_id"] == "tavern_hall"

    def test_brief_is_string(self):
        result = _fresh_run()
        assert isinstance(result["brief"], str)
        assert len(result["brief"]) > 10

    def test_observation_shape(self):
        result = _fresh_run()
        obs = result["observation"]
        for key in ("tick", "zone_id", "entities", "inventory", "quests", "score", "steps"):
            assert key in obs, f"observation missing key: {key}"


# ---------------------------------------------------------------------------
# confirm_ranked
# ---------------------------------------------------------------------------

class TestConfirmRanked:
    def test_confirms_ranked_run(self):
        run_id = _fresh_run(ranked=True)["run_id"]
        result = _jloads(mcp_server.tavernbench_confirm_ranked(run_id))
        assert result["confirmed"] is True
        assert "started_at" in result

    def test_confirm_casual_run_also_works(self):
        """confirm_ranked can be called on any run; it just sets confirmed=True."""
        run_id = _fresh_run(ranked=False)["run_id"]
        result = _jloads(mcp_server.tavernbench_confirm_ranked(run_id))
        assert result["confirmed"] is True

    def test_confirm_unknown_run_returns_error(self):
        result = _jloads(mcp_server.tavernbench_confirm_ranked("no-such-run"))
        assert "error" in result

    def test_confirm_sets_registry_flag(self):
        run_id = _fresh_run(ranked=True)["run_id"]
        assert mcp_server.RUN_REGISTRY[run_id]["confirmed"] is False
        mcp_server.tavernbench_confirm_ranked(run_id)
        assert mcp_server.RUN_REGISTRY[run_id]["confirmed"] is True


# ---------------------------------------------------------------------------
# act
# ---------------------------------------------------------------------------

class TestAct:
    def test_unknown_run_returns_error(self):
        result = _jloads(mcp_server.tavernbench_act("bad-id", "look"))
        assert "error" in result

    def test_unknown_action_returns_error(self):
        run_id = _fresh_run()["run_id"]
        result = _jloads(mcp_server.tavernbench_act(run_id, "frobulate"))
        # Either server-level error or action error — either way 'error' key
        assert "error" in result

    def test_valid_action_keys_when_server_down(self):
        """With no live server, act() should still return a structured error dict."""
        run_id = _fresh_run()["run_id"]
        result = _jloads(mcp_server.tavernbench_act(run_id, "look"))
        # Could be error (no server) or success; either way must be a dict
        assert isinstance(result, dict)

    def test_all_14_action_names_accepted(self):
        """The dispatcher must recognise all 14 canonical action strings (no typos)."""
        valid_actions = [
            "move", "enter", "speak", "reply", "examine", "pickup", "drop",
            "use", "attack", "flee", "inventory", "quests", "look", "wait",
        ]
        run_id = _fresh_run()["run_id"]
        for action in valid_actions:
            result = _jloads(mcp_server.tavernbench_act(run_id, action))
            # Must NOT contain the "Unknown action" error text
            error_msg = result.get("error", "")
            assert "Unknown action" not in error_msg, f"Action {action!r} not recognised"


# ---------------------------------------------------------------------------
# observe
# ---------------------------------------------------------------------------

class TestObserve:
    def test_unknown_run_returns_error(self):
        result = _jloads(mcp_server.tavernbench_observe("bad-id"))
        assert "error" in result

    def test_known_run_returns_dict(self):
        run_id = _fresh_run()["run_id"]
        result = _jloads(mcp_server.tavernbench_observe(run_id))
        assert isinstance(result, dict)

    def test_observe_wraps_in_observation_key_or_error(self):
        run_id = _fresh_run()["run_id"]
        result = _jloads(mcp_server.tavernbench_observe(run_id))
        # With no live server it'll be an error; that's fine
        assert "observation" in result or "error" in result


# ---------------------------------------------------------------------------
# CLI wiring — mcp serve dispatches to run_server
# ---------------------------------------------------------------------------

class TestMcpServeCli:
    def test_run_server_callable(self):
        """mcp/server.py must export run_server as a callable."""
        assert callable(mcp_server.run_server)

    def test_commands_mcp_serve_dispatches(self, monkeypatch):
        """tavernbench mcp serve should call mcp_server.run_server, not print a stub."""
        import tavernbench_cli.commands as cmds
        called = []

        # Patch server.run_server in the already-loaded mcp_server module
        orig = mcp_server.run_server
        mcp_server.run_server = lambda: called.append(True)

        # Also patch via sys.modules so that cmds.mcp_serve()'s `from server import run_server`
        # picks up our fake.  We do this by injecting into sys.modules['server'].
        import types
        fake_server_mod = types.ModuleType("server")
        fake_server_mod.run_server = lambda: called.append(True)
        orig_server = sys.modules.get("server")
        sys.modules["server"] = fake_server_mod

        try:
            cmds.mcp_serve()
        except (SystemExit, Exception):
            pass
        finally:
            mcp_server.run_server = orig
            if orig_server is None:
                sys.modules.pop("server", None)
            else:
                sys.modules["server"] = orig_server

        assert called, "mcp_serve() did not invoke run_server()"
