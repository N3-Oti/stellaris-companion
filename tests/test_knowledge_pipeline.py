import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import knowledge_pipeline as pipeline
from stellaris_companion.knowledge_graph import (
    load_knowledge_graph,
    resolve_graph_knowledge,
)

# A frozen 4.5.1-era subset, so these tests hold after the shipped graph learns 4.5.2.
FIXTURE_GRAPH = Path(__file__).parent / "fixtures" / "knowledge_graph"

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
    "Stellaris 4.3 'Cetus' is now available!": "4.3",
    "Stellaris 4.3.1 hotfix release (checksum f646)": "4.3.1",
    "Stellaris 4.3.7 hotfix patch released (checksum 4f3c)": "4.3.7",
    "Stellaris Patch 4.2.4 released (checksum 7a03)": "4.2.4",
    "4.2.2 Hotfix now available": "4.2.2",
    "4.1.7 Patch Released (checksum 6486)": "4.1.7",
    "Stellaris Dev Diary #434 - 4.5.2 'Cygnus' Tentative Patch Notes": None,
    "4.3.2 Open Beta is now on stellaris_test [checksum 171a]": None,
    "[Dev Team] stellaris_test updated with 4.4.2 (checksum 38b9)": None,
    "v4.1.7 Open Beta released! (checksum ad13)": None,
    'Stellaris 4.3 "Cetus" Open Beta Updated (2026-03-06)': None,
    "Stellaris: Nomads is available now!": None,
    "Mammalian Science Ship Brickset and Bubbles Cantina Puzzle now available!": None,
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
    shutil.copytree(FIXTURE_GRAPH, target)
    load_knowledge_graph.cache_clear()
    yield target
    load_knowledge_graph.cache_clear()


def test_clean_bbcode_handles_feed_markup():
    raw = (
        '[p][img src="{STEAM_CLAN_IMAGE}/1/a.png"][/img][/p][p]Hello![/p]'
        "[h3][b]4.5.2 Hotfix Release Notes[/b][/h3][list][*][p]Arkships can Detoxify "
        "worlds.[/p][/*][*][p]Fixed a [redacted] bug.\u200b[/p][/*][/list]"
        '[dynamiclink href="https://store.steampowered.com/app/1/"][/dynamiclink]'
    )

    text = pipeline.clean_bbcode(raw)

    assert text == (
        "Hello!\n\n4.5.2 Hotfix Release Notes\n\n- Arkships can Detoxify worlds.\n\n"
        "- Fixed a [redacted] bug."
    )


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
    graph = load_knowledge_graph(FIXTURE_GRAPH)
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
    graph = load_knowledge_graph(FIXTURE_GRAPH)
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

    assert output.read_text(encoding="utf-8") == "version=\nnotice=\n"


# Shape of `steamcmd +app_info_print 281990` (values from the 6 October 2026 public build).
APP_INFO = """
"281990"
{
	"depots"
	{
		"branches"
		{
			"public"
			{
				"buildid"		"25664273"
				"timeupdated"		"1791277234"
				"timebuildupdated"		"1790894566"
			}
			"stellaris_test"
			{
				"buildid"		"25482991"
				"description"		"Open Beta"
				"timeupdated"		"1790176101"
			}
		}
	}
}
"""


def _write_app_info(tmp_path: Path) -> Path:
    path = tmp_path / "app_info.txt"
    path.write_text(APP_INFO, encoding="utf-8")
    return path


def _check(knowledge_dir: Path, tmp_path: Path, news: dict | None) -> dict[str, str]:
    output = tmp_path / "github_output"
    output.write_text("", encoding="utf-8")
    argv = ["--knowledge-dir", str(knowledge_dir), "--app-info", str(_write_app_info(tmp_path))]
    if news is not None:
        news_file = tmp_path / "news.json"
        news_file.write_text(json.dumps(news), encoding="utf-8")
        argv += ["--news-file", str(news_file)]
    pipeline.main([*argv, "check", "--github-output", str(output)])
    lines = output.read_text(encoding="utf-8").splitlines()
    return dict(line.split("=", 1) for line in lines)


def test_parse_public_build_ignores_beta_branches():
    build = pipeline.parse_public_build(APP_INFO)

    assert build == pipeline.PublicBuild(
        "25664273", datetime(2026, 10, 6, 9, 0, 34, tzinfo=timezone.utc)
    )
    assert pipeline.parse_public_build("no branches here") is None


def test_unchanged_public_build_skips_the_news_feed(
    knowledge_copy: Path, tmp_path: Path, monkeypatch
):
    pipeline.record_public_build(knowledge_copy, "25664273")

    def fail(*_: object) -> None:
        raise AssertionError("news must not be fetched")

    monkeypatch.setattr(pipeline, "fetch_news", fail)

    outputs = _check(knowledge_copy, tmp_path, news=None)

    assert outputs == {"version": "", "notice": "", "build_id": "25664273"}


