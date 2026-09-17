from __future__ import annotations

import json
from pathlib import Path

import psycopg
import pytest
from typer.testing import CliRunner

from etl.cli import app

pytestmark = pytest.mark.integration

runner = CliRunner()


@pytest.fixture(autouse=True)
def _truncate_puzzles(test_database_url: str) -> None:
    with psycopg.connect(test_database_url) as conn:
        conn.execute("TRUNCATE TABLE scores, puzzles")
        conn.commit()


@pytest.fixture()
def db_home(data_home: Path, test_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    return data_home


def _puzzles_jsonl(data_home: Path) -> Path:
    return data_home / "puzzles" / "puzzles.jsonl"


def test_load_upsert_is_idempotent(db_home: Path, test_database_url: str):
    assert runner.invoke(app, ["refresh", "--fixtures"]).exit_code == 0
    assert runner.invoke(app, ["generate", "--n", "0", "--seed", "1"]).exit_code == 0
    jsonl = _puzzles_jsonl(db_home)
    puzzles = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines() if line]
    assert len(puzzles) >= 3

    first = runner.invoke(app, ["load", str(jsonl)])
    assert first.exit_code == 0, first.output
    second = runner.invoke(app, ["load", str(jsonl)])
    assert second.exit_code == 0, second.output

    with psycopg.connect(test_database_url) as conn:
        count = conn.execute("SELECT count(*) FROM puzzles").fetchone()[0]
    assert count == len(puzzles)

    result = runner.invoke(app, ["validate", "--db"])
    assert result.exit_code == 0, result.output
    assert "ok" in result.stdout


def test_disable_skips_enabled_lookup(db_home: Path, test_database_url: str):
    assert runner.invoke(app, ["refresh", "--fixtures"]).exit_code == 0
    assert runner.invoke(app, ["generate", "--n", "0", "--seed", "1"]).exit_code == 0
    jsonl = _puzzles_jsonl(db_home)
    puzzles = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines() if line]
    target = puzzles[0]["id"]

    assert runner.invoke(app, ["load", str(jsonl)]).exit_code == 0
    result = runner.invoke(app, ["disable", target])
    assert result.exit_code == 0, result.output

    with psycopg.connect(test_database_url) as conn:
        enabled = conn.execute("SELECT enabled FROM puzzles WHERE id = %s", (target,)).fetchone()[0]
        remaining = conn.execute("SELECT count(*) FROM puzzles WHERE enabled").fetchone()[0]
    assert enabled is False
    assert remaining == len(puzzles) - 1


def test_reset_puzzles_keeps_users(db_home: Path, test_database_url: str):
    assert runner.invoke(app, ["refresh", "--fixtures"]).exit_code == 0
    generate = runner.invoke(app, ["generate", "--db", "--n", "0", "--seed", "1"])
    assert generate.exit_code == 0, generate.output
    assert "replaced" in generate.stdout

    with psycopg.connect(test_database_url) as conn:
        conn.execute("INSERT INTO users DEFAULT VALUES")
        conn.commit()
        users_before = conn.execute("SELECT count(*) FROM users").fetchone()[0]
        puzzles_before = conn.execute("SELECT count(*) FROM puzzles").fetchone()[0]
    assert users_before >= 1
    assert puzzles_before >= 1

    result = runner.invoke(app, ["reset", "--puzzles"])
    assert result.exit_code == 0, result.output

    with psycopg.connect(test_database_url) as conn:
        users_after = conn.execute("SELECT count(*) FROM users").fetchone()[0]
        puzzles_after = conn.execute("SELECT count(*) FROM puzzles").fetchone()[0]
        tables = conn.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name IN ('users', 'puzzles', 'scores')
            """
        ).fetchall()
    assert users_after == users_before
    assert puzzles_after == 0
    assert {row[0] for row in tables} == {"users", "puzzles", "scores"}
    assert not (db_home / "puzzles" / "puzzles.jsonl").exists()
