from pathlib import Path

import pytest

from stellaris_companion.game_knowledge import build_game_knowledge_prompt
from stellaris_companion.knowledge_graph import (
    DEFAULT_KNOWLEDGE_DIR,
    load_knowledge_graph,
    parse_facts,
    parse_front_matter,
    resolve_graph_knowledge,
)

PLAYER_LOCALES = ("en", "ja", "zh-Hans", "de", "fr", "es", "pt-BR")


def _write_graph(root: Path, notes: dict[str, str], *, manifest: str) -> Path:
    directory = root / "knowledge"
    (directory / "concepts").mkdir(parents=True)
    (directory / "_manifest.md").write_text(f"---\n{manifest}\n---\n", encoding="utf-8")
    for name, text in notes.items():
        (directory / "concepts" / f"{name}.md").write_text(text, encoding="utf-8")
    load_knowledge_graph.cache_clear()
    return directory


def _note(title: str, body: str, *, terms: str = "", extra: str = "") -> str:
    return f"---\nterms:\n  ja: [{terms}]\n{extra}---\n# {title}\n\n{body}\n"


SAMPLE_NOTES = {
    "anchorages": _note(
        "Anchorages",
        "- **Old Anchorage:** Old rule. {since: 1.0, until: 1.2}\n"
        "- **Anchorage:** Current rule. {since: 1.2}\n\nRelated: [[Fleet Upkeep]]",
        terms="停泊所",
        extra="verified_through: 1.2.0\n",
    ),
    "fleet-upkeep": _note(
        "Fleet Upkeep",
        "- **Upkeep:** Upkeep rule. {since: 1.0}",
        terms="維持費",
        extra="verified_through: 1.2.0\n",
    ),
    "pop-groups": _note(
        "Pop Groups",
        "- **Pop Groups:** Grouped by faction. {since: 1.0, until: 2.0}\n"
        "- **Pop Group Shares:** Groups track faction shares. {since: 2.0}",
        terms="ポップ",
        extra="verified_through: 1.2.0\n",
    ),
    "baseline": _note(
        "Baseline",
        "- **Base:** Always-on rule. {since: 1.0}",
        extra="verified_through: 1.2.0\nalways: true\n",
    ),
    "guardrails": _note(
        "Guardrails",
        "- **Evidence:** Save evidence first. {since: 1.0}",
        extra="always: true\nversion_independent: true\n",
    ),
}


@pytest.fixture
def sample_graph(tmp_path: Path):
    directory = _write_graph(
        tmp_path, SAMPLE_NOTES, manifest="min_version: 1.0\nbreaking_lines: [2.0]"
    )
    return load_knowledge_graph(directory)


def test_front_matter_supports_nested_lists_and_booleans():
    data, body = parse_front_matter(
        "---\nterms:\n  ja: [市民, 民間人]\n  de: [Zivilisten]\nalways: true\n"
        "verified_through: 4.4.6\n---\n# Title\n"
    )

    assert data["terms"] == {"ja": ("市民", "民間人"), "de": ("Zivilisten",)}
    assert data["always"] is True
    assert data["verified_through"] == "4.4.6"
    assert body == "# Title\n"


def test_facts_parse_bullets_tables_and_metadata():
    facts = parse_facts(
        "<!-- source note -->\n"
        "- **One:** First line\n  continued. {since: 4.0, until: 4.5}\n"
        "- **Two:** Second. {since: 4.4.6}\n\n"
        "| Class | Use |\n| --- | ---: |\n| Corvette | 5 |\n{since: 4.4.6}\n\n"
        "Related: [[Other]]\n"
    )

    assert [fact.text for fact in facts] == [
        "- **One:** First line\ncontinued.",
        "- **Two:** Second.",
        "| Class | Use |\n| --- | ---: |\n| Corvette | 5 |",
    ]
    assert facts[0].since == (4, 0, 0) and facts[0].until == (4, 5, 0)
    assert facts[2].since == (4, 4, 6)
    assert facts[0].label == "One"


def test_invalid_fact_metadata_is_rejected():
    with pytest.raises(ValueError):
        parse_facts("- **Bad:** Rule. {from: 4.0}")


def test_facts_follow_their_version_ranges(sample_graph):
    old = resolve_graph_knowledge(sample_graph, (1, 1, 0))
    current = resolve_graph_knowledge(sample_graph, (1, 2, 0))

    assert "Old rule" in (old.content or "") and "Current rule" not in (old.content or "")
    assert "Current rule" in (current.content or "") and "Old rule" not in (current.content or "")
    assert current.status == "exact"
    assert old.status == "exact"


def test_newer_version_in_same_line_is_partial(sample_graph):
    knowledge = resolve_graph_knowledge(sample_graph, (1, 2, 5))

    assert knowledge.status == "partial"
    assert knowledge.loaded_through == "1.2.0"


def test_breaking_line_drops_unconfirmed_facts_but_keeps_guardrails(sample_graph):
    knowledge = resolve_graph_knowledge(sample_graph, (2, 0, 0))

    assert knowledge.status == "notes_only"
    assert knowledge.loaded_through == "2.0.0"
    assert "Groups track faction shares" in (knowledge.content or "")
    assert "Save evidence first" in (knowledge.content or "")
    assert "Current rule" not in (knowledge.content or "")
    assert "Always-on rule" not in (knowledge.content or "")


