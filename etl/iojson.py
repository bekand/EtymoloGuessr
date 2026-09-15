from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from etl.models import Puzzle
from etl.paths import default_puzzles_jsonl


def write_jsonl(puzzles: Iterable[Puzzle], path: Path | None = None) -> Path:
    path = path or default_puzzles_jsonl()
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for puzzle in puzzles:
            f.write(json.dumps(puzzle.to_dict(), ensure_ascii=False) + "\n")
            n += 1
    return path


def read_jsonl(path: Path | None = None) -> list[Puzzle]:
    path = path or default_puzzles_jsonl()
    if not path.exists():
        raise SystemExit(f"puzzle file not found: {path}")
    out: list[Puzzle] = []
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(Puzzle.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise SystemExit(f"{path}:{line_no}: invalid puzzle ({exc})") from exc
    return out


def puzzles_to_json(puzzles: list[Puzzle]) -> str:
    return json.dumps([p.to_dict() for p in puzzles], ensure_ascii=False, indent=2)
