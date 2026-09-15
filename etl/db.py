from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterable, Iterator

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from etl.models import Puzzle
from etl.paths import database_url

PUZZLES_COLUMNS = (
    "id",
    "enabled",
    "leaf_a",
    "leaf_b",
    "prompt_graph",
    "answer_graph",
    "choices",
    "correct_choice",
    "quality_score",
    "lang_pair",
    "source",
)

UPSERT_SQL = """
INSERT INTO puzzles (
    id, enabled, leaf_a, leaf_b, prompt_graph, answer_graph,
    choices, correct_choice, quality_score, lang_pair, source
) VALUES (
    %(id)s, %(enabled)s, %(leaf_a)s, %(leaf_b)s, %(prompt_graph)s, %(answer_graph)s,
    %(choices)s, %(correct_choice)s, %(quality_score)s, %(lang_pair)s, %(source)s
)
ON CONFLICT (id) DO UPDATE SET
    enabled = EXCLUDED.enabled,
    leaf_a = EXCLUDED.leaf_a,
    leaf_b = EXCLUDED.leaf_b,
    prompt_graph = EXCLUDED.prompt_graph,
    answer_graph = EXCLUDED.answer_graph,
    choices = EXCLUDED.choices,
    correct_choice = EXCLUDED.correct_choice,
    quality_score = EXCLUDED.quality_score,
    lang_pair = EXCLUDED.lang_pair,
    source = EXCLUDED.source
"""


def require_database_url() -> str:
    url = database_url()
    if not url:
        raise SystemExit("DATABASE_URL is not set")
    return url


def connect(url: str | None = None) -> psycopg.Connection:
    return psycopg.connect(url or require_database_url())


@contextmanager
def connection_scope(conn: psycopg.Connection | None = None) -> Iterator[psycopg.Connection]:
    owns_connection = conn is None
    active_connection = conn or connect()
    try:
        yield active_connection
    finally:
        if owns_connection:
            active_connection.close()


def puzzles_table_exists(conn: psycopg.Connection) -> bool:
    row = conn.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'puzzles'
        )
        """
    ).fetchone()
    return bool(row and row[0])


def _row(puzzle: Puzzle) -> dict[str, Any]:
    d = puzzle.to_dict()
    # prompt_graph is derived from answer_graph; still written for the legacy
    # Postgres column until Go migrations drop it.
    return {
        "id": d["id"],
        "enabled": d["enabled"],
        "leaf_a": Jsonb(d["leaf_a"]),
        "leaf_b": Jsonb(d["leaf_b"]),
        "prompt_graph": Jsonb(puzzle.prompt_graph),
        "answer_graph": Jsonb(d["answer_graph"]),
        "choices": Jsonb(d["choices"]),
        "correct_choice": d["correct_choice"],
        "quality_score": d["quality_score"],
        "lang_pair": d["lang_pair"],
        "source": d["source"],
    }


def upsert_puzzles(puzzles: Iterable[Puzzle], conn: psycopg.Connection | None = None) -> int:
    with connection_scope(conn) as active_connection:
        if not puzzles_table_exists(active_connection):
            raise SystemExit("puzzles table is missing - run Go migrations first (etl doctor)")
        count = 0
        with active_connection.cursor() as cur:
            for puzzle in puzzles:
                cur.execute(UPSERT_SQL, _row(puzzle))
                count += 1
        active_connection.commit()
        return count


def fetch_puzzles(
    *,
    puzzle_id: str | None = None,
    lang_pair: str | None = None,
    random: bool = False,
    conn: psycopg.Connection | None = None,
) -> list[dict[str, Any]]:
    with connection_scope(conn) as active_connection:
        if not puzzles_table_exists(active_connection):
            raise SystemExit("puzzles table is missing - run Go migrations first (etl doctor)")
        query = sql.SQL("SELECT {columns} FROM puzzles").format(
            columns=sql.SQL(", ").join(sql.Identifier(column) for column in PUZZLES_COLUMNS)
        )
        params: dict[str, Any] = {}
        clauses: list[sql.SQL] = []
        if puzzle_id:
            clauses.append(sql.SQL("id = %(id)s"))
            params["id"] = puzzle_id
        if lang_pair:
            clauses.append(sql.SQL("lang_pair = %(lang_pair)s"))
            params["lang_pair"] = lang_pair
        if clauses:
            query += sql.SQL(" WHERE ") + sql.SQL(" AND ").join(clauses)
        if random:
            query += sql.SQL(" ORDER BY random() LIMIT 1")
        rows = active_connection.execute(query, params).fetchall()
        return [dict(zip(PUZZLES_COLUMNS, row)) for row in rows]


def disable_puzzle(puzzle_id: str) -> bool:
    with connect() as conn:
        if not puzzles_table_exists(conn):
            raise SystemExit("puzzles table is missing - run Go migrations first (etl doctor)")
        cur = conn.execute(
            "UPDATE puzzles SET enabled = false WHERE id = %s",
            (puzzle_id,),
        )
        conn.commit()
        return cur.rowcount > 0


def truncate_puzzles() -> None:
    with connect() as conn:
        if not puzzles_table_exists(conn):
            raise SystemExit("puzzles table is missing - run Go migrations first (etl doctor)")
        conn.execute("TRUNCATE TABLE puzzles")
        conn.commit()


def ping() -> tuple[bool, str]:
    url = database_url()
    if not url:
        return False, "DATABASE_URL is not set"
    try:
        with connect(url) as conn:
            conn.execute("SELECT 1")
            if puzzles_table_exists(conn):
                return True, "reachable; puzzles table present"
            return True, "reachable; puzzles table missing (run Go migrations)"
    except Exception as exc:  # noqa: BLE001 - doctor should never crash
        return False, str(exc)
