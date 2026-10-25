# Model Game Knowledge

Stellaris Companion gives every supported model versioned mechanics context for the player's
save. Complete snapshots provide a factual baseline; focused release-note packs provide partial
coverage when a new game version has not yet been fully audited.

## How It Works

1. The app reads the Stellaris version from the save.
2. The shared resolver selects an exact snapshot, a compatible snapshot and overlays, or a
   notes-only pack for an audited breaking release line.
3. The context is added to both Advisor and Chronicle prompts alongside extracted campaign facts.
4. Unknown newer release lines do not receive older mechanics presented as current.

Snapshots describe current behavior rather than patch history. Campaign evidence remains the
authority for what happened in a particular save, and modded mechanics may differ from the
unmodded baseline documented here.

## Why Snapshots

Models of any age can reproduce obsolete Stellaris systems because older information is common in
their training data. A self-contained snapshot supplies the current system from first principles
instead of assuming that the model already understands every earlier redesign.

In a controlled test of six deliberately stale premises across five model families, the compact
patch context produced 1 clearly correct response from 29 usable answers. The self-contained
4.4.6 snapshot produced 30 accurate or acceptable answers from 30 responses. Results were judged
by a maintainer for substantive correctness, allowing normal variation in wording.

## Maintaining Snapshots

- Use final Paradox release notes first, followed by shipped unmodded game data for numerical rules.
- Keep the current stable snapshot self-contained, including foundational mechanics that remain true.
- Add small overlays for hotfixes, then fold them into a fresh snapshot before history accumulates.
- When a new release changes an underlying mechanic before shipped data can be checked, add
  source-backed release-note deltas for that release line. The resolver labels these partial
  and does not import the prior release's snapshot. Publish a complete snapshot only after
  its current-state claims have been checked against the shipped game.
- Do not add open-beta mechanics to a stable snapshot.
- Avoid subjective benchmarks unless authoritative sources and relevant game settings support them.

Source and coverage decisions for each stable snapshot live in `patches/audits/`.

## Topic Selection and Keywords

Advisor prompts keep the critical baseline and guardrails, then add the few sections that match
the question. Small release-line deltas (overlays newer than the snapshot, or a notes-only pack)
are always included because each one corrects a stale belief. When nothing matches, the earlier
questions in the conversation are tried; failing that, the prompt lists the omitted sections so
the model knows which areas have version-specific rules.

Section titles are English, so every topic section carries keywords for the app's player
languages in a comment directly under its heading. Comments never reach the model:

```markdown
## Naval Capacity & Fleets
<!-- keywords
en: naval capacity, command limit, anchorage
ja: 艦隊上限, 停泊所
zh-Hans: 海军容量, 锚地
de: Flottenkapazität
fr: capacité navale
es: capacidad naval
pt-BR: capacidade naval
-->
```

Latin-script keywords match whole words (all words of a phrase must appear); Japanese and Chinese
keywords match as substrings, so avoid very short or generic terms. `tests/test_game_knowledge.py`
requires keywords for every locale in the newest snapshot and in each newer release-note pack.

Before shipping, run `tests/test_game_knowledge.py` and record cross-provider responses with
`scripts/experiments/eval_game_knowledge.py` for human review. Test stale premises that a model
with an older knowledge cutoff is likely to answer confidently but incorrectly.

Official release announcements are available from the
[Stellaris Steam news feed](https://store.steampowered.com/news/posts/?appids=281990).
