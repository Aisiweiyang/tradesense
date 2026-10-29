"""Deployment initialization must honor seed opt-out and migration failures."""
import importlib.util
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import settings
from app.seed import run as seed


@pytest.fixture()
def init_script(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts" / "init_db.py"
    spec = importlib.util.spec_from_file_location("tradesense_init_db", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 0))
    return module


def test_init_without_demo_does_not_create_demo_account(init_script, monkeypatch, capsys):
    monkeypatch.setattr(settings, "seed_demo_data", False)
    monkeypatch.setattr(seed, "ensure_seeded", lambda: pytest.fail("seed disabled"))
    assert init_script.main() == 0
    out = capsys.readouterr().out
    assert "seed disabled" in out
    assert "demo1234" not in out


def test_init_with_demo_seeds_once(init_script, monkeypatch, capsys):
    monkeypatch.setattr(settings, "seed_demo_data", True)
    calls = []
    monkeypatch.setattr(seed, "ensure_seeded", lambda: calls.append(True) or True)
    assert init_script.main() == 0
    assert calls == [True]
    assert "demo seed done" in capsys.readouterr().out


def test_failed_migration_stops_without_stamping_or_seeding(init_script, monkeypatch, capsys):
    calls = []
    def fail(*args, **kwargs):
        calls.append(args[0])
        return subprocess.CompletedProcess(args[0], 1, stderr="test migration failure")
    monkeypatch.setattr(init_script.subprocess, "run", fail)
    monkeypatch.setattr(seed, "ensure_seeded", lambda: pytest.fail("must not seed after migration failure"))
    assert init_script.main() == 1
    assert len(calls) == 1 and calls[0][-2:] == ["upgrade", "head"]
    assert "test migration failure" in capsys.readouterr().err


def test_fresh_database_migrates_without_demo_and_reinitializes(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    db_path = tmp_path / "fresh.db"
    env = {**os.environ, "DATABASE_URL": "sqlite:///" + db_path.as_posix(),
           "SEED_DEMO_DATA": "0", "AI_PROVIDER": "none"}
    def initialize():
        result = subprocess.run([sys.executable, str(backend / "scripts" / "init_db.py")],
                                cwd=tmp_path, env=env, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr
    initialize()
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT count(*) FROM organizations").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 0
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "bbfad02a6489"
        assert sum(row[1] == "settings_json" for row in conn.execute("PRAGMA table_info(organizations)")) == 1
    initialize()
    result = subprocess.run([sys.executable, "-m", "alembic", "downgrade", "-1"],
                            cwd=backend, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(db_path) as conn:
        assert "settings_json" in {row[1] for row in conn.execute("PRAGMA table_info(organizations)")}
    initialize()
