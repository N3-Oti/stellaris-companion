import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import knowledge_pipeline as pipeline
from stellaris_companion.knowledge_graph import (
    DEFAULT_KNOWLEDGE_DIR,
    load_knowledge_graph,
    resolve_graph_knowledge,
)

RELEASE_TEXT = (
    "[h2]Economy[/h2][list][*]Branch Offices now cost 100 Influence plus 5 Influence per jump."
    "[*]Fixed a crash when opening the market.[/list]"
    "[h2]Megastructures[/h2][list][*]The Quantum Forge converts 10 Alloys into 1 Dark Matter "
    "each month.[/list]"
)

# Titles as published on the Stellaris Steam announcements feed.
REAL_TITLES = {
    'Stellaris 4.5 "Cygnus" now available!': "4.5",
    "Stellaris 4.5.1 released (checksum 358e)": "4.5.1",
    "Stellaris 4.5.2 released [checksum 9776]": "4.5.2",
    "Stellaris 4.4.6 hotfix released (fdde)": "4.4.6",
    "Stellaris 4.4.5 patch released (2f57)": "4.4.5",
    "Stellaris 4.3.6 patch released (checksum 6ccb)": "4.3.6",
    "Stellaris 4.0.10 Patch": "4.0.10",
    'Stellaris 4.4.4 "Pegasus" Open Beta (3bc0) now available!': None,
    'Stellaris 4.4.5 "Pegasus" Early Open Beta (c22e) now available!': None,
    "Stellaris 4.5 'Cygnus' Open Beta Update 4 (e6fd)": None,
    "Stellaris Dev Diary #433 - 4.5 'Cygnus' Preliminary Release Notes": None,
    "Stellaris Dev Diary #427 - We've Had One, Yes. But What About Second Open Beta?": None,
    "Willpower and the Stellaris 4.6 'Corona Borealis' update will be released on Monday": None,
}

NEWS = {
    "appnews": {
        "newsitems": [
            {
                "title": "Stellaris 4.5.2 released [checksum 9776]",
                "url": "https://x/452",
                "contents": RELEASE_TEXT,
                "date": 30,
            },
            {
                "title": 'Stellaris 4.6 "Corona Borealis" Open Beta (abcd) now available!',
                "url": "https://x/beta",
                "contents": "",
                "date": 31,
            },
            {
                "title": "Stellaris 4.5.1 released (checksum 358e)",
                "url": "https://x/451",
                "contents": "",
                "date": 20,
            },
            {
                "title": "Stellaris 4.3.6 patch released (checksum 6ccb)",
                "url": "https://x/436",
                "contents": "",
                "date": 10,
            },
            {
                "title": "Stellaris Dev Diary #436 - Ideologies",
                "url": "https://x/dd",
                "contents": "",
                "date": 32,
            },
        ]
    }
}


class FakeGenerator:
    def __init__(self, responses: list[dict]):
        self.responses = list(responses)
        self.calls: list[str] = []

    def generate(self, *, system_prompt: str, user_prompt: str, **_: object):
        self.calls.append(user_prompt)
        return SimpleNamespace(text=json.dumps(self.responses.pop(0)))

    def close(self) -> None:
        pass


def _proposal(**overrides: object) -> dict:
    base = {
        "quote": "Branch Offices now cost 100 Influence plus 5 Influence per jump.",
        "note": "Branch Offices",
        "new_note": False,
        "label": "Branch Offices",
        "fact": "Building a Branch Office costs 100 Influence plus 5 Influence per jump.",
        "supersedes_label": None,
        "related": [],
    }
    return {**base, **overrides}


TERMS = {
    "en": ["quantum forge"],
    "ja": ["量子炉"],
    "zh_hans": ["量子熔炉"],
    "de": ["Quantenschmiede"],
    "fr": ["forge quantique"],
    "es": ["forja cuántica"],
    "pt_br": ["forja quântica"],
}


@pytest.fixture
def knowledge_copy(tmp_path: Path) -> Path:
    target = tmp_path / "knowledge"
    shutil.copytree(DEFAULT_KNOWLEDGE_DIR, target)
    load_knowledge_graph.cache_clear()
    yield target
    load_knowledge_graph.cache_clear()


def test_clean_bbcode_keeps_readable_lists_and_headings():
    text = pipeline.clean_bbcode(RELEASE_TEXT)

    assert "Economy" in text
    assert "- Branch Offices now cost 100 Influence plus 5 Influence per jump." in text
    assert "[" not in text


@pytest.mark.parametrize(("title", "version"), REAL_TITLES.items())
def test_recognizes_published_stable_titles_only(title: str, version: str | None):
    releases = pipeline.find_stable_releases([{"title": title, "contents": "", "date": 1}])

    assert [release.version for release in releases] == ([version] if version else [])


def test_finds_stable_releases_oldest_first():
    releases = pipeline.find_stable_releases(NEWS["appnews"]["newsitems"])

    assert [release.version for release in releases] == ["4.3.6", "4.5.1", "4.5.2"]


