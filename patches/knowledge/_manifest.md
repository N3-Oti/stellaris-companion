---
min_version: 4.4.6
breaking_lines: [4.5]
reviewed_releases: [4.4.6, 4.5, 4.5.1]
---
# Mechanics Knowledge Graph

Concept notes under `concepts/` supply versioned mechanics for saves at or above
`min_version`. Older saves use the snapshot and release-note files in `patches/`.
`reviewed_releases` records stable releases whose notes were reviewed, including those that
changed no fact, so the maintenance pipeline does not propose them again.
See `docs/knowledge-graph.md` for the format and resolution rules.
