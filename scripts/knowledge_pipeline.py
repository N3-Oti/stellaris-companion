"""Propose mechanics knowledge-graph updates from stable Stellaris release notes.

Commands:
    check   List stable releases on the Steam news feed that the graph has not reviewed.
    update  Draft graph changes for one release with any supported model provider.

The model only proposes facts. Each proposal must quote its source sentence, which is
checked against the fetched notes before anything is written. Proposed facts never
raise ``verified_through``; a maintainer does that after checking the shipped game.
See docs/knowledge-graph.md.

Provider settings come from the environment, so no provider is fixed:
    KNOWLEDGE_PROVIDER   gemini, openrouter, custom, ollama, or lm_studio (default: custom)
    KNOWLEDGE_MODEL      model ID for that provider
    KNOWLEDGE_BASE_URL   OpenAI-compatible base URL (custom/ollama/lm_studio)
    KNOWLEDGE_API_KEY    API key for the provider
In GitHub Actions the workflow defaults to GitHub Models with the job's GITHUB_TOKEN.

Examples:
    python scripts/knowledge_pipeline.py check
    KNOWLEDGE_PROVIDER=gemini KNOWLEDGE_API_KEY=... \\
        python scripts/knowledge_pipeline.py update --version 4.5.2 --summary summary.md
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stellaris_companion.game_knowledge import parse_version  # noqa: E402
from stellaris_companion.knowledge_graph import (  # noqa: E402
    DEFAULT_KNOWLEDGE_DIR,
    KnowledgeGraph,
    load_knowledge_graph,
)

STEAM_APP_ID = 281990
STEAM_NEWS_URL = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
PLAYER_LOCALES = ("en", "ja", "zh-Hans", "de", "fr", "es", "pt-BR")
DEFAULT_CHUNK_CHARS = 12000
MIN_QUOTE_CHARS = 20

_TITLE_VERSION_PATTERN = re.compile(r"(?<![\d.])(\d+\.\d+(?:\.\d+)?)(?![\d.])")
_RELEASE_WORDS = re.compile(r"\b(release[ds]?|update|patch|hotfix|notes)\b", re.IGNORECASE)
_BETA_WORDS = re.compile(r"\b(beta|preview|preliminary)\b", re.IGNORECASE)
# Model-facing facts are present tense; change history confuses models and players.
_HISTORY_WORDS = re.compile(
    r"\b(now|anymore|used to|no longer|previously|formerly|was changed|were changed|"
    r"has been|have been|changed|increased|decreased|reduced|patch(?:es|ed)?|"
    r"hotfix(?:es)?)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ReleaseNote:
    version: str
    title: str
    url: str
    text: str


class ProposedFact(BaseModel):
    quote: str = Field(description="Exact sentence copied from the release notes.")
    note: str = Field(description="Existing note title, or the title of a new note.")
    new_note: bool = Field(description="True only when no existing note fits.")
    label: str = Field(description="Short bold label, 1-5 words.")
    fact: str = Field(description="Present-tense mechanic, without the label.")
    supersedes_label: str | None = Field(
        default=None, description="Label of the existing fact in the note this replaces."
    )
    related: list[str] = Field(
        default_factory=list, description="For new notes: related existing note titles."
    )


class ReleaseAnalysis(BaseModel):
    facts: list[ProposedFact]


class NoteTerms(BaseModel):
    en: list[str]
    ja: list[str]
    zh_hans: list[str]
    de: list[str]
    fr: list[str]
    es: list[str]
    pt_br: list[str]

    def by_locale(self) -> dict[str, list[str]]:
        values = self.model_dump()
        return {locale: values[locale.lower().replace("-", "_")] for locale in PLAYER_LOCALES}


@dataclass
class Review:
    accepted: list[ProposedFact] = field(default_factory=list)
    rejected: list[tuple[ProposedFact, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# --- Release notes ---------------------------------------------------------


def clean_bbcode(text: str) -> str:
    """Convert Steam announcement BBCode into plain Markdown-like text."""
    text = re.sub(r"\{STEAM_CLAN_IMAGE\}\S*", "", text)
    text = re.sub(r"\[url=[^\]]*\](.*?)\[/url\]", r"\1", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"\[h[1-6]\](.*?)\[/h[1-6]\]", r"\n\n\1\n", text, flags=re.IGNORECASE)
    text = re.sub(r"\[\*\]", "\n- ", text)
    text = re.sub(r"\[/?[a-z0-9]+(?:=[^\]]*)?\]", "", text, flags=re.IGNORECASE)
    text = html.unescape(text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def find_stable_releases(items: list[dict[str, Any]]) -> list[ReleaseNote]:
    """Pick stable release announcements from Steam news items, oldest first."""
    releases: dict[tuple[int, int, int], ReleaseNote] = {}
    for item in sorted(items, key=lambda entry: entry.get("date", 0)):
        title = str(item.get("title") or "")
        match = _TITLE_VERSION_PATTERN.search(title)
        if not match or _BETA_WORDS.search(title) or not _RELEASE_WORDS.search(title):
            continue
        key = parse_version(match.group(1))
        if key is None or key in releases:
            continue
        releases[key] = ReleaseNote(
            version=match.group(1),
            title=title,
            url=str(item.get("url") or ""),
            text=clean_bbcode(str(item.get("contents") or "")),
        )
    return [releases[key] for key in sorted(releases)]


def fetch_news(count: int = 100) -> list[dict[str, Any]]:
    import httpx

    response = httpx.get(
        STEAM_NEWS_URL,
        params={
            "appid": STEAM_APP_ID,
            "count": count,
            "maxlength": 0,
            "feeds": "steam_community_announcements",
            "format": "json",
        },
        timeout=30,
    )
    response.raise_for_status()
    return list(response.json().get("appnews", {}).get("newsitems", []))


def load_news(news_file: Path | None) -> list[dict[str, Any]]:
    if news_file is None:
        return fetch_news()
    data = json.loads(news_file.read_text(encoding="utf-8"))
    return list(data.get("appnews", {}).get("newsitems", data if isinstance(data, list) else []))


def known_versions(graph: KnowledgeGraph) -> set[tuple[int, int, int]]:
    versions = set(graph.reviewed_releases)
    for note in graph.notes.values():
        if note.verified_through:
            versions.add(note.verified_through)
        versions.update(fact.since for fact in note.facts if fact.since)
    return versions


def unreviewed_releases(releases: list[ReleaseNote], graph: KnowledgeGraph) -> list[ReleaseNote]:
    known = known_versions(graph)
    minimum = graph.min_version or (0, 0, 0)
    return [
        release
        for release in releases
        if (key := parse_version(release.version)) is not None
        and key >= minimum
        and key not in known
    ]


def split_chunks(text: str, max_chars: int = DEFAULT_CHUNK_CHARS) -> list[str]:
    """Split on blank lines so each model request stays within small free-tier limits."""
    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        while len(paragraph) > max_chars:
            chunks.extend([current] if current else [])
            current = ""
            chunks.append(paragraph[:max_chars])
            paragraph = paragraph[max_chars:]
        if current and len(current) + len(paragraph) + 2 > max_chars:
            chunks.append(current)
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}" if current else paragraph
    if current.strip():
        chunks.append(current)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


# --- Model requests --------------------------------------------------------


def note_catalog(graph: KnowledgeGraph) -> str:
    lines = []
    for note in sorted(graph.notes.values(), key=lambda item: item.title):
        current = [fact.label for fact in note.facts if fact.until is None and fact.label]
        lines.append(f"- {note.title}: {', '.join(current) or '(no labeled facts)'}")
    return "\n".join(lines)


ANALYSIS_SYSTEM_PROMPT = """You maintain a knowledge base of Stellaris game mechanics used to
correct AI advisors whose training data describes older game versions.

