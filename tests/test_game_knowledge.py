from pathlib import Path

from stellaris_companion.game_knowledge import (
    DEFAULT_PATCHES_DIR,
    DEFAULT_SNAPSHOTS_DIR,
    DELTA_ALWAYS_INCLUDE_CHARS,
    _find_default_patches_dir,
    build_game_knowledge_prompt,
    list_versioned_markdown,
    load_game_knowledge,
    parse_section_keywords,
    parse_version,
)

PLAYER_LOCALES = ("ja", "zh-Hans", "de", "fr", "es", "pt-BR")


def test_patch_resources_resolve_from_pyinstaller_sibling_layout(tmp_path: Path):
    package_dir = tmp_path / "stellaris_companion"
    package_dir.mkdir()
    patches_dir = tmp_path / "patches"
    patches_dir.mkdir()

    assert _find_default_patches_dir(package_dir / "game_knowledge.py") == patches_dir


def test_pegasus_uses_exact_compiled_snapshot():
    knowledge = load_game_knowledge("Pegasus v4.4.6 (fdde)")

    assert knowledge.status == "exact"
    assert knowledge.loaded_through == "4.4.6"
    assert "A normal Anchorage adds 5 Naval Capacity" in (knowledge.content or "")
    assert "Typical mid-game empire" not in (knowledge.content or "")
    assert "3:1 rule" not in (knowledge.content or "")


def test_pegasus_snapshot_is_self_sufficient_for_foundational_4x_mechanics():
    knowledge = load_game_knowledge("Pegasus v4.4.6")
    content = knowledge.content or ""

    assert "Critical 4.x Baseline" in content
    assert "Humanoids Species Pack are integrated into the current base game" in content
    assert "Every eligible Pop Group on a planet grows simultaneously" in content
    assert "Machine and Organic Assembly can occur simultaneously" in content
    assert "There is no current starbase collection-range" in content
    assert "Heavy Industry" in content
    assert "Focus progression unlocks permanent research options" in content
    assert "does not by itself change the draw weights" in content
    assert "Sub-Species Integration" in content


def test_pegasus_snapshot_covers_material_mechanics_through_4_4_6():
    knowledge = load_game_knowledge("Pegasus v4.4.6")
    content = knowledge.content or ""

    assert "logistic pressure cannot reduce growth below 10%" in content
    assert "Research Restriction policies" in content
    assert "Psionic Ascension proceeds through an Ascension Situation" in content
    assert "Gaia Worlds provide +15% Pop Growth" in content
    assert "one pop-limited Assault Army per 100 pops" in content
    assert "non-primary participant can negotiate" in content
    assert "+5% after the first month, +10% after the second" in content
    assert "fully occupied secondary participant does not trigger" in content
    assert "Stellar Cannon is an offensive megastructure" in content
    assert "10,000 is not the minimum needed to fire" in content
    assert "Tier III Arkship can equip the Stellar Engine" in content
    assert "Arkships have inherent 40% habitability" in content
    assert "15,000 + 7,500 + 5,000 = 27,500 capacity" in content
    assert "Critical stage occupies the lowest 5%" in content
    assert "4 Energy upkeep per 100 automated Worker" in content


def test_new_hotfix_uses_honestly_labeled_partial_coverage():
    prompt = build_game_knowledge_prompt("Pegasus v4.4.7", purpose="advisor")

    assert "coverage is verified only through 4.4.6" in prompt
    assert "do not assume older details remained unchanged" in prompt
    assert "Treat these as the current baseline" not in prompt


def test_cygnus_uses_partial_release_notes_without_stale_pegasus_mechanics():
    for version in ("Cygnus v4.5.0", "Cygnus v4.5.1"):
        knowledge = load_game_knowledge(version)
        prompt = build_game_knowledge_prompt(version, purpose="chronicle")

        assert knowledge.status == "partial"
        assert "rather than splitting into separate groups" in prompt
        assert "Cybernetic Pops gain 10% Job Efficiency" in prompt
        assert "Building a Branch Office costs 75 Influence" in prompt
        assert "The Stellar Cannon is a Tier 3 technology" in prompt
        assert "Temporary Purge Vassals are special subjects" in prompt
        assert "Eligible Deep Scans can reveal anomalies" in prompt
        assert "Only the listed mechanics changes are verified" in prompt
        assert "other mechanics remain unverified" in prompt
        assert "Do not carry forward older-version rules" in prompt
        assert "A normal Anchorage adds 5 Naval Capacity" not in prompt
        assert "grouped for calculation by Species" not in prompt
        assert "Treat these as the current baseline" not in prompt


def test_cygnus_hotfix_only_applies_to_4_5_1_and_later():
    initial = load_game_knowledge("Cygnus v4.5.0")
    hotfix = load_game_knowledge("Cygnus v4.5.1")

    assert "Ships do not automatically disengage" not in (initial.content or "")
    assert "Ships do not automatically disengage" in (hotfix.content or "")
    assert hotfix.loaded_through == "4.5.1"


