# Mechanics Knowledge Graph

How Advisor and Chronicle prompts receive versioned Stellaris mechanics from concept notes.

## Goals

1. **Correct stale beliefs.** Models of every age carry older Stellaris systems from their
   training data. The prompt must state the current mechanic for the player's game version.
2. **Bring the right facts, not all facts.** A question about civilians should receive every
   verified fact about civilians and the concepts that directly govern them, without unrelated
   rules that the model might misapply.
3. **Resolve history before the request.** Models handle change logs poorly: in the
   maintainer's evaluation, compact patch history produced 1 clearly correct answer from 29,
   while a self-contained current-state snapshot produced 30 acceptable answers from 30
   (see `patches/README.md`). Supersession is therefore decided when knowledge is written and
   reviewed. At request time the resolver only filters facts by version.
4. **Keep working as the game changes.** A new release should require reviewing the facts it
   changes, not rewriting a snapshot.
5. **Stay provider-neutral and deterministic.** Selection is plain Python. It adds no model or
   embedding calls, behaves identically for every provider, and works offline.
6. **Never discuss patches with players.** Facts are present-tense statements. Version
   metadata stays out of model-facing text, following the existing prompt policy.

The current release line is the priority. Older release lines remain on the legacy snapshot
resolver until their facts are added to the graph.

## Layout

```
patches/knowledge/
  _manifest.md         graph-wide settings
  concepts/*.md        one concept per note
```

The folder can be opened as an Obsidian vault. `[[Wikilinks]]` between notes form the graph and
appear in Obsidian's graph view. Files under `patches/` are already bundled with the desktop
backend.

### Manifest

```markdown
---
min_version: 4.4.6
breaking_lines: [4.5]
---
```

- `min_version`: the oldest game version the graph is authoritative for. Older saves use the
  legacy resolver in `stellaris_companion/game_knowledge.py`.
- `breaking_lines`: release lines that redesigned underlying mechanics (4.5 changed the
  Pop Group data model). Facts not confirmed on or after such a line are not carried across it.

### Concept notes

```markdown
---
terms:
  en: [civilian, civilians, jobless pops]
  ja: [市民, 民間人, シビリアン, 無職]
  zh-Hans: [平民]
  de: [Zivilisten]
  fr: [civils]
  es: [civiles]
  pt-BR: [civis]
verified_through: 4.4.6
---
# Civilian Stratum

- **Fallback Strata:** Jobless pops fall into the Civilian stratum ... {since: 4.4.6}

Related: [[Workforce]], [[Migration]]
```

Front matter fields:

| Field | Meaning |
| --- | --- |
| `terms` | Words players use for the concept, per app language. Required for every locale. |
| `verified_through` | Newest version for which the whole note was checked against the shipped game. Omit when the note holds release-note facts only. |
| `always` | Include whenever the note has facts for the version, regardless of topic. Replaces matching the "Critical 4.x Baseline" heading text. |
| `version_independent` | Interpretation rules that do not depend on game mechanics (for example, evidence guardrails). They are never cut at a breaking line. |

Body rules:

- Each fact is a bullet (`- ` or `* `, continuation lines indented) or a Markdown table.
- A trailing `{since: X}` or `{since: X, until: Y}` gives the versions where the fact holds:
  `since <= version < until`. A table takes its metadata on the line directly below it.
- A changed mechanic keeps its old fact with `until` and gains a new fact with `since`. Old
  facts are never rewritten in place, so older saves keep receiving the rules of their version.
- Facts are written in the present tense. A stale belief is countered with a present-tense
  negative ("There is no single species growth slot"), never with change history.
- `[[Links]]` may appear anywhere in the note. They are rendered as plain text.
- HTML comments hold sources and maintainer notes and never reach the model.

`since` defaults conservatively to the version where the fact was verified. It can be lowered
when an older release line is added to the graph.

## Request-time resolution

1. **Version.** Extract the version from the save. Use the graph when the version is at or
   above `min_version`; otherwise use the legacy resolver. A release line newer than anything
   in the graph receives no mechanics, as before.