From the release-note excerpt, extract only changes that alter strategic advice:
- Include system-level rules, costs, requirements, and numbers players plan around.
- Skip bug fixes, crash or performance fixes, UI and tooltip changes, localisation,
  modding fields, achievements, and cosmetic content.
Write each fact as a present-tense statement of how the game works now. Never use change
history ("now", "no longer", "used to", "was changed", "increased", "patch").
Copy one supporting sentence verbatim from the excerpt into "quote".
Put each fact in the best existing note from the catalog. Set new_note only when no note
fits. When a fact replaces an existing labeled fact, give that label in supersedes_label.
Return an empty list when nothing qualifies."""


TERMS_SYSTEM_PROMPT = """List words Stellaris players use for a game concept, as they would
type them in questions. Use the official in-game terminology of each language when known,
plus common player variants. 3-8 short terms per language; avoid generic words."""


def _parse_json(text: str, model: type[BaseModel]) -> BaseModel:
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()
    return model.model_validate_json(cleaned)


def create_generator() -> Any:
    from backend.core.advisor_providers import (
        ADVISOR_PROVIDER_GEMINI,
        AdvisorProviderConfig,
        create_advisor_generator,
    )

    config = AdvisorProviderConfig.from_environment(
        provider=os.environ.get("KNOWLEDGE_PROVIDER") or "custom",
        model=os.environ.get("KNOWLEDGE_MODEL"),
        base_url=os.environ.get("KNOWLEDGE_BASE_URL"),
        advisor_api_key=os.environ.get("KNOWLEDGE_API_KEY"),
        google_api_key=os.environ.get("KNOWLEDGE_API_KEY"),
    )
    gemini_client = None
    if config.provider == ADVISOR_PROVIDER_GEMINI:
        from google import genai

        gemini_client = genai.Client(api_key=config.api_key)
    generator = create_advisor_generator(config=config, gemini_client=gemini_client)
    if generator is None:
        raise SystemExit(
            "Model provider is not configured. Set KNOWLEDGE_PROVIDER, KNOWLEDGE_MODEL, "
            "KNOWLEDGE_BASE_URL, and KNOWLEDGE_API_KEY as needed."
        )
    return generator


def request_json(generator: Any, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
    result = generator.generate(
        system_prompt=system,
        user_prompt=user,
        temperature=0.2,
        max_output_tokens=4096,
        response_schema=schema,
        schema_name=schema.__name__,
    )
    return _parse_json(result.text, schema)


def propose_facts(
    generator: Any, release: ReleaseNote, graph: KnowledgeGraph, *, chunk_chars: int
) -> tuple[list[ProposedFact], list[str]]:
    proposals: list[ProposedFact] = []
    problems: list[str] = []
    catalog = note_catalog(graph)
    chunks = split_chunks(release.text, chunk_chars)
    for index, chunk in enumerate(chunks, start=1):
        user = (
            f"Release: Stellaris {release.version} ({release.title})\n"
            f"Excerpt {index} of {len(chunks)}:\n{chunk}\n\n"
            f"Existing notes and their current fact labels:\n{catalog}"
        )
        try:
            analysis = request_json(generator, ANALYSIS_SYSTEM_PROMPT, user, ReleaseAnalysis)
        except (ValidationError, ValueError) as error:
            problems.append(f"Excerpt {index}: unreadable model response ({error})")
            continue
        proposals.extend(analysis.facts)  # type: ignore[attr-defined]
    return proposals, problems


def request_terms(generator: Any, title: str, facts: list[ProposedFact]) -> dict[str, list[str]]:
    summary = "\n".join(f"- {fact.label}: {fact.fact}" for fact in facts)
    terms = request_json(
        generator, TERMS_SYSTEM_PROMPT, f"Concept: {title}\nFacts:\n{summary}", NoteTerms
    )
    return terms.by_locale()  # type: ignore[attr-defined]


# --- Validation and edits --------------------------------------------------


def _normalize(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"')
    text = text.replace("”", '"').replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip().lower()


def _note_key(title: str) -> str:
    return re.sub(r"[^0-9a-z]+", "-", title.strip().lower()).strip("-")


def review_proposals(
    proposals: list[ProposedFact], release_text: str, graph: KnowledgeGraph
) -> Review:
    """Keep proposals that quote the source, read as current mechanics, and fit the graph."""
    review = Review()
    source = _normalize(release_text)
    seen: set[tuple[str, str]] = set()
    for proposal in proposals:
        label = proposal.label.strip().rstrip(":")
        fact = " ".join(proposal.fact.split())
        key = _note_key(proposal.note)
        note = graph.notes.get(key)
        reason = None
        if (
            len(proposal.quote.strip()) < MIN_QUOTE_CHARS
            or _normalize(proposal.quote) not in source
        ):
            reason = "quote not found in the release notes"
        elif not label or len(label) > 60 or not fact:
            reason = "missing or overlong label or fact"
        elif _HISTORY_WORDS.search(f"{label} {fact}"):
            reason = "uses change-history wording"
        elif note is None and not proposal.new_note:
            reason = f"unknown note '{proposal.note}'"
        elif (key, label.lower()) in seen:
            reason = "duplicate label in this release"
        elif proposal.supersedes_label and (
            note is None
            or not any(
                existing.label == proposal.supersedes_label and existing.until is None
                for existing in note.facts
            )
        ):
            reason = f"fact to supersede '{proposal.supersedes_label}' not found"
        if reason:
            review.rejected.append((proposal, reason))
            continue
        seen.add((key, label.lower()))
        review.accepted.append(
            proposal.model_copy(update={"label": label, "fact": fact, "new_note": note is None})
        )
    return review


def _close_fact(text: str, label: str, version: str) -> tuple[str, bool]:
    lines = text.split("\n")
    for start, line in enumerate(lines):
        if not re.match(rf"^[-*] \*\*{re.escape(label)}:?\*\*", line):
            continue
        for index in range(start, len(lines)):
            if index > start and (not lines[index].strip() or lines[index].startswith(("-", "*"))):
                break
            match = re.search(r"\{since: ([0-9.]+)\}\s*$", lines[index])
            if match:
                lines[index] = (
                    lines[index][: match.start()] + f"{{since: {match.group(1)}, until: {version}}}"
                )
                return "\n".join(lines), True
    return text, False


def _insert_fact(text: str, bullet: str) -> str:
    related = re.search(r"(?m)^Related:", text)
    if related:
        return f"{text[: related.start()]}{bullet}\n\n{text[related.start() :]}"
    return f"{text.rstrip()}\n\n{bullet}\n"


def _new_note_text(
    title: str, terms: dict[str, list[str]], related: list[str], release: ReleaseNote
) -> str:
    front = ["---", "terms:"]
    front += [f"  {locale}: [{', '.join(terms[locale])}]" for locale in PLAYER_LOCALES]
    front.append("---")
    body = [
        f"# {title}",
        "",
        f"<!-- Sources: Stellaris {release.version} release notes {release.url} -->",
    ]
    text = "\n".join(front + body) + "\n"
    if related:
        text += "\nRelated: " + ", ".join(f"[[{item}]]" for item in related) + "\n"
    return text


def apply_review(
    review: Review,
    release: ReleaseNote,
    graph: KnowledgeGraph,
    knowledge_dir: Path,
    *,
    terms_for: Any,
) -> list[str]:
    """Write accepted facts into notes and return the changed note titles."""
    concepts = knowledge_dir / "concepts"
    changed: list[str] = []
    new_notes: dict[str, list[ProposedFact]] = {}
    for proposal in review.accepted:
        if proposal.new_note:
            new_notes.setdefault(proposal.note.strip(), []).append(proposal)

    for title, facts in new_notes.items():
        try:
            terms = terms_for(title, facts)
        except (ValidationError, ValueError) as error:
            terms = {}
            review.notes.append(f"Terms for new note '{title}' failed: {error}")
        if any(not terms.get(locale) for locale in PLAYER_LOCALES):
            for fact in facts:
                review.accepted.remove(fact)
                review.rejected.append((fact, "new note lacks terms for every locale"))
            continue
        related = sorted(
            {
                graph.notes[_note_key(item)].title
                for fact in facts
                for item in fact.related
                if _note_key(item) in graph.notes
            }
        )
        (concepts / f"{_note_key(title)}.md").write_text(
            _new_note_text(title, terms, related, release), encoding="utf-8"
        )

    for proposal in review.accepted:
        path = concepts / f"{_note_key(proposal.note)}.md"
        text = path.read_text(encoding="utf-8")
        note = graph.notes.get(_note_key(proposal.note))
        to_close = proposal.supersedes_label
        if (
            not to_close
            and note
            and any(
                existing.label == proposal.label and existing.until is None
                for existing in note.facts
            )
        ):
            to_close = proposal.label
            review.notes.append(
                f"'{proposal.label}' in {note.title} was closed because the new fact reuses its label."
            )
        if to_close:
            text, closed = _close_fact(text, to_close, release.version)
            if not closed:
                review.notes.append(
                    f"Could not close '{to_close}' in {proposal.note}; check by hand."
                )
        bullet = f"- **{proposal.label}:** {proposal.fact} {{since: {release.version}}}"
        path.write_text(_insert_fact(text, bullet), encoding="utf-8")
        title = note.title if note else proposal.note.strip()
        if title not in changed:
            changed.append(title)
    return changed


def record_reviewed_release(knowledge_dir: Path, version: str) -> None:
    path = knowledge_dir / "_manifest.md"
    text = path.read_text(encoding="utf-8")
    match = re.search(r"(?m)^reviewed_releases: \[(.*)\]$", text)
    if match:
        versions = [item.strip() for item in match.group(1).split(",") if item.strip()]
        if version not in versions:
            versions.append(version)
        text = (
            text[: match.start()]
            + f"reviewed_releases: [{', '.join(versions)}]"
            + text[match.end() :]
        )
    else:
        text = text.replace("\n---\n", f"\nreviewed_releases: [{version}]\n---\n", 1)
    path.write_text(text, encoding="utf-8")


def integrity_problems(graph: KnowledgeGraph) -> list[str]:
    problems = []
    for note in graph.notes.values():
        if not note.facts:
            problems.append(f"{note.title}: no facts")
        problems.extend(
            f"{note.title}: broken link [[{link}]]"
            for link in note.links
            if not graph.resolve_link(link)
        )
        missing = [locale for locale in PLAYER_LOCALES if not note.terms.get(locale)]
        if missing:
            problems.append(f"{note.title}: no terms for {', '.join(missing)}")
        problems.extend(
            f"{note.title}: fact without since" for fact in note.facts if fact.since is None
        )
    return problems


def render_summary(
    release: ReleaseNote,
    review: Review,
    changed: list[str],
    problems: list[str],
    graph: KnowledgeGraph,
) -> str:
    lines = [
        f"## Mechanics knowledge update: Stellaris {release.version}",
        "",
        f"Source: [{release.title}]({release.url})",
        "",
        "Drafted by `scripts/knowledge_pipeline.py`. Every accepted fact quotes a sentence that",
        "was found in the release notes. `verified_through` was not raised, so these facts are",
        "served as partial coverage until someone checks them against the shipped game.",
        "",
        "### Review checklist",
        "- [ ] Each fact is correct, present tense, and placed in the right note.",
        "- [ ] Closed facts (`until`) are really superseded.",
        "- [ ] New notes have accurate terms in every language.",
    ]
    key = parse_version(release.version)
    newest = graph.newest_line()
    if key is not None and newest is not None and key[:2] > newest:
        lines.append(
            f"- [ ] {key[0]}.{key[1]} is a new release line: decide whether it redesigns "
            "mechanics enough to add it to `breaking_lines` in `_manifest.md`."
        )
    lines += ["", f"### Changed notes ({len(changed)})"]
    lines += [f"- {title}" for title in changed] or ["- None"]
    if review.accepted:
        lines += ["", "### Accepted facts"]
        for proposal in review.accepted:
            replaced = (
                f" (replaces '{proposal.supersedes_label}')" if proposal.supersedes_label else ""
            )
            lines.append(f"- **{proposal.note}** / {proposal.label}{replaced}")
            lines.append(f'  - Quote: "{proposal.quote.strip()}"')
    if review.rejected:
        lines += ["", f"### Rejected proposals ({len(review.rejected)})"]
        lines += [
            f"- {proposal.note} / {proposal.label}: {reason}"
            for proposal, reason in review.rejected
        ]
    if review.notes or problems:
        lines += ["", "### Needs attention"]
        lines += [f"- {item}" for item in [*review.notes, *problems]]
    return "\n".join(lines) + "\n"


# --- Commands --------------------------------------------------------------


def _write_github_output(path: str | None, values: dict[str, str]) -> None:
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def command_check(args: argparse.Namespace) -> int:
    graph = load_knowledge_graph(args.knowledge_dir)
    if graph is None:
        raise SystemExit(f"No knowledge graph at {args.knowledge_dir}")
    pending = unreviewed_releases(find_stable_releases(load_news(args.news_file)), graph)
    for release in pending:
        print(f"{release.version}\t{release.title}\t{release.url}")
    if not pending:
        print("No unreviewed stable releases.")
    _write_github_output(args.github_output, {"version": pending[0].version if pending else ""})
    return 0


def command_update(args: argparse.Namespace) -> int:
    knowledge_dir: Path = args.knowledge_dir
    graph = load_knowledge_graph(knowledge_dir)
    if graph is None:
        raise SystemExit(f"No knowledge graph at {knowledge_dir}")
    releases = unreviewed_releases(find_stable_releases(load_news(args.news_file)), graph)
    if args.version:
        releases = [release for release in releases if release.version == args.version]
    if not releases:
        print("No matching unreviewed stable release.")
        return 0
    release = releases[0]
    generator = create_generator()
    try:
        proposals, problems = propose_facts(generator, release, graph, chunk_chars=args.chunk_chars)
        review = review_proposals(proposals, release.text, graph)
        if args.dry_run:
            changed = sorted({proposal.note for proposal in review.accepted})
        else:
            changed = apply_review(
                review,
                release,
                graph,
                knowledge_dir,
                terms_for=lambda title, facts: request_terms(generator, title, facts),
            )
            record_reviewed_release(knowledge_dir, release.version)
            load_knowledge_graph.cache_clear()
            updated = load_knowledge_graph(knowledge_dir)
            problems += integrity_problems(updated) if updated else ["Graph failed to load"]
    finally:
        generator.close()
    summary = render_summary(release, review, changed, problems, graph)
    if args.summary:
        args.summary.write_text(summary, encoding="utf-8")
    print(summary)
    return 1 if problems and not args.dry_run else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--knowledge-dir", type=Path, default=DEFAULT_KNOWLEDGE_DIR)
    parser.add_argument(
        "--news-file", type=Path, help="Saved Steam news JSON instead of fetching the feed."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="List unreviewed stable releases.")
    check.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    check.set_defaults(handler=command_check)
    update = commands.add_parser("update", help="Draft graph changes for one release.")
    update.add_argument("--version", help="Release version to process (default: oldest pending).")
    update.add_argument("--summary", type=Path, help="Write the review summary to this file.")
    update.add_argument("--chunk-chars", type=int, default=DEFAULT_CHUNK_CHARS)
    update.add_argument("--dry-run", action="store_true", help="Propose without writing files.")
    update.set_defaults(handler=command_update)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
