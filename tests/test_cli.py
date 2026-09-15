from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from etl.cli import app

runner = CliRunner()


@pytest.fixture()
def data_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ETL_DATA_DIR", str(tmp_path))
    return tmp_path


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ["refresh", "generate", "reset", "doctor", "stats", "inspect", "validate", "load", "disable"]:
        assert cmd in result.stdout


def test_refresh_fixtures_generate_validate_inspect(data_home: Path):
    result = runner.invoke(app, ["refresh", "--fixtures"])
    assert result.exit_code == 0, result.output
    assert (data_home / "raw" / "etymology.jsonl").exists()
    assert (data_home / "raw" / "NOTICE").exists()
    assert (data_home / "derived" / "edges.parquet").exists()

    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["generate", "--n", "0", "--seed", "1"])
    assert result.exit_code == 0, result.output
    jsonl = data_home / "puzzles" / "puzzles.jsonl"
    assert jsonl.exists()
    puzzles = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines() if line]
    assert len(puzzles) >= 3
    ids = {p["id"] for p in puzzles}
    assert len(ids) == len(puzzles)
    for p in puzzles:
        assert 3 <= len(p["answer_graph"]["nodes"]) <= 5
        assert p["prompt_graph"]["edges"] == []
        assert len(p["choices"]) == 4
        assert isinstance(p["quality_score"], int)
        assert 0 <= p["quality_score"] <= 5
        terms = {p["leaf_a"]["term"], p["leaf_b"]["term"]}
        assert terms != {"hound", "Hund"}
        assert terms != {"padre"}

    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["inspect", "--lang-pair", "de-en"])
    assert result.exit_code == 0, result.output
    assert "gold edges:" in result.stdout
    assert "choices:" in result.stdout

    result = runner.invoke(app, ["generate", "--n", "0", "--stdout", "--seed", "1"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert isinstance(payload, list) and payload

    result = runner.invoke(app, ["generate", "--dry-run", "--n", "2"])
    assert result.exit_code == 0, result.output
    assert "dry-run" in result.stdout

    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 0, result.output
    stats = json.loads(result.stdout)
    assert stats["puzzles"]["n_puzzles"] >= 3
    assert (data_home / "reports" / "funnel.json").exists()

    result = runner.invoke(app, ["reset", "--derived"])
    assert result.exit_code == 0
    assert not (data_home / "derived" / "edges.parquet").exists()


def test_refresh_fixtures_replaces_stale_parquet(data_home: Path):
    raw = data_home / "raw"
    raw.mkdir(parents=True)
    stale_parquet = raw / "etymology.parquet"
    stale_parquet.write_bytes(b"stale download")

    result = runner.invoke(app, ["refresh", "--fixtures"])

    assert result.exit_code == 0, result.output
    assert not stale_parquet.exists()
    assert (data_home / "derived" / "edges.parquet").exists()


def test_generate_requires_derived(data_home: Path):
    result = runner.invoke(app, ["generate", "--stdout"])
    assert result.exit_code != 0


def test_ids_stable(data_home: Path):
    runner.invoke(app, ["refresh", "--fixtures"])
    runner.invoke(app, ["generate", "--n", "0", "--seed", "99"])
    first = [json.loads(l) for l in (data_home / "puzzles" / "puzzles.jsonl").read_text().splitlines() if l]
    runner.invoke(app, ["generate", "--n", "0", "--seed", "99"])
    second = [json.loads(l) for l in (data_home / "puzzles" / "puzzles.jsonl").read_text().splitlines() if l]
    assert [p["id"] for p in first] == [p["id"] for p in second]


def test_validate_rejects_bad_file(tmp_path: Path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({"id": "x", "enabled": True}) + "\n", encoding="utf-8")
    result = runner.invoke(app, ["validate", str(bad)])
    assert result.exit_code != 0


def test_mutual_exclusive_sinks(data_home: Path):
    runner.invoke(app, ["refresh", "--fixtures"])
    result = runner.invoke(app, ["generate", "--stdout", "--db"])
    assert result.exit_code != 0
