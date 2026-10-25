"""Concept-note knowledge graph for versioned Stellaris mechanics.

See ``docs/knowledge-graph.md`` for the note format and resolution rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from .game_knowledge import (
    _LATIN_WORD_PATTERN,
    DEFAULT_PATCHES_DIR,
    DELTA_ALWAYS_INCLUDE_CHARS,
    MAX_INDEX_LABELS,
    _keyword_matches,
    parse_version,
)

DEFAULT_KNOWLEDGE_DIR = DEFAULT_PATCHES_DIR / "knowledge"
TOPIC_CHAR_BUDGET = 8000

Version = tuple[int, int, int]
GraphStatus = Literal["exact", "partial", "notes_only", "unsupported_newer", "unavailable"]

_FRONT_MATTER_PATTERN = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
_COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
_METADATA_PATTERN = re.compile(r"\s*\{([^{}]*)\}\s*$")
_LINK_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
_LABEL_PATTERN = re.compile(r"^\s*[*-]\s+\*\*(.+?)\*\*")
_TITLE_STOPWORDS = frozenset({"a", "an", "and", "by", "for", "in", "of", "on", "the", "to", "vs"})


@dataclass(frozen=True)
class Fact:
    """One present-tense mechanic and the versions where it holds."""

    text: str
    since: Version | None
    until: Version | None

    def holds_for(self, version: Version) -> bool:
        return (self.since is None or self.since <= version) and (
            self.until is None or version < self.until
        )

    @property
    def label(self) -> str | None:
        match = _LABEL_PATTERN.match(self.text)
        return match.group(1).strip().rstrip(":") if match else None


@dataclass(frozen=True)
class ConceptNote:
    """A concept with its player-facing terms, links, and versioned facts."""

    key: str
    title: str
    terms: dict[str, tuple[str, ...]]
    links: tuple[str, ...]
    facts: tuple[Fact, ...]
    always: bool = False
    version_independent: bool = False
    verified_through: Version | None = None


@dataclass(frozen=True)
class KnowledgeGraph:
    notes: dict[str, ConceptNote]
    min_version: Version | None
    breaking_lines: tuple[tuple[int, int], ...]
    # Releases whose notes were reviewed, including those that changed no fact.
    reviewed_releases: tuple[Version, ...] = ()

    def resolve_link(self, target: str) -> str | None:
        key = _note_key(target)
        return key if key in self.notes else None

    def newest_line(self) -> tuple[int, int] | None:
        lines = list(self.breaking_lines)
        lines.extend(version[:2] for version in self.reviewed_releases)
        for note in self.notes.values():
            if note.verified_through:
                lines.append(note.verified_through[:2])
            lines.extend(fact.since[:2] for fact in note.facts if fact.since)
        return max(lines, default=None)


@dataclass(frozen=True)
class GraphKnowledge:
    """Resolved graph mechanics for one game version and request."""

    status: GraphStatus
    loaded_through: str | None
    content: str | None
    matched_topics: bool


def _note_key(name: str) -> str:
    return re.sub(r"[^0-9a-z]+", "-", name.strip().lower()).strip("-")


def _parse_value(raw: str) -> object:
    value = raw.strip()
    if value.startswith("[") and value.endswith("]"):
        return tuple(item.strip().strip("\"'") for item in value[1:-1].split(",") if item.strip())
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    return value.strip("\"'")


def parse_front_matter(text: str) -> tuple[dict[str, object], str]:
    """Parse the small YAML subset used by notes: scalars, inline lists, one nesting level."""
    match = _FRONT_MATTER_PATTERN.match(text)
    if not match:
        return {}, text
    data: dict[str, object] = {}
    parent: dict[str, object] | None = None
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.strip().partition(":")
        if not separator:
            raise ValueError(f"Invalid front matter line: {line!r}")
        if line.startswith((" ", "\t")):
            if parent is None:
                raise ValueError(f"Indented front matter without a parent: {line!r}")
            parent[key.strip()] = _parse_value(value)
        elif value.strip():
            data[key.strip()] = _parse_value(value)
            parent = None
        else:
            parent = {}
            data[key.strip()] = parent
    return data, text[match.end() :]


def _parse_metadata(raw: str) -> dict[str, Version]:
    metadata: dict[str, Version] = {}
    for item in raw.split(","):
        key, separator, value = item.partition(":")
        version = parse_version(value.strip())
        if not separator or version is None or key.strip() not in {"since", "until"}:
            raise ValueError(f"Invalid fact metadata: {{{raw}}}")
        metadata[key.strip()] = version
    return metadata


def parse_facts(body: str) -> list[Fact]:
    """Split a note body into bullet and table facts with their version metadata."""
    facts: list[Fact] = []
    lines: list[str] = []
    kind: str | None = None
    metadata: dict[str, Version] = {}

    def flush() -> None:
        nonlocal lines, kind, metadata
        if lines:
            facts.append(
                Fact("\n".join(lines).strip(), metadata.get("since"), metadata.get("until"))
            )
        lines, kind, metadata = [], None, {}

    for line in _COMMENT_PATTERN.sub("", body).splitlines():
        stripped = line.strip()
        if not stripped:
            if kind == "bullet":
                flush()
            continue
        if stripped.startswith("#") or stripped.lower().startswith("related:"):
            flush()
            continue
        if kind == "table" and stripped.startswith("{") and stripped.endswith("}"):
            metadata = _parse_metadata(stripped[1:-1])
            flush()
            continue
        if stripped.startswith("|"):
            if kind != "table":
                flush()
                kind = "table"
            lines.append(stripped)
            continue
        if kind == "table":
            flush()
        if stripped.startswith(("- ", "* ")) and not line[0].isspace():
            flush()
            kind = "bullet"
            lines.append(stripped)
        elif kind == "bullet":
            lines.append(stripped)
        else:
            continue
        trailing = _METADATA_PATTERN.search(lines[-1])
        if kind == "bullet" and trailing:
            metadata = _parse_metadata(trailing.group(1))
            lines[-1] = lines[-1][: trailing.start()].rstrip()
            flush()
    flush()
    return facts


def parse_note(text: str, *, fallback_title: str) -> ConceptNote:
    front_matter, body = parse_front_matter(text)
    title_match = re.search(r"(?m)^#\s+(.+?)\s*$", body)
    title = title_match.group(1) if title_match else fallback_title
    raw_terms = front_matter.get("terms") or {}
    terms = {
        str(language): tuple(values) if isinstance(values, tuple) else (str(values),)
        for language, values in (raw_terms.items() if isinstance(raw_terms, dict) else ())
    }
    verified = front_matter.get("verified_through")
    return ConceptNote(
        key=_note_key(title),
        title=title,
        terms=terms,
        links=tuple(
            dict.fromkeys(
                _note_key(match.group(1)) for match in _LINK_PATTERN.finditer(_strip(body))
            )
        ),
        facts=tuple(parse_facts(body)),
        always=front_matter.get("always") is True,
        version_independent=front_matter.get("version_independent") is True,
        verified_through=parse_version(str(verified)) if verified else None,
    )


def _strip(text: str) -> str:
    return _COMMENT_PATTERN.sub("", text)


@lru_cache(maxsize=8)
def load_knowledge_graph(directory: Path = DEFAULT_KNOWLEDGE_DIR) -> KnowledgeGraph | None:
    """Load the concept notes under ``directory``; ``None`` when no graph exists."""
    manifest_path = directory / "_manifest.md"
    if not manifest_path.exists():
        return None
    manifest, _ = parse_front_matter(manifest_path.read_text(encoding="utf-8"))

    def manifest_versions(name: str) -> tuple[Version, ...]:
        raw = manifest.get(name) or ()
        return tuple(
            version
            for item in (raw if isinstance(raw, tuple) else (raw,))
            if (version := parse_version(str(item))) is not None
        )

    lines = tuple(version[:2] for version in manifest_versions("breaking_lines"))
    notes: dict[str, ConceptNote] = {}
    for path in sorted((directory / "concepts").glob("*.md")):
        note = parse_note(path.read_text(encoding="utf-8"), fallback_title=path.stem)
        if note.key in notes:
            raise ValueError(f"Duplicate concept note: {note.title}")
        notes[note.key] = note
    return KnowledgeGraph(
        notes=notes,
        min_version=parse_version(str(manifest.get("min_version") or "")),
        breaking_lines=tuple(sorted(lines)),
        reviewed_releases=manifest_versions("reviewed_releases"),
    )


def graph_covers(graph: KnowledgeGraph | None, version: Version) -> bool:
    return bool(graph and graph.min_version is not None and version >= graph.min_version)


def _eligible_facts(graph: KnowledgeGraph, version: Version) -> tuple[dict[str, list[Fact]], bool]:
    """Return facts that hold for ``version`` and whether every note was cut at a breaking line."""
    boundary = max((line for line in graph.breaking_lines if line <= version[:2]), default=None)
    eligible: dict[str, list[Fact]] = {}
    carried_notes = 0
    versioned_notes = 0
    for key, note in graph.notes.items():
        cut = bool(
            boundary
            and not note.version_independent
            and (note.verified_through is None or note.verified_through[:2] < boundary)
        )
        facts = [
            fact
            for fact in note.facts
            if fact.holds_for(version)
            and (not cut or (fact.since is not None and fact.since[:2] >= boundary))
        ]
        if facts:
            eligible[key] = facts
            if not note.version_independent:
                versioned_notes += 1
                carried_notes += cut
    return eligible, bool(versioned_notes and carried_notes == versioned_notes)


def _is_delta(note: ConceptNote, fact: Fact) -> bool:
    return fact.since is not None and (
        note.verified_through is None or fact.since > note.verified_through
    )


def _plain_terms(text: str) -> set[str]:
    """Words and their singular forms; synonyms belong in each note's ``terms``."""
    words = set(_LATIN_WORD_PATTERN.findall(text.lower()))
    words.update(
        f"{word[:-3]}y" if word.endswith("ies") else word[:-1]
        for word in tuple(words)
        if len(word) > 3 and word.endswith(("ies", "s"))
    )
    return words


