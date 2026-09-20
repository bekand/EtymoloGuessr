from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

from etl.core.models import Puzzle
from etl.core.paths import load_config, reports_dir
from etl.pipeline.derive import load_derived_edges, load_gloss_index, load_lemma_index
from etl.pipeline.emit import emit_puzzles
from etl.pipeline.extract import build_graph, extract_candidates


class Funnel:
    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()

    def bump(self, reason: str, n: int = 1) -> None:
        self.counts[reason] += n

    def as_dict(self) -> dict[str, int]:
        return dict(self.counts)


class StageTimer:
    """Print timed stage progress to stderr when verbose is enabled."""

    def __init__(self, enabled: bool = False, stream=None) -> None:
        self.enabled = enabled
        self.stream = stream or sys.stderr
        self._t0 = time.perf_counter()
        self._last = self._t0

    def stage(self, name: str, detail: str = "") -> None:
        if not self.enabled:
            return
        now = time.perf_counter()
        stage_s = now - self._last
        total_s = now - self._t0
        suffix = f" ({detail})" if detail else ""
        print(
            f"[generate] {name}{suffix}: {stage_s:.3f}s (total {total_s:.3f}s)",
            file=self.stream,
            flush=True,
        )
        self._last = now


def generate_puzzles(
    *,
    n: int | None = None,
    seed: int | None = None,
    lang_pairs: list[str] | None = None,
    min_quality: int | None = None,
    cfg: dict[str, Any] | None = None,
    verbose: bool = False,
) -> tuple[list[Puzzle], Funnel]:
    import random as random_mod

    cfg = cfg or load_config()
    gen_cfg = cfg["generate"]
    n = gen_cfg["n"] if n is None else n
    seed = gen_cfg["seed"] if seed is None else seed
    min_quality = int(gen_cfg["min_quality"] if min_quality is None else min_quality)
    n_choices = int(gen_cfg["n_choices"])
    rng = random_mod.Random(seed)
    timer = StageTimer(enabled=verbose)

    funnel = Funnel()
    edges = load_derived_edges()
    funnel.bump("derived_edges", len(edges))
    timer.stage("load derived edges", f"{len(edges)} rows")

    glosses = load_gloss_index()
    funnel.bump("gloss_index", len(glosses))
    timer.stage("load gloss index", f"{len(glosses)} entries")

    lemmas = load_lemma_index()
    funnel.bump("lemma_index", len(lemmas))
    timer.stage("load lemma index", f"{len(lemmas)} entries")

    g = build_graph(edges, set(cfg["ancestor_reltypes"]))
    funnel.bump("graph_nodes", g.number_of_nodes())
    funnel.bump("graph_edges", g.number_of_edges())
    timer.stage("build graph", f"{g.number_of_nodes()} nodes / {g.number_of_edges()} edges")

    # When n > 0, stop once we have enough quality survivors. Oversample so
    # lang_pair / leaf-reuse / distractor filters still have headroom, and so the
    # distractor pool (built from all extracted LCA glosses) stays diverse.
    extract_limit: int | None = None
    if n and n > 0:
        # Need ≥ n_choices distinct LCA glosses in the pool; oversample for dedup.
        extract_limit = max(n * 5, n_choices * 4) if lang_pairs else max(n * 4, n_choices * 4)

    candidates = extract_candidates(
        g,
        glosses,
        cfg,
        funnel,
        limit=extract_limit,
        min_quality=min_quality,
        progress=timer.stage if verbose else None,
        lemmas=lemmas,
        rng=rng,
    )
    if lang_pairs:
        want = {p.lower() for p in lang_pairs}
        before = len(candidates)
        candidates = [c for c in candidates if c["lang_pair"] in want]
        funnel.bump("lang_pair_filtered", before - len(candidates))
    timer.stage("filter lang pairs", f"{len(candidates)} left")

    before_q = len(candidates)
    candidates = [c for c in candidates if c["quality_score"] >= min_quality]
    funnel.bump("below_min_quality", before_q - len(candidates))
    timer.stage("filter quality", f"{len(candidates)} left (min_quality={min_quality})")

    puzzles = emit_puzzles(
        candidates,
        g=g,
        glosses=glosses,
        funnel=funnel,
        rng=rng,
        n=n,
        n_choices=n_choices,
    )
    timer.stage("emit puzzles", f"{len(puzzles)} puzzles")

    funnel.counts["emitted"] = len(puzzles)
    return puzzles, funnel


def write_funnel(funnel: Funnel, extra: dict[str, Any] | None = None) -> Path:
    dest = reports_dir()
    dest.mkdir(parents=True, exist_ok=True)
    payload = {"funnel": funnel.as_dict(), **(extra or {})}
    path = dest / "funnel.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
