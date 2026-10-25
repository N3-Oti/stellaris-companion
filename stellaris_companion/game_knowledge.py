"""Versioned, provider-neutral Stellaris mechanics for model prompts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .paths import get_repo_root


def _find_default_patches_dir(module_file: Path = Path(__file__)) -> Path:
    """Find source, package-local, or PyInstaller-sibling knowledge resources."""
    package_dir = module_file.resolve().parent
    candidates = (
        get_repo_root(module_file) / "patches",
        package_dir / "patches",
        package_dir.parent / "patches",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return package_dir / "patches"


DEFAULT_PATCHES_DIR = _find_default_patches_dir()
DEFAULT_SNAPSHOTS_DIR = DEFAULT_PATCHES_DIR / "snapshots"

# Cygnus changed the Pop Group data model, so Pegasus' compiled mechanics cannot
# serve as its baseline. Add future release lines here only after a breaking audit.
BREAKING_SNAPSHOT_BOUNDARIES = frozenset({(4, 5)})

# Release-line deltas each correct a stale belief, so they bypass topic selection
# while they stay small. Larger delta packs fall back to keyword selection.
DELTA_ALWAYS_INCLUDE_CHARS = 8000
MAX_INDEX_LABELS = 6

_VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")
_MARKDOWN_SECTION_PATTERN = re.compile(r"(?m)^(#{1,3})\s+(.+?)\s*$")
_COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
_KEYWORDS_COMMENT_PATTERN = re.compile(r"<!--\s*keywords\s*\n(.*?)-->", re.DOTALL | re.IGNORECASE)
_BOLD_LABEL_PATTERN = re.compile(r"(?m)^\s*[*-]\s+\*\*(.+?)\*\*")
_LATIN_WORD_PATTERN = re.compile(r"[0-9a-z\u00c0-\u024f]+")
_SEARCH_ALIASES: dict[str, tuple[str, ...]] = {
    "pop": ("population", "workforce", "colony"),
    "growth": ("population", "workforce", "colony"),
    "job": ("population", "workforce"),
    "district": ("planet", "development", "production"),
    "building": ("planet", "development", "production"),
    "resource": ("economy", "trade", "production", "reserve"),
    "energy": ("economy", "production", "reserve"),
    "mineral": ("economy", "production", "reserve"),
    "alloy": ("economy", "production"),
    "food": ("economy", "production"),
    "technology": ("research", "science", "focus"),
    "tech": ("research", "science", "focus"),
    "scientist": ("research", "science"),
    "ship": ("naval", "fleet", "starbase"),
    "anchorage": ("naval", "fleet", "starbase"),
    "psi": ("psionic", "shroud"),
    "gaia": ("infernal", "hot"),
    "battle": ("combat", "war", "threat"),
    "army": ("combat", "war", "military"),
    "invasion": ("combat", "war", "military"),
    "occupation": ("combat", "war"),
    "arkship": ("nomad", "logistics"),
    "waystation": ("nomad", "logistics", "contract"),
    "wayline": ("nomad", "logistics"),
    "cargo": ("reserve", "economy", "logistics"),
    "abundance": ("reserve", "economy"),
    "astral": ("automation", "reliability", "science"),
    "rift": ("automation", "reliability", "science"),
    "automated": ("automation", "reliability"),
}

KnowledgeStatus = Literal["exact", "partial", "unsupported_newer", "unavailable"]
KnowledgePurpose = Literal["advisor", "chronicle"]


@dataclass(frozen=True)
class GameKnowledgeContext:
    """Resolved mechanics and their coverage for one game version."""

    requested_version: str
    target_version: str | None
    loaded_through: str | None
    status: KnowledgeStatus
    content: str | None
    # Lower-cased section title -> maintainer keywords in every language.
    section_keywords: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    # Offset in ``content`` where release-line deltas begin, if any.
    delta_offset: int | None = None


def parse_version(version: str) -> tuple[int, int, int] | None:
    """Parse a major.minor[.patch] version into a sortable tuple."""
    match = re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+))?", str(version or "").strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def extract_version(version: str) -> str | None:
    """Extract the most specific numeric version from a display string."""
    match = _VERSION_PATTERN.search(str(version or ""))
    if not match:
        return None
    parts = [match.group(1), match.group(2)]
    if match.group(3) is not None:
        parts.append(match.group(3))
    return ".".join(parts)


def clean_knowledge_content(content: str) -> str:
    """Remove maintainer comments while retaining model-useful Markdown structure."""
    cleaned = _COMMENT_PATTERN.sub("", content)
    lines = [line.rstrip() for line in cleaned.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    # Removed comments can leave stacked blank lines; one is enough for Markdown.
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines))


def list_versioned_markdown(directory: Path) -> list[str]:
    """List version-named Markdown files in numeric order."""
    if not directory.exists():
        return []
    versions: list[tuple[tuple[int, int, int], str]] = []
    for file_path in directory.glob("*.md"):
        parsed = parse_version(file_path.stem)
        if parsed is not None:
            versions.append((parsed, file_path.stem))
    versions.sort(key=lambda item: item[0])
    return [version for _, version in versions]


def parse_section_keywords(text: str) -> dict[str, dict[str, tuple[str, ...]]]:
    """Map each section title to its maintainer-authored keywords by language.

    Keywords live in a comment inside the section, one language per line::

        <!-- keywords
        ja: ポップ, 人口
        de: Bevölkerung
        -->
    """
    without_notes = _COMMENT_PATTERN.sub(
        lambda match: match.group(0) if _KEYWORDS_COMMENT_PATTERN.fullmatch(match.group(0)) else "",
        text,
    )
    headings = list(_MARKDOWN_SECTION_PATTERN.finditer(without_notes))
    keywords_by_section: dict[str, dict[str, tuple[str, ...]]] = {}
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(without_notes)
        languages: dict[str, tuple[str, ...]] = {}
        for block in _KEYWORDS_COMMENT_PATTERN.finditer(without_notes, heading.end(), end):
            for line in block.group(1).splitlines():
                language, separator, values = line.partition(":")
                terms = tuple(value.strip() for value in values.split(",") if value.strip())
                if separator and terms:
                    languages[language.strip()] = languages.get(language.strip(), ()) + terms
        if languages:
            keywords_by_section[heading.group(2).strip()] = languages
    return keywords_by_section


def _load_document(version: str, directory: Path) -> tuple[str, dict[str, tuple[str, ...]]] | None:
    path = directory / f"{version}.md"
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    keywords = {
        title.lower(): tuple(term for terms in languages.values() for term in terms)
        for title, languages in parse_section_keywords(raw).items()
    }
    return clean_knowledge_content(raw), keywords


def _load_file(version: str, directory: Path) -> str | None:
    document = _load_document(version, directory)
    return document[0] if document else None


def _has_non_latin_letters(text: str) -> bool:
    """Detect scripts (e.g. Japanese, Chinese) that are matched by substring, not words."""
    return any(char.isalpha() and ord(char) > 0x024F for char in text)


def _search_terms(text: str) -> set[str]:
    terms = set(_LATIN_WORD_PATTERN.findall(text.lower()))
    singular_terms = {
        f"{term[:-3]}y" if term.endswith("ies") else term[:-1]
        for term in terms
        if len(term) > 3 and term.endswith(("ies", "s"))
    }
    terms.update(singular_terms)
    for term in tuple(terms):
        terms.update(_SEARCH_ALIASES.get(term, ()))
    return terms


def _keyword_matches(keywords: tuple[str, ...], topic_terms: set[str], topic_text: str) -> set[str]:
    matched: set[str] = set()
    for keyword in keywords:
        normalized = keyword.lower()
        if _has_non_latin_letters(normalized):
            if normalized in topic_text:
                matched.add(normalized)
            continue
        words = _LATIN_WORD_PATTERN.findall(normalized)
        if words and all(
            word in topic_terms
            or (len(word) > 3 and word.endswith("s") and word[:-1] in topic_terms)
            for word in words
        ):
            matched.update(words)
    return matched


def _topic_candidates(
    headings: list[re.Match[str]],
    topics: str,
    *,
    skip: set[int],
    section_keywords: Mapping[str, tuple[str, ...]],
) -> list[tuple[int, int, int, set[str]]]:
    topic_terms = _search_terms(topics)
    topic_text = topics.lower()
    candidates: list[tuple[int, int, int, set[str]]] = []
    document_index = -1
    for index, match in enumerate(headings):
        if match.group(1) == "#":
            document_index += 1
        if index in skip:
            continue
        title = match.group(2).strip()
        matched_terms = (topic_terms & _search_terms(title)) | _keyword_matches(
            section_keywords.get(title.lower(), ()), topic_terms, topic_text
        )
        if matched_terms:
            candidates.append((len(matched_terms), document_index, index, matched_terms))

    # A newer overlay with the same topic takes precedence over an older snapshot.
    return [
        candidate
        for candidate in candidates
        if not any(
            newer_document > candidate[1] and len(candidate[3] & newer_terms) >= 2
            for _, newer_document, _, newer_terms in candidates
        )
    ]


def _section_index_line(title: str, body: str) -> str | None:
    labels = [label.strip().rstrip(":") for label in _BOLD_LABEL_PATTERN.findall(body)]
    if not labels:
        return None
    shown = ", ".join(labels[:MAX_INDEX_LABELS])
    more = ", ..." if len(labels) > MAX_INDEX_LABELS else ""
    return f"- {title}: {shown}{more}"


def _select_relevant_sections(
    content: str,
    topics: str,
    *,
    limit: int,
    section_keywords: Mapping[str, tuple[str, ...]] | None = None,
    delta_offset: int | None = None,
    fallback_topics: str | None = None,
) -> str:
    """Keep safety baselines plus the few mechanics sections relevant to a request.

    Small release-line deltas are always kept. When neither the request nor the
    recent conversation matches a section, an index of the omitted sections tells
    the model which areas have version-specific rules instead of silently dropping
    them.
    """
    headings = list(_MARKDOWN_SECTION_PATTERN.finditer(content))
    if not headings:
        return content

    keywords = section_keywords or {}
    keep_deltas = (
        delta_offset is not None and len(content) - delta_offset <= DELTA_ALWAYS_INCLUDE_CHARS
    )
    selected: set[int] = set()
    for index, match in enumerate(headings):
        normalized_title = match.group(2).strip().lower()
        if (keep_deltas and match.start() >= (delta_offset or 0)) or (
            "critical 4.x baseline" in normalized_title
            or "interpretation guardrails" in normalized_title
        ):
            selected.add(index)

    candidates = _topic_candidates(headings, topics, skip=selected, section_keywords=keywords)
    if not candidates and fallback_topics:
        candidates = _topic_candidates(
            headings, fallback_topics, skip=selected, section_keywords=keywords
        )
    candidates.sort(key=lambda item: (-item[0], -item[1], -item[2]))
    selected.update(index for _, _, index, _ in candidates[:limit])

    def section_body(index: int) -> str:
        start = headings[index].start()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(content)
        return content[start:end].strip()

    sections = [section_body(index) for index in sorted(selected)]
    if not candidates:
        index_lines = [
            line
            for index, match in enumerate(headings)
            if index not in selected
            and (line := _section_index_line(match.group(2).strip(), section_body(index)))
        ]
        if index_lines:
            sections.append(
                "Other verified mechanics areas for this version (details omitted; when a "
                "request touches one, do not assert older-version rules for it):\n"
                + "\n".join(index_lines)
            )
    return "\n\n".join(sections)


def load_game_knowledge(
    version: str,
    *,
    cumulative: bool = True,
    prefer_snapshot: bool = True,
    patches_dir: Path = DEFAULT_PATCHES_DIR,
    snapshots_dir: Path = DEFAULT_SNAPSHOTS_DIR,
) -> GameKnowledgeContext:
    """Resolve mechanics without presenting stale knowledge as current truth."""
    target_version = extract_version(version)
    target_key = parse_version(target_version) if target_version else None
    if target_key is None or target_version is None:
        return GameKnowledgeContext(version, None, None, "unavailable", None)

    patch_versions = list_versioned_markdown(patches_dir)
    snapshot_versions = list_versioned_markdown(snapshots_dir)
    snapshot_keys = [parse_version(item) for item in snapshot_versions]
    newest_snapshot_key = max((key for key in snapshot_keys if key is not None), default=None)
    # Release-note deltas for a newer game line are useful, but combining them
    # with an older complete snapshot would reintroduce superseded mechanics.
    notes_only_line = bool(
        target_key[:2] in BREAKING_SNAPSHOT_BOUNDARIES
        and (newest_snapshot_key is None or target_key[:2] > newest_snapshot_key[:2])
        and any(
            (key := parse_version(item)) is not None and key[:2] == target_key[:2]
            for item in patch_versions
        )
    )
    known_versions = patch_versions + snapshot_versions
    known_keys = [parse_version(item) for item in known_versions]
    comparable_keys = [item for item in known_keys if item is not None]
    newest_key = max(comparable_keys, default=None)

    if newest_key is not None and target_key[:2] > newest_key[:2]:
        return GameKnowledgeContext(
            version,
            target_version,
            ".".join(str(part) for part in newest_key),
            "unsupported_newer",
            None,
        )

    if not cumulative:
        content_parts: list[str] = []
        loaded_version: str | None = None
        for patch_version in patch_versions:
            patch_key = parse_version(patch_version)
            if patch_key is None:
                continue
            if patch_key[:2] == target_key[:2] and patch_key <= target_key:
                content = _load_file(patch_version, patches_dir)
                if content:
                    content_parts.append(content)
                    loaded_version = patch_version
        status: KnowledgeStatus = (
            "exact" if loaded_version == target_version and not notes_only_line else "partial"
        )
        return GameKnowledgeContext(
            version,
            target_version,
            loaded_version,
            status if content_parts else "unavailable",
            "\n\n".join(content_parts) if content_parts else None,
        )

    content_parts = []
    loaded_version = None
    snapshot_key: tuple[int, int, int] | None = None
    section_keywords: dict[str, tuple[str, ...]] = {}
    delta_offset: int | None = 0 if notes_only_line else None

    if prefer_snapshot and not notes_only_line:
        eligible = [
            (parsed, snapshot_version)
            for snapshot_version in snapshot_versions
            if (parsed := parse_version(snapshot_version)) is not None and parsed <= target_key
        ]
        if eligible:
            snapshot_key, snapshot_version = eligible[-1]
            document = _load_document(snapshot_version, snapshots_dir)
            if document and document[0]:
                content_parts.append(document[0])
                section_keywords.update(document[1])
                loaded_version = snapshot_version
                delta_offset = len(document[0]) + 2
            else:
                snapshot_key = None

    for patch_version in patch_versions:
        patch_key = parse_version(patch_version)
        if patch_key is None or patch_key > target_key:
            continue
        if notes_only_line and patch_key[:2] != target_key[:2]:
            continue
        if snapshot_key is not None and patch_key <= snapshot_key:
            continue
        document = _load_document(patch_version, patches_dir)
        if document and document[0]:
            content_parts.append(document[0])
            for title, terms in document[1].items():
                section_keywords[title] = section_keywords.get(title, ()) + terms
            loaded_version = patch_version

    status = "exact" if loaded_version == target_version and not notes_only_line else "partial"
    return GameKnowledgeContext(
        version,
        target_version,
        loaded_version,
        status if content_parts else "unavailable",
        "\n\n".join(content_parts) if content_parts else None,
        section_keywords,
        delta_offset,
    )


def build_game_knowledge_prompt(
    version: str,
    *,
    purpose: KnowledgePurpose,
    topics: str | None = None,
    fallback_topics: str | None = None,
    max_topic_sections: int = 3,
    patches_dir: Path = DEFAULT_PATCHES_DIR,
    snapshots_dir: Path = DEFAULT_SNAPSHOTS_DIR,
    knowledge_dir: Path | None = None,
) -> str:
    """Build shared evidence rules and verified mechanics for a model system prompt.

    Versions covered by the concept-note graph (``patches/knowledge``) resolve through
    it; older versions use the snapshot and release-note files.
    ``fallback_topics`` (such as recent questions) is consulted only when ``topics``
    matches no section, so follow-up questions keep their earlier subject.
    """
    from .knowledge_graph import graph_covers, load_knowledge_graph, resolve_graph_knowledge

    target_key = parse_version(extract_version(version) or "")
    graph = load_knowledge_graph(knowledge_dir or patches_dir / "knowledge")
    if graph is not None and target_key is not None and graph_covers(graph, target_key):
        resolved = resolve_graph_knowledge(
            graph,
            target_key,
            topics=topics,
            fallback_topics=fallback_topics,
            limit=max(0, max_topic_sections),
        )
        status = resolved.status
        loaded_through = resolved.loaded_through
        knowledge_content = resolved.content
        notes_only = status == "notes_only"
        has_knowledge = status in {"exact", "partial", "notes_only"}
    else:
        knowledge = load_game_knowledge(
            version,
            patches_dir=patches_dir,
            snapshots_dir=snapshots_dir,
        )
        status = knowledge.status
        loaded_through = knowledge.loaded_through
        has_knowledge = bool(knowledge.content)
        knowledge_content = knowledge.content
        if knowledge_content and topics is not None:
            knowledge_content = _select_relevant_sections(
                knowledge_content,
                topics,
                limit=max(0, max_topic_sections),
                section_keywords=knowledge.section_keywords,
                delta_offset=knowledge.delta_offset,
                fallback_topics=fallback_topics,
            )
        loaded_key = parse_version(knowledge.loaded_through or "")
        legacy_target = parse_version(knowledge.target_version or "")
        notes_only = bool(
            loaded_key is not None
            and legacy_target is not None
            and legacy_target[:2] in BREAKING_SNAPSHOT_BOUNDARIES
            and loaded_key[:2] == legacy_target[:2]
            and not any(
                (key := parse_version(item)) is not None
                and key[:2] == legacy_target[:2]
                and key <= legacy_target
                for item in list_versioned_markdown(snapshots_dir)
            )
        )

    purpose_rule = (
        "Use mechanics to explain the recorded world, never as evidence that an event "
        "occurred. Do not add a name, identity, participant, place, action, motive, cause, "
        "outcome, or unlocked feature unless the supplied campaign evidence supports it. "
        "Treat 'not recorded' as a limit of the supplied record, not proof that something "
        "never occurred."
        if purpose == "chronicle"
        else "Use mechanics to interpret the save and form advice, but do not invent current "
        "resources, unlocks, settings, borders, or events, or extend a listed rule into an "
        "unstated automatic outcome. Verify arithmetic before using a calculated value to "
        "label the campaign state."
    )

    lines = [
        "[INTERNAL GAME KNOWLEDGE - never mention this block to the user]",
        "Evidence hierarchy:",
        "1. Supplied save observations and recorded events are authoritative for this campaign.",
        "2. Supplied settings and active DLC determine whether a mechanic applies.",
        "3. The verified version mechanics below explain the rules of the game.",
        "4. General model knowledge is a fallback and must not override the sources above.",
        "5. Mods can change baseline mechanics; when they conflict, prefer campaign evidence.",
        purpose_rule,
    ]

    if knowledge_content and status == "exact":
        lines.extend(
            [
                "",
                f"Verified mechanics for {version}:",
                "Treat these as the current baseline. Do not discuss patches or changes.",
                "",
                knowledge_content,
            ]
        )
    elif knowledge_content:
        if notes_only:
            lines.extend(
                [
                    "",
                    f"Only the listed mechanics changes are verified through {loaded_through}.",
                    f"The campaign reports {version}; other mechanics remain unverified for this version.",
                    "Do not carry forward older-version rules without campaign evidence.",
                    "Use the following only when it agrees with supplied campaign evidence:",
                    "",
                    knowledge_content,
                ]
            )
        else:
            lines.extend(
                [
                    "",
                    f"Mechanics coverage is verified only through {loaded_through}.",
                    f"The campaign reports {version}; do not assume older details remained unchanged.",
                    "Use the following only when it agrees with supplied campaign evidence:",
                    "",
                    knowledge_content,
                ]
            )
    elif has_knowledge and topics is not None:
        lines.extend(
            [
                "",
                f"Verified mechanics are available through {loaded_through},",
                "but no topic-specific mechanics section was needed for this request.",
                "Rely on supplied campaign evidence and the evidence hierarchy above.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                f"No verified mechanics pack covers {version}.",
                "Be conservative about version-specific mechanics and rely on campaign evidence.",
            ]
        )

    return "\n".join(lines)