def test_cygnus_boundary_stays_safe_when_snapshot_resources_are_missing(tmp_path: Path):
    patches_dir = tmp_path / "patches"
    patches_dir.mkdir()
    (patches_dir / "4.4.md").write_text("obsolete Pegasus mechanic", encoding="utf-8")
    (patches_dir / "4.5.md").write_text("Cygnus pop groups", encoding="utf-8")

    knowledge = load_game_knowledge(
        "Cygnus v4.5.0",
        patches_dir=patches_dir,
        snapshots_dir=tmp_path / "missing_snapshots",
    )

    assert knowledge.status == "partial"
    assert knowledge.content == "Cygnus pop groups"


def test_unknown_newer_release_still_does_not_receive_old_mechanics():
    knowledge = load_game_knowledge("v4.6.0")
    prompt = build_game_knowledge_prompt("v4.6.0", purpose="advisor")

    assert knowledge.status == "unsupported_newer"
    assert knowledge.content is None
    assert "No verified mechanics pack covers v4.6.0" in prompt


def test_chronicle_prompt_keeps_mechanics_subordinate_to_recorded_evidence():
    prompt = build_game_knowledge_prompt("Pegasus v4.4.6", purpose="chronicle")

    assert "never as evidence that an event occurred" in prompt
    assert "Do not add a name, identity, participant, place, action" in prompt
    assert "Treat 'not recorded' as a limit of the supplied record" in prompt
    assert "Supplied save observations and recorded events are authoritative" in prompt
    assert "Mods can change baseline mechanics" in prompt


def test_advisor_prompt_does_not_extend_rules_into_unverified_outcomes():
    prompt = build_game_knowledge_prompt("Pegasus v4.4.6", purpose="advisor")

    assert "extend a listed rule into an unstated automatic outcome" in prompt
    assert "Verify arithmetic before using a calculated value" in prompt


def test_topic_focused_prompt_keeps_only_relevant_mechanics_and_guardrails():
    full_prompt = build_game_knowledge_prompt("Pegasus v4.4.6", purpose="advisor")
    focused_prompt = build_game_knowledge_prompt(
        "Pegasus v4.4.6",
        purpose="advisor",
        topics="Should I add anchorages before expanding my fleet and naval capacity?",
    )

    assert "A normal Anchorage adds 5 Naval Capacity" in focused_prompt
    assert "Critical 4.x Baseline" in focused_prompt
    assert "Interpretation Guardrails" in focused_prompt
    assert "Psionics & the Shroud" not in focused_prompt
    assert "Nomadic Empires & Arkships" not in focused_prompt
    assert len(focused_prompt) < len(full_prompt) / 2


def test_topic_focused_prompt_prefers_newer_overlay_sections():
    prompt = build_game_knowledge_prompt(
        "Pegasus v4.4.5",
        purpose="advisor",
        topics="operational reserves, resource abundance, and automation",
    )

    assert "Operational Reserves track Energy and Minerals one-to-one" in prompt
    assert "Resource Abundance slider" in prompt
    assert "uses a 3:1 rule rather than one-to-one conversion" not in prompt
    assert "Automated Science Ships return normally after exploring Astral Rifts" not in prompt


def test_topic_focused_prompt_does_not_misreport_available_older_coverage():
    prompt = build_game_knowledge_prompt(
        "Cetus v4.3.5",
        purpose="advisor",
        topics="What should I prioritize next?",
    )

    assert "Verified mechanics for Cetus v4.3.5" in prompt
    assert "Other verified mechanics areas for this version" in prompt
    assert "- Naval Capacity & Fleet Scale: Anchorages" in prompt
    assert "No verified mechanics pack covers" not in prompt


def test_topic_focused_cygnus_prompt_keeps_small_release_note_deltas():
    prompt = build_game_knowledge_prompt(
        "Cygnus v4.5.1",
        purpose="advisor",
        topics="population and factions",
    )

    assert "Only the listed mechanics changes are verified through 4.5.1" in prompt
    assert "rather than splitting into separate groups" in prompt
    assert "Do not carry forward older-version rules" in prompt
    # Each delta corrects a stale belief, so a small pack is never trimmed by topic.
    assert "Building a Branch Office costs 75 Influence" in prompt
    assert "Synaptic Lathe that Nomads build" in prompt
    assert "A normal Anchorage adds 5 Naval Capacity" not in prompt
    assert "Treat these as the current baseline" not in prompt


def test_japanese_cygnus_question_receives_release_note_deltas():
    prompt = build_game_knowledge_prompt(
        "Cygnus v4.5.1",
        purpose="advisor",
        topics="ポップの成長を早めるには？",
    )

    assert "rather than splitting into separate groups" in prompt
    assert "Do not carry forward older-version rules" in prompt
    assert "no topic-specific mechanics section was needed" not in prompt