def test_unknown_newer_line_receives_nothing(sample_graph):
    knowledge = resolve_graph_knowledge(sample_graph, (3, 0, 0))

    assert knowledge.status == "unsupported_newer"
    assert knowledge.content is None


def test_topic_selection_adds_seed_neighbors_and_always_notes(sample_graph):
    knowledge = resolve_graph_knowledge(sample_graph, (1, 2, 0), topics="停泊所は必要？")

    assert knowledge.matched_topics
    assert "Current rule" in (knowledge.content or "")
    assert "Upkeep rule" in (knowledge.content or "")
    assert "Always-on rule" in (knowledge.content or "")
    assert "Grouped by faction" not in (knowledge.content or "")


def test_unmatched_topic_tries_recent_questions_then_lists_notes(sample_graph):
    follow_up = resolve_graph_knowledge(
        sample_graph, (1, 2, 0), topics="それは？", fallback_topics="ポップについて"
    )
    unmatched = resolve_graph_knowledge(sample_graph, (1, 2, 0), topics="それは？")

    assert "Grouped by faction" in (follow_up.content or "")
    assert not unmatched.matched_topics
    assert "- Anchorages: Anchorage" in (unmatched.content or "")
    assert "Current rule" not in (unmatched.content or "")


def test_unreviewed_deltas_are_always_included(tmp_path: Path):
    notes = dict(SAMPLE_NOTES)
    notes["fleet-upkeep"] = _note(
        "Fleet Upkeep",
        "- **Upkeep:** Upkeep rule. {since: 1.0}\n- **Hotfix:** Hotfix rule. {since: 1.2.1}",
        terms="維持費",
        extra="verified_through: 1.2.0\n",
    )
    directory = _write_graph(tmp_path, notes, manifest="min_version: 1.0\nbreaking_lines: [2.0]")

    knowledge = resolve_graph_knowledge(
        load_knowledge_graph(directory), (1, 2, 1), topics="ポップは？"
    )

    assert knowledge.status == "partial"
    assert knowledge.loaded_through == "1.2.1"
    assert "Hotfix rule" in (knowledge.content or "")
    assert "Upkeep rule" not in (knowledge.content or "")


def test_prompt_uses_legacy_resolver_below_graph_minimum():
    prompt = build_game_knowledge_prompt("Cetus v4.3.5", purpose="advisor")

    assert "Verified mechanics for Cetus v4.3.5" in prompt
    assert "Current Mechanics Snapshot" in prompt


def test_prompt_falls_back_to_legacy_when_knowledge_dir_is_missing(tmp_path: Path):
    prompt = build_game_knowledge_prompt(
        "Pegasus v4.4.6", purpose="advisor", knowledge_dir=tmp_path / "missing"
    )

    assert '# Stellaris 4.4.6 "Pegasus" Current Mechanics' in prompt


def test_civilian_question_reaches_civilian_and_related_notes():
    prompt = build_game_knowledge_prompt(
        "Pegasus v4.4.6", purpose="advisor", topics="市民が増えすぎてる、どうしたらいい？"
    )

    assert "## Civilian Stratum" in prompt
    assert "Jobless pops fall into the Civilian stratum" in prompt
    assert "## Workforce" in prompt
    assert "## Naval Capacity" not in prompt


def test_cygnus_prompt_is_notes_only_with_every_small_delta():
    prompt = build_game_knowledge_prompt(
        "Cygnus v4.5.1", purpose="advisor", topics="ポップの成長を早めるには？"
    )

    assert "Only the listed mechanics changes are verified through 4.5.1" in prompt
    assert "Building a Branch Office costs 75 Influence" in prompt
    assert "Synaptic Lathe that Nomads build" in prompt
    assert "Branch Offices use Trade, rather than Energy" not in prompt
    assert "A normal Anchorage adds 5 Naval Capacity" not in prompt
    assert "## Interpretation Guardrails" in prompt


def test_shipped_graph_is_consistent():
    load_knowledge_graph.cache_clear()
    graph = load_knowledge_graph(DEFAULT_KNOWLEDGE_DIR)
    assert graph is not None
    assert graph.min_version == (4, 4, 6)

    for note in graph.notes.values():
        assert note.facts, f"{note.title} has no facts"
        for fact in note.facts:
            assert fact.since is not None, f"{note.title}: fact without since"
            assert fact.until is None or fact.until > fact.since
        for link in note.links:
            assert graph.resolve_link(link), f"{note.title}: broken link [[{link}]]"
        missing = [locale for locale in PLAYER_LOCALES if not note.terms.get(locale)]
        assert not missing, f"{note.title} lacks terms for {missing}"


def test_shipped_graph_resolves_current_versions():
    load_knowledge_graph.cache_clear()
    graph = load_knowledge_graph(DEFAULT_KNOWLEDGE_DIR)
    assert graph is not None

    assert resolve_graph_knowledge(graph, (4, 4, 6)).status == "exact"
    assert resolve_graph_knowledge(graph, (4, 5, 1)).status == "notes_only"
    assert resolve_graph_knowledge(graph, (4, 6, 0)).status == "unsupported_newer"
