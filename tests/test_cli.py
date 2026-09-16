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
        assert 2 <= len(p["answer_graph"]["nodes"]) <= 9
        assert "prompt_graph" not in p
        assert len(p["choices"]) == 4
        assert isinstance(p["quality_score"], int)
        assert 3 <= p["quality_score"] <= 5
        glosses = [c["gloss"] for c in p["choices"]]
        assert all(not g.startswith("(unrelated)") for g in glosses)
        assert len(set(glosses)) == 4
        terms = {p["leaf_a"]["term"], p["leaf_b"]["term"]}
        assert terms != {"hound", "Hund"}
        assert terms != {"padre"}
        assert "Paris" not in terms
        assert p["leaf_a"]["lang"] != p["leaf_b"]["lang"]

    # Leaf reuse: no (lang, term) appears twice as a leaf across the batch.
    seen_leaves: set[tuple[str, str]] = set()
    for p in puzzles:
        for leaf in (p["leaf_a"], p["leaf_b"]):
            key = (leaf["lang"], leaf["term"])
            assert key not in seen_leaves
            seen_leaves.add(key)

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


def test_generate_verbose_prints_stage_timings(data_home: Path):
    assert runner.invoke(app, ["refresh", "--fixtures"]).exit_code == 0
    result = runner.invoke(app, ["generate", "-v", "--n", "10", "--dry-run", "--seed", "1"])
    assert result.exit_code == 0, result.output
    err = result.stderr
    assert "[generate] load derived edges" in err
    assert "[generate] build graph" in err
    assert "[generate] candidate pairs" in err or "[generate] ancestor paths" in err
    assert "[generate] emit puzzles" in err
    assert "s (total" in err


def test_generate_verbose_via_global_flag(data_home: Path):
    assert runner.invoke(app, ["refresh", "--fixtures"]).exit_code == 0
    result = runner.invoke(app, ["-v", "generate", "--n", "2", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "[generate] load derived edges" in result.stderr


def test_ids_stable(data_home: Path):
    runner.invoke(app, ["refresh", "--fixtures"])
    runner.invoke(app, ["generate", "--n", "0", "--seed", "99"])
    first = [json.loads(l) for l in (data_home / "puzzles" / "puzzles.jsonl").read_text().splitlines() if l]
    runner.invoke(app, ["generate", "--n", "0", "--seed", "99"])
    second = [json.loads(l) for l in (data_home / "puzzles" / "puzzles.jsonl").read_text().splitlines() if l]
    assert [p["id"] for p in first] == [p["id"] for p in second]


def test_generate_default_min_quality_and_no_placeholders(data_home: Path):
    assert runner.invoke(app, ["refresh", "--fixtures"]).exit_code == 0
    result = runner.invoke(app, ["generate", "--n", "5", "--stdout", "--seed", "1"])
    assert result.exit_code == 0, result.output
    puzzles = json.loads(result.stdout)
    assert len(puzzles) >= 1
    for p in puzzles:
        assert p["quality_score"] >= 3
        assert all(not c["gloss"].startswith("(unrelated)") for c in p["choices"])


def test_validate_rejects_bad_file(tmp_path: Path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({"id": "x", "enabled": True}) + "\n", encoding="utf-8")
    result = runner.invoke(app, ["validate", str(bad)])
    assert result.exit_code != 0


def test_mutual_exclusive_sinks(data_home: Path):
    runner.invoke(app, ["refresh", "--fixtures"])
    result = runner.invoke(app, ["generate", "--stdout", "--db"])
    assert result.exit_code != 0


def test_database_url_missing_config_returns_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ETL_CONFIG", str(tmp_path / "nope.yaml"))
    from etl.paths import database_url

    assert database_url() is None


def test_database_url_invalid_yaml_returns_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    bad = tmp_path / "broken.yaml"
    bad.write_text(":\n  - not: valid: yaml: [", encoding="utf-8")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ETL_CONFIG", str(bad))
    from etl.paths import database_url

    assert database_url() is None


def test_database_url_env_wins_over_broken_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ETL_CONFIG", str(tmp_path / "nope.yaml"))
    monkeypatch.setenv("DATABASE_URL", "postgres://from-env")
    from etl.paths import database_url

    assert database_url() == "postgres://from-env"
