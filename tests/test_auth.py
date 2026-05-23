"""Tests for tavernbench config and auth command."""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tavernbench.config as cfg
import tavernbench.main as main_mod


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        cfg.CONFIG_DIR = self.tmp
        cfg.CONFIG_FILE = self.tmp / "config.toml"

    def test_load_empty(self):
        self.assertEqual(cfg.load(), {})

    def test_set_and_get_api_key(self):
        cfg.set_api_key("tb_test_key_12345")
        self.assertEqual(cfg.get_api_key(), "tb_test_key_12345")

    def test_config_toml_contents(self):
        cfg.set_api_key("tb_abc")
        contents = (self.tmp / "config.toml").read_text()
        self.assertIn("[auth]", contents)
        self.assertIn("api_key", contents)
        self.assertIn("tb_abc", contents)

    def test_overwrite_key(self):
        cfg.set_api_key("old_key")
        cfg.set_api_key("new_key")
        self.assertEqual(cfg.get_api_key(), "new_key")

    def test_no_key_returns_none(self):
        self.assertIsNone(cfg.get_api_key())

    def test_require_api_key_exits_when_missing(self):
        with self.assertRaises(SystemExit):
            cfg.require_api_key()

    def test_require_api_key_returns_key(self):
        cfg.set_api_key("tb_xyz")
        self.assertEqual(cfg.require_api_key(), "tb_xyz")


class TestAuthCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        cfg.CONFIG_DIR = self.tmp
        cfg.CONFIG_FILE = self.tmp / "config.toml"

    def test_auth_saves_key(self):
        ns = argparse.Namespace()
        with patch("getpass.getpass", return_value="tb_fresh_key"):
            rc = main_mod.cmd_auth(ns)
        self.assertEqual(rc, 0)
        self.assertEqual(cfg.get_api_key(), "tb_fresh_key")

    def test_auth_empty_key_returns_error(self):
        ns = argparse.Namespace()
        with patch("getpass.getpass", return_value=""):
            rc = main_mod.cmd_auth(ns)
        self.assertEqual(rc, 1)

    def test_auth_overwrite_abort(self):
        cfg.set_api_key("tb_original")
        ns = argparse.Namespace()
        with patch("builtins.input", return_value="n"):
            rc = main_mod.cmd_auth(ns)
        self.assertEqual(rc, 0)
        self.assertEqual(cfg.get_api_key(), "tb_original")

    def test_auth_overwrite_confirm(self):
        cfg.set_api_key("tb_original")
        ns = argparse.Namespace()
        with patch("builtins.input", return_value="y"), \
             patch("getpass.getpass", return_value="tb_new"):
            rc = main_mod.cmd_auth(ns)
        self.assertEqual(rc, 0)
        self.assertEqual(cfg.get_api_key(), "tb_new")


if __name__ == "__main__":
    unittest.main()