def test_changed_public_build_finds_the_release_post(knowledge_copy: Path, tmp_path: Path):
    outputs = _check(knowledge_copy, tmp_path, NEWS)

    assert outputs["version"] == "4.5.2"
    assert outputs["build_id"] == "25664273"


def test_launch_post_without_version_raises_a_notice(
    knowledge_copy: Path, tmp_path: Path, monkeypatch
):
    went_live = datetime(2026, 10, 6, 9, 0, 34, tzinfo=timezone.utc)
    monkeypatch.setattr(pipeline, "_now", lambda: went_live + timedelta(hours=30))
    launch = {
        "title": "Stellaris: Willpower is available now!",
        "url": "https://x/launch",
        "contents": "",
        "date": int((went_live + timedelta(minutes=20)).timestamp()),
    }

    outputs = _check(knowledge_copy, tmp_path, {"appnews": {"newsitems": [launch]}})

    assert outputs["version"] == ""
    assert "Stellaris: Willpower is available now!" in outputs["notice"]
    assert "release line may have launched" in outputs["notice"]


def test_build_without_any_post_stays_quiet(
    knowledge_copy: Path, tmp_path: Path, monkeypatch, capsys
):
    went_live = datetime(2026, 10, 6, 9, 0, 34, tzinfo=timezone.utc)
    monkeypatch.setattr(pipeline, "_now", lambda: went_live + timedelta(hours=2))

    outputs = _check(knowledge_copy, tmp_path, {"appnews": {"newsitems": []}})

    assert outputs["notice"] == ""
    assert "next run checks again" in capsys.readouterr().out


def test_update_records_the_build_once_nothing_else_is_pending(
    knowledge_copy: Path, tmp_path: Path, monkeypatch
):
    news = {"appnews": {"newsitems": [*NEWS["appnews"]["newsitems"]]}}
    news["appnews"]["newsitems"].append(
        {
            "title": "Stellaris 4.5.3 released [checksum 0000]",
            "url": "https://x/453",
            "contents": RELEASE_TEXT,
            "date": 40,
        }
    )
    news_file = tmp_path / "news.json"
    news_file.write_text(json.dumps(news), encoding="utf-8")
    app_info = _write_app_info(tmp_path)
    monkeypatch.setattr(pipeline, "create_generator", lambda: FakeGenerator([{"facts": []}] * 2))

    def update(version: str) -> None:
        pipeline.main(
            [
                "--knowledge-dir",
                str(knowledge_copy),
                "--news-file",
                str(news_file),
                "--app-info",
                str(app_info),
                "update",
                "--version",
                version,
            ]
        )
        load_knowledge_graph.cache_clear()

    update("4.5.2")
    assert pipeline.recorded_public_build(knowledge_copy) is None
    update("4.5.3")
    assert pipeline.recorded_public_build(knowledge_copy) == "25664273"


def test_provider_failure_is_reported_in_one_line(
    knowledge_copy: Path, tmp_path: Path, monkeypatch, capsys
):
    from backend.core.advisor_providers import AdvisorProviderError

    class BillingFailure(FakeGenerator):
        def generate(self, **_: object):
            raise AdvisorProviderError(
                "402 RESOURCE_EXHAUSTED. Your prepayment credits are depleted.",
                code="ADVISOR_PROVIDER_ERROR",
            )

    news_file = tmp_path / "news.json"
    news_file.write_text(json.dumps(NEWS), encoding="utf-8")
    monkeypatch.setattr(pipeline, "create_generator", lambda: BillingFailure([]))

    code = pipeline.main(
        ["--knowledge-dir", str(knowledge_copy), "--news-file", str(news_file), "update"]
    )

    assert code == 1
    assert "::error title=Model provider::402 RESOURCE_EXHAUSTED" in capsys.readouterr().out
    assert "reviewed_releases: [4.4.6, 4.5, 4.5.1]\n" in (
        knowledge_copy / "_manifest.md"
    ).read_text(encoding="utf-8")


def test_update_pins_the_configured_model_and_reports_it(
    knowledge_copy: Path, tmp_path: Path, monkeypatch
):
    calls: list[str | None] = []

    class ConfiguredGenerator(FakeGenerator):
        config = SimpleNamespace(model="configured-model")

        def generate(self, *, model: str | None = None, **_: object):
            calls.append(model)
            return SimpleNamespace(text=json.dumps({"facts": []}), model="served-model")

    news_file = tmp_path / "news.json"
    news_file.write_text(json.dumps(NEWS), encoding="utf-8")
    summary = tmp_path / "summary.md"
    monkeypatch.setattr(pipeline, "create_generator", lambda: ConfiguredGenerator([]))

    pipeline.main(
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

    assert calls and set(calls) == {"configured-model"}
    assert "Model: served-model" in summary.read_text(encoding="utf-8")
