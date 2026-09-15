from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Optional

import typer

from etl.db import disable_puzzle, fetch_puzzles, truncate_puzzles, upsert_puzzles
from etl.doctor import doctor_report, format_doctor
from etl.generate import generate_puzzles, write_funnel
from etl.inspect_cmd import format_puzzle
from etl.iojson import puzzles_to_json, read_jsonl, write_jsonl
from etl.logutil import setup_logging
from etl.models import Puzzle
from etl.paths import default_puzzles_jsonl
from etl.refresh import refresh as refresh_cmd
from etl.reset import reset_data
from etl.stats import collect_stats
from etl.validate import validate_puzzles

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Etymology puzzle ETL")
log = logging.getLogger(__name__)


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    setup_logging(verbose)


@app.command()
def refresh(
    force: bool = typer.Option(False, "--force", help="Re-download even if files exist"),
    skip_derived: bool = typer.Option(False, "--skip-derived", help="Download only; skip graph/gloss rebuild"),
    fixtures: bool = typer.Option(False, "--fixtures", help="Copy etl/fixtures into data/raw instead of downloading"),
) -> None:
    """Fetch dumps into data/raw and rebuild derived graph + gloss index."""
    refresh_cmd(force=force, skip_derived=skip_derived, fixtures=fixtures)
    typer.echo("refresh complete")


