from __future__ import annotations

import hashlib
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from etl.core.paths import FIXTURES_DIR, load_config, raw_dir

log = logging.getLogger(__name__)

NOTICE = """Etymology data
==============

Derived from Wiktionary (https://en.wiktionary.org/) via:

- etymology-db (https://github.com/droher/etymology-db) — CC BY-SA 3.0
- wiktextract / kaikki.org dictionary dumps — Wiktionary, CC BY-SA

Downstream puzzle data remains CC BY-SA 3.0 (share-alike).
"""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    log.info("downloading %s -> %s", url, dest)
    with httpx.stream("GET", url, follow_redirects=True, timeout=120.0) as resp:
        resp.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in resp.iter_bytes():
                f.write(chunk)
    tmp.replace(dest)


def _verify(path: Path, expected: str | None) -> str:
    digest = sha256_file(path)
    if expected and digest.lower() != expected.lower():
        raise SystemExit(f"checksum mismatch for {path.name}: got {digest}, expected {expected}")
    return digest


def _source_entries(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    sources = cfg["sources"]
    entries = [sources["etymology"]]
    entries.extend(sources.get("glosses") or [])
    return entries


def install_fixtures(dest: Path | None = None) -> None:
    dest = dest or raw_dir()
    dest.mkdir(parents=True, exist_ok=True)
    stale_parquet = dest / "etymology.parquet"
    if stale_parquet.exists():
        stale_parquet.unlink()
    for src in FIXTURES_DIR.iterdir():
        if src.is_file() and src.suffix in {".jsonl", ".txt"}:
            shutil.copy2(src, dest / src.name)
    (dest / "NOTICE").write_text(NOTICE, encoding="utf-8")
    manifest = {
        "source": "fixtures",
        "copied_at": datetime.now(timezone.utc).isoformat(),
        "files": sorted(p.name for p in dest.iterdir() if p.is_file()),
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    log.info("copied fixtures into %s", dest)


def refresh(*, force: bool = False, skip_derived: bool = False, fixtures: bool = False) -> None:
    dest = raw_dir()
    dest.mkdir(parents=True, exist_ok=True)
    if fixtures:
        install_fixtures(dest)
    else:
        cfg = load_config()
        files_meta: list[dict[str, Any]] = []
        for entry in _source_entries(cfg):
            name = entry["name"]
            url = entry["url"]
            path = dest / name
            expected = entry.get("sha256")
            if path.exists() and not force:
                digest = _verify(path, expected)
                log.info("using cached %s (%s)", name, digest[:12])
            else:
                _download(url, path)
                digest = _verify(path, expected)
                log.info("stored %s (%s)", name, digest[:12])
            files_meta.append(
                {
                    "name": name,
                    "url": url,
                    "sha256": digest,
                    "bytes": path.stat().st_size,
                    "lang": entry.get("lang"),
                }
            )
        (dest / "NOTICE").write_text(NOTICE, encoding="utf-8")
        manifest = {
            "source": "download",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "files": files_meta,
        }
        (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    if not skip_derived:
        from etl.pipeline.derive import rebuild_derived

        rebuild_derived()

