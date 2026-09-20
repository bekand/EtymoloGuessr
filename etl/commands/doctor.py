from __future__ import annotations

from typing import Any

from etl.core.paths import data_dir, database_url, load_config, raw_dir
from etl.pipeline.derive import derived_ready
from etl.pipeline.refresh import sha256_file


def disk_estimate_bytes(cfg: dict[str, Any] | None = None) -> int:
    cfg = cfg or load_config()
    total = int(cfg["sources"]["etymology"].get("bytes_estimate") or 0)
    for g in cfg["sources"].get("glosses") or []:
        total += int(g.get("bytes_estimate") or 0)
    return total


def raw_status() -> dict[str, Any]:
    cfg = load_config()
    raw = raw_dir()
    files: list[dict[str, Any]] = []
    checksum_ok = True
    parquet = raw / cfg["sources"]["etymology"]["name"]
    jsonl = raw / "etymology.jsonl"
    if jsonl.exists() and not parquet.exists():
        files.append({"name": "etymology.jsonl", "present": True, "checksum_ok": True, "note": "fixture/jsonl"})
        etymology_ok = True
    else:
        present = parquet.exists()
        note = None if present else "missing"
        expected_hash = cfg["sources"]["etymology"].get("sha256")
        if present and expected_hash:
            digest = sha256_file(parquet)
            checksum_ok = digest.lower() == expected_hash.lower()
            if not checksum_ok:
                note = "checksum mismatch"
        files.append(
            {"name": parquet.name, "present": present, "checksum_ok": checksum_ok, "note": note}
        )
        etymology_ok = present and checksum_ok
    gloss_files = list(raw.glob("kaikki*.jsonl")) + list(raw.glob("glosses.jsonl"))
    files.append({"name": "glosses", "present": bool(gloss_files), "files": [p.name for p in gloss_files]})
    notice = (raw / "NOTICE").exists()
    manifest = (raw / "manifest.json").exists()
    return {
        "ok": etymology_ok and bool(gloss_files),
        "dir": str(raw),
        "files": files,
        "notice": notice,
        "manifest": manifest,
        "fixture_mode": (raw / "etymology.jsonl").exists(),
    }


def doctor_report() -> dict[str, Any]:
    from etl.store.db import ping

    raw = raw_status()
    derived_ok = derived_ready()
    db_ok, db_msg = ping()
    estimate = disk_estimate_bytes()
    data = data_dir()
    used = 0
    if data.exists():
        used = sum(p.stat().st_size for p in data.rglob("*") if p.is_file())
    return {
        "raw": raw,
        "derived": {"ok": derived_ok, "dir": str(data / "derived")},
        "postgres": {"ok": db_ok, "detail": db_msg, "database_url_set": bool(database_url())},
        "disk": {
            "data_dir": str(data),
            "used_bytes": used,
            "full_refresh_estimate_bytes": estimate,
        },
    }


def format_doctor(report: dict[str, Any]) -> str:
    lines = [
        f"raw: {'ok' if report['raw']['ok'] else 'MISSING'} ({report['raw']['dir']})",
        f"  notice={report['raw']['notice']} manifest={report['raw']['manifest']} fixture_mode={report['raw']['fixture_mode']}",
        f"derived: {'ok' if report['derived']['ok'] else 'MISSING'} ({report['derived']['dir']})",
        f"postgres: {'ok' if report['postgres']['ok'] else 'no'} - {report['postgres']['detail']}",
        f"disk used: {report['disk']['used_bytes']} bytes",
        f"full refresh estimate: {report['disk']['full_refresh_estimate_bytes']} bytes",
    ]
    return "\n".join(lines)
