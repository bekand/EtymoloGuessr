from __future__ import annotations

import logging
import shutil

from etl.paths import derived_dir, puzzles_dir, raw_dir, reports_dir

log = logging.getLogger(__name__)


def _empty_dir(path) -> None:
    if not path.exists():
        return
    for child in path.iterdir():
        if child.name == ".gitkeep":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    log.info("cleared %s", path)


def reset_data(*, raw: bool = False, derived: bool = False, puzzles: bool = False) -> None:
    if raw:
        _empty_dir(raw_dir())
    if derived:
        _empty_dir(derived_dir())
        _empty_dir(reports_dir())
    if puzzles:
        _empty_dir(puzzles_dir())
