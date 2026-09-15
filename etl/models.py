from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Term:
    lang: str
    term: str
    gloss: str | None = None

    @property
    def node_id(self) -> str:
        return node_id(self.lang, self.term)


def node_id(lang: str, term: str) -> str:
    return f"{lang}:{term}"


@dataclass
class GraphNode:
    id: str
    lang: str
    term: str
    gloss: str | None
    role: str  # leaf | ancestor

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GraphEdge:
    source: str
    target: str
    reltype: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {"from": self.source, "to": self.target}
        if self.reltype:
            d["reltype"] = self.reltype
        return d


@dataclass
class Choice:
    id: str
    gloss: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def prompt_graph_from_answer(answer_graph: dict[str, Any]) -> dict[str, Any]:
    """Player-facing prompt: same nodes as gold, no edges.

    Hard mode (future API) may further strip ancestor labels; easy mode
    hides gold until solve. Both start from this derivation of answer_graph.
    Not persisted — derive at inspect/API serve time.
    """
    return {"nodes": list(answer_graph.get("nodes") or []), "edges": []}


@dataclass
class Puzzle:
    id: str
    enabled: bool
    leaf_a: dict[str, Any]
    leaf_b: dict[str, Any]
    answer_graph: dict[str, Any]
    choices: list[dict[str, Any]]
    correct_choice: str
    quality_score: int
    lang_pair: str
    source: str = "etymology-db+kaikki"
    lca: dict[str, Any] = field(default_factory=dict)

    @property
    def prompt_graph(self) -> dict[str, Any]:
        """Derived prompt view; not stored in JSONL or Postgres."""
        return prompt_graph_from_answer(self.answer_graph)

    def to_dict(self) -> dict[str, Any]:
        # Store gold once. Consumers that need a prompt view call
        # prompt_graph_from_answer / Puzzle.prompt_graph (or the future API).
        return {
            "id": self.id,
            "enabled": self.enabled,
            "leaf_a": self.leaf_a,
            "leaf_b": self.leaf_b,
            "answer_graph": self.answer_graph,
            "choices": self.choices,
            "correct_choice": self.correct_choice,
            "quality_score": self.quality_score,
            "lang_pair": self.lang_pair,
            "source": self.source,
            "lca": self.lca,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Puzzle:
        if "prompt_graph" in data:
            raise ValueError(
                "prompt_graph is not stored; derive via prompt_graph_from_answer(answer_graph)"
            )
        return cls(
            id=data["id"],
            enabled=bool(data.get("enabled", True)),
            leaf_a=data["leaf_a"],
            leaf_b=data["leaf_b"],
            answer_graph=data["answer_graph"],
            choices=data["choices"],
            correct_choice=data["correct_choice"],
            quality_score=int(data.get("quality_score") or 0),
            lang_pair=data["lang_pair"],
            source=data.get("source", "etymology-db+kaikki"),
            lca=data.get("lca") or {},
        )