2. **Eligible facts.** Keep facts with `since <= version < until`. When a breaking line lies at
   or below the version and a note was last verified before it, keep only that note's facts
   from the breaking line onward.
3. **Coverage status.**
   - *exact*: every eligible fact comes from notes verified through the version.
   - *partial*: some facts are newer than their note's verification, or the version is newer
     than the verification. The prompt says coverage is verified only through the stated version.
   - *notes-only*: past a breaking line with no note re-verified on it. The prompt says only
     the listed changes are verified and older rules must not be carried forward.
4. **Selection** (when the request has topics):
   - Always: `always` notes, plus every unverified delta fact (newer than its note's
     `verified_through`) while those deltas total at most 8,000 characters.
   - Seeds: notes whose title words or `terms` match the request. Latin-script terms match
     whole words (plural forms included), and every word of a phrase must appear. Japanese and
     Chinese terms match as substrings. Synonyms live in each note's `terms`, not in code. Up
     to three notes, ranked by matched terms.
   - Follow-ups: when nothing matches, the session's recent questions are tried.
   - Neighbors: up to three notes linked to or from a seed are added, most-connected first.
     Seeds and neighbors share an 8,000-character budget; the best seed is always kept.
   - Index: when nothing matches at all, the prompt lists the omitted notes and their fact
     labels so the model knows which areas have version-specific rules.
   Without topics, all eligible notes are included.
5. **Rendering.** Each selected note becomes `## Title` followed by its eligible facts, with
   metadata and link brackets removed.

## Maintenance pipeline

`scripts/knowledge_pipeline.py` drafts graph changes for new stable releases; a maintainer
reviews them as a pull request.

1. **Detect a release.** The trigger is Stellaris' public branch build on Steam, read with
   anonymous SteamCMD (`+login anonymous +app_info_update 1 +app_info_print 281990`): the
   `branches.public` entry gives `buildid` and `timeupdated` (when it went live), while betas
   sit on separate branches such as `stellaris_test`. While the build matches
   `steam_public_build` in `_manifest.md`, nothing else runs. Across 50 public builds from May
   2025 to October 2026, every stable release post appeared within 5.1 hours of its build going
   live (median 1 hour), and 15 builds had no release post at all. So after a build changes:
   - a versioned release post is processed as below;
   - an unversioned launch post (such as `Stellaris: Nomads is available now!`, which carried
     4.4.1) within 6 hours before to 24 hours after the build raises a warning, for 72 hours,
     that a release line may have launched and needs its notes added by hand;
   - with no post, the next daily run checks again, and after 24 hours the build is treated as
     an unannounced update.
   The build is recorded by the release's pull request once no older release is pending, so
   unannounced builds and backlogs never block a later release.
2. **Find release posts.** `check` calls Steam's `ISteamNews/GetNewsForApp/v2` for app 281990 with
   `feeds=steam_community_announcements` and `maxlength=0` (full post bodies), and lists stable
   release announcements whose version is at or above `min_version` and not yet known to the
   graph (as a fact's `since`, a note's `verified_through`, or `reviewed_releases`).
   Stable titles start with the version (optionally after "Stellaris" or "Stellaris Patch")
   and say it is released, available, or a patch or hotfix: `Stellaris 4.5 "Cygnus" now
   available!`, `Stellaris 4.5.1 released (checksum 358e)`, `Stellaris 4.4.6 hotfix released
   (fdde)`, `4.2.2 Hotfix now available`. Open betas (`Stellaris 4.4.4 "Pegasus" Open Beta (3bc0)
   now available!`, `4.3.2 Open Beta is now on stellaris_test`), dev diaries (including
   "Tentative Patch Notes"), and teasers are skipped. Checked against the feed's 100 most recent
   announcements (September 2025 to October 2026): all 21 stable releases from 4.1.1 to 4.5.2
   are found and no beta is. A release line that launches only inside a DLC announcement
   (4.4 arrived as `Stellaris: Nomads is available now!`) has no version in its title; the
   report then asks for its main notes when the line's first hotfix is processed.