@app.command()
def generate(
    n: int = typer.Option(None, "--n", help="Max puzzles to emit; 0 = all that pass filters"),
    seed: int = typer.Option(None, "--seed"),
    lang_pair: list[str] = typer.Option(None, "--lang-pair", help="Repeatable, e.g. en-de"),
    min_quality: Optional[int] = typer.Option(None, "--min-quality"),
    stdout: bool = typer.Option(False, "--stdout", help="Print JSON to stdout"),
    jsonl: Optional[Path] = typer.Option(
        None,
        "--jsonl",
        help="Write JSONL (default data/puzzles/puzzles.jsonl if no other sink)",
        show_default=False,
    ),
    db: bool = typer.Option(False, "--db", help="Upsert into Postgres"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Counts and funnel only, no write"),
) -> None:
    """Extract puzzles from derived artifacts (does not download)."""
    sinks = sum([stdout, db, jsonl is not None])
    if sinks > 1:
        raise typer.BadParameter("choose one sink: --stdout, --jsonl, or --db")

    puzzles, funnel = generate_puzzles(
        n=n,
        seed=seed,
        lang_pairs=list(lang_pair) if lang_pair else None,
        min_quality=min_quality,
    )
    path = write_funnel(funnel, extra={"n_requested": n, "dry_run": dry_run})
    typer.echo(f"funnel: {funnel.as_dict()}", err=True)
    typer.echo(f"wrote {path}", err=True)

    if dry_run:
        typer.echo(f"dry-run: would emit {len(puzzles)} puzzles")
        return

    if stdout:
        typer.echo(puzzles_to_json(puzzles))
        return
    if db:
        count = upsert_puzzles(puzzles)
        typer.echo(f"upserted {count} puzzles")
        return
    dest = jsonl or default_puzzles_jsonl()
    write_jsonl(puzzles, dest)
    typer.echo(f"wrote {len(puzzles)} puzzles to {dest}")


@app.command()
def reset(
    puzzles: bool = typer.Option(False, "--puzzles", help="Truncate puzzle rows and local JSONL"),
    derived: bool = typer.Option(False, "--derived", help="Delete data/derived"),
    raw: bool = typer.Option(False, "--raw", help="Delete downloads in data/raw"),
    all_data: bool = typer.Option(False, "--all", help="raw + derived + puzzles"),
    reload: bool = typer.Option(False, "--reload", help="Then refresh + generate --db"),
    fixtures: bool = typer.Option(False, "--fixtures", help="With --reload, refresh from fixtures"),
) -> None:
    """Regenerate from scratch. Never drops the database or users/scores tables."""
    if all_data:
        raw = derived = puzzles = True
    if not (raw or derived or puzzles or reload):
        puzzles = True

    if puzzles:
        try:
            truncate_puzzles()
            typer.echo("truncated puzzles table")
        except SystemExit as exc:
            typer.echo(f"skip db truncate: {exc}", err=True)
        reset_data(puzzles=True)

    reset_data(raw=raw, derived=derived, puzzles=False)

    if reload:
        refresh_cmd(force=True, skip_derived=False, fixtures=fixtures)
        puzzles_out, funnel = generate_puzzles()
        write_funnel(funnel, extra={"reload": True})
        count = upsert_puzzles(puzzles_out)
        write_jsonl(puzzles_out)
        typer.echo(f"reloaded {count} puzzles")
        return

    typer.echo("reset complete")


@app.command()
def doctor() -> None:
    """Check raw dumps, derived artifacts, Postgres, and disk estimate."""
    report = doctor_report()
    typer.echo(format_doctor(report))
    typer.echo(json.dumps(report, indent=2, default=str))
    ok = report["raw"]["ok"] and report["derived"]["ok"]
    if not ok:
        raise typer.Exit(code=1)


@app.command()
def stats(
    jsonl: Optional[Path] = typer.Option(None, "--jsonl", help="Puzzle JSONL to summarize"),
) -> None:
    """Edge counts, puzzle counts by lang-pair, and last generation funnel."""
    payload = collect_stats(jsonl)
    from etl.paths import reports_dir

    snapshot = reports_dir() / "stats.json"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    typer.echo(json.dumps(payload, indent=2, default=str))
    typer.echo(f"wrote {snapshot}", err=True)


@app.command()
def inspect(
    puzzle_id: Optional[str] = typer.Argument(None),
    random: bool = typer.Option(False, "--random"),
    lang_pair: Optional[str] = typer.Option(None, "--lang-pair"),
    jsonl: Optional[Path] = typer.Option(None, "--jsonl"),
    db: bool = typer.Option(False, "--db"),
) -> None:
    """Print one puzzle as readable text (leaves, glosses, choices, gold edges)."""
    if db:
        rows = fetch_puzzles(puzzle_id=puzzle_id, lang_pair=lang_pair, random=random or not puzzle_id)
        if not rows:
            raise SystemExit("no matching puzzle in database")
        puzzle = Puzzle.from_dict(rows[0])
    else:
        puzzles = read_jsonl(jsonl or default_puzzles_jsonl())
        if lang_pair:
            puzzles = [p for p in puzzles if p.lang_pair == lang_pair]
        if puzzle_id:
            puzzles = [p for p in puzzles if p.id == puzzle_id]
            if not puzzles:
                raise SystemExit(f"puzzle not found: {puzzle_id}")
        if not puzzles:
            raise SystemExit("no puzzles to inspect")
        if random or not puzzle_id:
            import random as random_mod

            puzzle = random_mod.choice(puzzles)
        else:
            puzzle = puzzles[0]
    typer.echo(format_puzzle(puzzle))


@app.command()
def validate(
    path: Optional[Path] = typer.Argument(None),
    db: bool = typer.Option(False, "--db"),
) -> None:
    """Schema-check puzzles from JSONL or Postgres."""
    if db:
        rows = fetch_puzzles()
        puzzles = [Puzzle.from_dict(row) for row in rows]
        source = "database"
    else:
        puzzles = read_jsonl(path or default_puzzles_jsonl())
        source = str(path or default_puzzles_jsonl())
    errors = validate_puzzles(puzzles)
    typer.echo(f"validated {len(puzzles)} puzzles from {source}")
    if errors:
        for e in errors:
            typer.echo(e, err=True)
        raise typer.Exit(code=1)
    typer.echo("ok")


@app.command()
def load(
    path: Path = typer.Argument(..., exists=True, readable=True),
) -> None:
    """JSONL to DB upsert without regenerating."""
    puzzles = read_jsonl(path)
    errors = validate_puzzles(puzzles)
    if errors:
        for e in errors:
            typer.echo(e, err=True)
        raise typer.Exit(code=1)
    count = upsert_puzzles(puzzles)
    typer.echo(f"upserted {count} puzzles from {path}")


@app.command()
def disable(puzzle_id: str = typer.Argument(...)) -> None:
    """Set enabled=false after a bad eyeball (API should skip these)."""
    if disable_puzzle(puzzle_id):
        typer.echo(f"disabled {puzzle_id}")
    else:
        raise SystemExit(f"puzzle not found: {puzzle_id}")

if __name__ == "__main__":
    app()
