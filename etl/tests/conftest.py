from __future__ import annotations

import os
import time
from pathlib import Path

import pytest


@pytest.fixture()
def data_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ETL_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")

    import psycopg

    deadline = time.time() + 30
    last = "unreachable"
    while time.time() < deadline:
        try:
            with psycopg.connect(url) as conn:
                row = conn.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_name = 'puzzles'
                    )
                    """
                ).fetchone()
                if row and row[0]:
                    return url
                last = "puzzles table missing (start docker-compose.test.yml so the API can migrate)"
        except Exception as exc:  # noqa: BLE001 - skip message should include connect errors
            last = str(exc)
        time.sleep(0.4)
    pytest.skip(f"postgres not ready: {last}")