@pytest.mark.parametrize(
    ("environment", "message"),
    [
        ({}, "Set KNOWLEDGE_PROVIDER"),
        ({"KNOWLEDGE_PROVIDER": "github_models"}, "Set KNOWLEDGE_PROVIDER"),
        ({"KNOWLEDGE_PROVIDER": "openrouter"}, "Set KNOWLEDGE_MODEL"),
    ],
)
def test_generator_requires_an_explicit_provider_and_model(monkeypatch, environment, message):
    for name in (
        "KNOWLEDGE_PROVIDER",
        "KNOWLEDGE_MODEL",
        "KNOWLEDGE_BASE_URL",
        "KNOWLEDGE_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(SystemExit, match=message):
        pipeline.create_generator()


def test_gemini_defaults_to_the_advisor_model(monkeypatch):
    from backend.core.model_routing import GEMINI_FLASH_MODEL

    monkeypatch.setenv("KNOWLEDGE_PROVIDER", "gemini")
    monkeypatch.delenv("KNOWLEDGE_MODEL", raising=False)
    monkeypatch.setenv("KNOWLEDGE_API_KEY", "test-key")

    generator = pipeline.create_generator()

    assert generator.config.model == GEMINI_FLASH_MODEL


def test_unreviewed_releases_skip_known_and_pre_graph_versions():
    graph = load_knowledge_graph(DEFAULT_KNOWLEDGE_DIR)
    releases = pipeline.find_stable_releases(NEWS["appnews"]["newsitems"])

    assert [release.version for release in pipeline.unreviewed_releases(releases, graph)] == [
        "4.5.2"
    ]


def test_split_chunks_respects_size_limit():
    text = "\n\n".join(["a" * 40] * 10 + ["b" * 130])

    chunks = pipeline.split_chunks(text, 100)

    assert all(len(chunk) <= 100 for chunk in chunks)
    assert "".join(chunks).replace("\n", "") == text.replace("\n", "")


def test_review_rejects_unquoted_historical_and_misplaced_facts():
    graph = load_knowledge_graph(DEFAULT_KNOWLEDGE_DIR)
    source = pipeline.clean_bbcode(RELEASE_TEXT)
    proposals = [
        pipeline.ProposedFact(**_proposal()),
        pipeline.ProposedFact(**_proposal(quote="Branch Offices are free for everyone forever.")),
        pipeline.ProposedFact(
            **_proposal(label="Office Cost", fact="Branch Offices now cost more.")
        ),
        pipeline.ProposedFact(**_proposal(note="Imaginary Note", label="Other")),
        pipeline.ProposedFact(**_proposal(label="Third", supersedes_label="Missing Label")),
    ]

    review = pipeline.review_proposals(proposals, source, graph)

    assert [proposal.label for proposal in review.accepted] == ["Branch Offices"]
    assert [reason for _, reason in review.rejected] == [
        "quote not found in the release notes",
        "uses change-history wording",
        "unknown note 'Imaginary Note'",
        "fact to supersede 'Missing Label' not found",
    ]


def test_update_writes_reviewable_graph_changes(knowledge_copy: Path, tmp_path: Path, monkeypatch):
    news_file = tmp_path / "news.json"
    news_file.write_text(json.dumps(NEWS), encoding="utf-8")
    forge = _proposal(
        quote="The Quantum Forge converts 10 Alloys into 1 Dark Matter each month.",
        note="Quantum Forge",
        new_note=True,
        label="Quantum Forge",
        fact="The Quantum Forge converts 10 Alloys into 1 Dark Matter each month.",
        related=["Districts & Buildings", "Not A Note"],
    )
    generator = FakeGenerator([{"facts": [_proposal(), forge]}, TERMS])
    monkeypatch.setattr(pipeline, "create_generator", lambda: generator)
    summary = tmp_path / "summary.md"

    code = pipeline.main(
        [
            "--knowledge-dir",
            str(knowledge_copy),
            "--news-file",
            str(news_file),
            "update",
            "--summary",
            str(summary),
        ]
    )

    assert code == 0
    branch_offices = (knowledge_copy / "concepts" / "branch-offices.md").read_text(encoding="utf-8")
    assert "{since: 4.5, until: 4.5.2}" in branch_offices
    assert "costs 100 Influence plus 5 Influence per jump. {since: 4.5.2}" in branch_offices
    assert branch_offices.index("{since: 4.5.2}") < branch_offices.index("Related:")
    forge_note = (knowledge_copy / "concepts" / "quantum-forge.md").read_text(encoding="utf-8")
    assert "ja: [量子炉]" in forge_note
    assert "Related: [[Districts & Buildings]]" in forge_note
    assert "reviewed_releases: [4.4.6, 4.5, 4.5.1, 4.5.2]" in (
        knowledge_copy / "_manifest.md"
    ).read_text(encoding="utf-8")
    assert "Fixed a crash" not in branch_offices
    report = summary.read_text(encoding="utf-8")
    assert "Mechanics knowledge update: Stellaris 4.5.2" in report
    assert "verified_through` was not raised" in report
    assert "points to the Paradox forum" in report

    load_knowledge_graph.cache_clear()
    graph = load_knowledge_graph(knowledge_copy)
    resolved = resolve_graph_knowledge(graph, (4, 5, 2), topics="支社のコストは？")
    assert "costs 100 Influence" in (resolved.content or "")
    assert "costs 75 Influence" not in (resolved.content or "")
    older = resolve_graph_knowledge(graph, (4, 5, 1), topics="支社のコストは？")
    assert "costs 75 Influence" in (older.content or "")
    assert pipeline.integrity_problems(graph) == []


def test_reviewed_release_is_not_proposed_again(knowledge_copy: Path, tmp_path: Path):
    news_file = tmp_path / "news.json"
    news_file.write_text(json.dumps(NEWS), encoding="utf-8")
    pipeline.record_reviewed_release(knowledge_copy, "4.5.2")
    load_knowledge_graph.cache_clear()
    output = tmp_path / "github_output"

    pipeline.main(
        [
            "--knowledge-dir",
            str(knowledge_copy),
            "--news-file",
            str(news_file),
            "check",
            "--github-output",
            str(output),
        ]
    )

    assert output.read_text(encoding="utf-8") == "version=\n"