def _write_large_delta_fixture(tmp_path: Path) -> tuple[Path, Path]:
    patches_dir = tmp_path / "patches"
    snapshots_dir = patches_dir / "snapshots"
    snapshots_dir.mkdir(parents=True)
    (snapshots_dir / "9.0.md").write_text(
        "# Snapshot\n\n## Critical 4.x Baseline\n* **Base:** Base rule.\n\n"
        "## Naval Capacity\n* **Old Anchorage:** Snapshot anchorage rule.\n",
        encoding="utf-8",
    )
    filler = "* **Filler:** " + "x" * DELTA_ALWAYS_INCLUDE_CHARS + "\n"
    (patches_dir / "9.0.1.md").write_text(
        "# Overlay\n\n## Naval Changes\n<!-- keywords\nja: 停泊所\n-->\n"
        "* **New Anchorage:** Overlay anchorage rule.\n\n"
        f"## Exploration Changes\n{filler}",
        encoding="utf-8",
    )
    return patches_dir, snapshots_dir


def test_large_delta_pack_is_still_selected_by_topic(tmp_path: Path):
    patches_dir, snapshots_dir = _write_large_delta_fixture(tmp_path)

    prompt = build_game_knowledge_prompt(
        "9.0.1",
        purpose="advisor",
        topics="停泊所はいくつ必要？",
        patches_dir=patches_dir,
        snapshots_dir=snapshots_dir,
    )

    assert "Overlay anchorage rule" in prompt
    assert "Base rule" in prompt
    assert "x" * 100 not in prompt


def test_japanese_question_selects_snapshot_section_by_keyword():
    prompt = build_game_knowledge_prompt(
        "Pegasus v4.4.6",
        purpose="advisor",
        topics="停泊所を増やしてから艦隊を拡大すべき？",
    )

    assert "A normal Anchorage adds 5 Naval Capacity" in prompt
    assert "## Critical 4.x Baseline" in prompt
    assert "Operational Reserves start with 15,000 capacity" not in prompt
    assert "Other verified mechanics areas" not in prompt


def test_unmatched_question_lists_omitted_sections_instead_of_full_snapshot():
    prompt = build_game_knowledge_prompt(
        "Pegasus v4.4.6",
        purpose="advisor",
        topics="次は何を優先すべき？",
    )

    assert "## Critical 4.x Baseline" in prompt
    assert "Other verified mechanics areas for this version" in prompt
    assert "- Naval Capacity & Fleets: Fleet Scale, Anchorages" in prompt
    assert "A normal Anchorage adds 5 Naval Capacity" not in prompt


def test_follow_up_question_uses_recent_topics_only_when_unmatched():
    follow_up = build_game_knowledge_prompt(
        "Pegasus v4.4.6",
        purpose="advisor",
        topics="それって具体的にどういうこと？",
        fallback_topics="停泊所を増やすべき？",
    )
    new_subject = build_game_knowledge_prompt(
        "Pegasus v4.4.6",
        purpose="advisor",
        topics="遊牧帝国の方舟はどう使う？",
        fallback_topics="停泊所を増やすべき？",
    )

    assert "A normal Anchorage adds 5 Naval Capacity" in follow_up
    assert "Arkships have inherent 40% habitability" in new_subject
    assert "A normal Anchorage adds 5 Naval Capacity" not in new_subject


def test_keyword_comments_never_reach_the_model():
    knowledge = load_game_knowledge("Cygnus v4.5.1")
    snapshot = load_game_knowledge("Pegasus v4.4.6")

    for content in (knowledge.content or "", snapshot.content or ""):
        assert "keywords" not in content
        assert "ja:" not in content
        assert "\n\n\n" not in content


def test_current_knowledge_sections_have_keywords_for_every_player_locale():
    snapshot_versions = list_versioned_markdown(DEFAULT_SNAPSHOTS_DIR)
    newest_snapshot = snapshot_versions[-1]
    newest_key = parse_version(newest_snapshot)
    current_files = [DEFAULT_SNAPSHOTS_DIR / f"{newest_snapshot}.md"] + [
        DEFAULT_PATCHES_DIR / f"{version}.md"
        for version in list_versioned_markdown(DEFAULT_PATCHES_DIR)
        if (key := parse_version(version)) is not None
        and newest_key is not None
        and key > newest_key
    ]

    for path in current_files:
        text = path.read_text(encoding="utf-8")
        keywords = parse_section_keywords(text)
        for section in text.split("\n#")[1:]:
            title = section.lstrip("#").splitlines()[0].strip()
            if "**" not in section.split("\n#")[0] or title in {
                "Critical 4.x Baseline",
                "Interpretation Guardrails",
            }:
                continue
            if title not in keywords:
                raise AssertionError(f"{path.name}: '{title}' has no keywords")
            missing = [locale for locale in PLAYER_LOCALES if not keywords[title].get(locale)]
            assert not missing, f"{path.name}: '{title}' lacks keywords for {missing}"