def _note_score(note: ConceptNote, topics: str) -> int:
    topic_terms = _plain_terms(topics)
    title_words = _plain_terms(note.title) - _TITLE_STOPWORDS
    keywords = tuple(term for values in note.terms.values() for term in values)
    return len(
        (topic_terms & title_words) | _keyword_matches(keywords, topic_terms, topics.lower())
    )


def _render_fact(fact: Fact) -> str:
    return _LINK_PATTERN.sub(lambda match: match.group(2) or match.group(1), fact.text)


def _render_note(note: ConceptNote, facts: list[Fact]) -> str:
    return "\n".join([f"## {note.title}", *(_render_fact(fact) for fact in facts)])


def resolve_graph_knowledge(
    graph: KnowledgeGraph,
    version: Version,
    *,
    topics: str | None = None,
    fallback_topics: str | None = None,
    limit: int = 3,
) -> GraphKnowledge:
    """Select and render the graph facts relevant to a request for one game version."""
    newest_line = graph.newest_line()
    if newest_line is not None and version[:2] > newest_line:
        return GraphKnowledge("unsupported_newer", ".".join(map(str, newest_line)), None, False)

    eligible, notes_only = _eligible_facts(graph, version)
    if not eligible:
        return GraphKnowledge("unavailable", None, None, False)

    versioned = [
        (graph.notes[key], fact)
        for key, facts in eligible.items()
        if not graph.notes[key].version_independent
        for fact in facts
    ]
    verified = [note.verified_through for note, _ in versioned if note.verified_through]
    has_delta = any(_is_delta(note, fact) for note, fact in versioned)
    if notes_only:
        status: GraphStatus = "notes_only"
        through = max((fact.since for _, fact in versioned if fact.since), default=None)
    elif not has_delta and verified and min(verified) >= version:
        status, through = "exact", version
    else:
        status = "partial"
        through = max(
            [*verified, *(fact.since for note, fact in versioned if _is_delta(note, fact))],
            default=None,
        )
    loaded_through = ".".join(map(str, through)) if through else None

    if topics is None:
        rendered = [_render_note(graph.notes[key], facts) for key, facts in eligible.items()]
        return GraphKnowledge(status, loaded_through, "\n\n".join(rendered), True)

    selected: dict[str, list[Fact]] = {}
    for key, facts in eligible.items():
        if graph.notes[key].always:
            selected[key] = list(facts)
    deltas = {
        key: [fact for fact in facts if _is_delta(graph.notes[key], fact)]
        for key, facts in eligible.items()
        if key not in selected
    }
    if (
        sum(len(fact.text) for facts in deltas.values() for fact in facts)
        <= DELTA_ALWAYS_INCLUDE_CHARS
    ):
        for key, facts in deltas.items():
            if facts:
                selected[key] = facts

    candidates = [key for key in eligible if not graph.notes[key].always]

    def rank(text: str) -> list[str]:
        scored = [(_note_score(graph.notes[key], text), key) for key in candidates]
        return [key for score, key in sorted(scored, key=lambda item: -item[0]) if score > 0]

    seeds = rank(topics)[: max(0, limit)]
    if not seeds and fallback_topics:
        seeds = rank(fallback_topics)[: max(0, limit)]

    budget = TOPIC_CHAR_BUDGET

    def add_whole(key: str, *, force: bool = False) -> bool:
        nonlocal budget
        size = sum(len(fact.text) for fact in eligible[key])
        if not force and size > budget:
            return False
        selected[key] = list(eligible[key])
        budget -= size
        return True

    for index, key in enumerate(seeds):
        add_whole(key, force=index == 0)

    seed_set = set(seeds)
    connections: dict[str, int] = {}
    for key in candidates:
        if key in seed_set:
            continue
        note_links = set(graph.notes[key].links)
        count = len(note_links & seed_set) + sum(key in graph.notes[seed].links for seed in seeds)
        if count:
            connections[key] = count
    neighbors = [
        key
        for key in sorted(connections, key=lambda item: (-connections[item], item))
        if selected.get(key) != eligible[key]
    ]
    for key in neighbors[: max(0, limit)]:
        add_whole(key)

    # Insertion order: always-on notes, unreviewed deltas, seeds, then neighbors.
    order = list(eligible)
    sections = [_render_note(graph.notes[key], facts) for key, facts in selected.items()]
    if not seeds:
        index_lines = []
        for key in order:
            if key in selected and selected[key] == eligible[key]:
                continue
            labels = [label for fact in eligible[key] if (label := fact.label)]
            if labels:
                more = ", ..." if len(labels) > MAX_INDEX_LABELS else ""
                index_lines.append(
                    f"- {graph.notes[key].title}: {', '.join(labels[:MAX_INDEX_LABELS])}{more}"
                )
        if index_lines:
            sections.append(
                "Other verified mechanics areas for this version (details omitted; when a "
                "request touches one, do not assert older-version rules for it):\n"
                + "\n".join(index_lines)
            )
    return GraphKnowledge(status, loaded_through, "\n\n".join(sections) or None, bool(seeds))