3. **Propose facts.** `update` splits the release notes into excerpts and sends each with a catalog of note titles and current fact labels. The model
   returns structured proposals: target note, label, present-tense fact, a verbatim quote, and an
   optional label of the fact it supersedes.
4. **Validate.** A proposal is rejected when its quote is not in the fetched notes, it uses
   change-history wording, it names an unknown note without asking for a new one, or the fact it
   claims to supersede does not exist. New notes get terms for every locale from a second request
   and are rejected without them.
5. **Edit.** Accepted facts are added with `{since: <release>}` before the note's `Related:` line.
   A superseded fact, or a current fact with the same label, is closed with `until`. The release is
   appended to `reviewed_releases`, even when nothing changed, so it is not proposed again.
   `verified_through` is never raised by the pipeline.
6. **Report.** A summary lists accepted facts with their quotes, rejected proposals with reasons,
   and anything needing attention, such as a new release line that may belong in `breaking_lines`,
   or a short Steam post whose full notes are only on the Paradox forum (not fetched).

### Choosing a model

The pipeline uses the Advisor's provider adapters, so any provider the app supports works:

| `KNOWLEDGE_PROVIDER` | `KNOWLEDGE_MODEL` | Other settings |
| --- | --- | --- |
| `gemini` | Optional; defaults to the Advisor's `GEMINI_FLASH_MODEL` (`backend/core/model_routing.py`) | `KNOWLEDGE_API_KEY` from Google AI Studio |
| `openrouter` | Required | `KNOWLEDGE_API_KEY` |
| `custom` | Required | `KNOWLEDGE_BASE_URL` (OpenAI-compatible) and usually `KNOWLEDGE_API_KEY` |
| `ollama`, `lm_studio` | Required | Local server; not reachable from GitHub-hosted runners |

No model ID is hard-coded in the pipeline or workflow. Gemini follows the model the Advisor
already ships and keeps current; every other provider must name a model it actually offers.
Free tiers change; check the provider's current limits (for Gemini, the project's rate-limit
view in Google AI Studio). A run makes one request per excerpt plus one per new note.

GitHub Models is not an option: GitHub retired it, including its inference API, on
July 30, 2026.

### Running locally

Any supported provider works; nothing is fixed to one vendor:

```sh
python scripts/knowledge_pipeline.py check
KNOWLEDGE_PROVIDER=gemini KNOWLEDGE_API_KEY=... \
  python scripts/knowledge_pipeline.py update --summary summary.md
KNOWLEDGE_PROVIDER=custom KNOWLEDGE_BASE_URL=https://openrouter.ai/api/v1 \
  KNOWLEDGE_MODEL=... KNOWLEDGE_API_KEY=... python scripts/knowledge_pipeline.py update --dry-run
```

`--news-file` reads a saved Steam news JSON response instead of fetching the feed.

### Daily workflow

`.github/workflows/knowledge-update.yml` runs daily and on demand. It processes the oldest
unreviewed release, runs the knowledge tests, and opens a pull request from
`knowledge/update-<version>`. It skips a release whose branch already exists.

The model provider comes from repository variables `KNOWLEDGE_PROVIDER`, `KNOWLEDGE_MODEL`,
and `KNOWLEDGE_BASE_URL` and the `KNOWLEDGE_API_KEY` secret. Without `KNOWLEDGE_PROVIDER` the job
only reports the unreviewed release as a notice and in the run summary.

To enable it in a fork:

- Add the variables and secret above under **Settings > Secrets and variables > Actions**.
- Enable Actions for the fork; scheduled workflows are disabled in forks until then.
- Allow **Settings > Actions > General > Allow GitHub Actions to create and approve pull
  requests**.
- Pull requests opened with `GITHUB_TOKEN` do not start other workflows, so the job runs the
  knowledge tests itself before opening one.

## Testing

`tests/test_knowledge_graph.py` checks parsing, version filtering, breaking lines, selection,
and the integrity of the shipped graph: every link resolves, every note has terms for each
player locale, and every fact has a valid `since`.
