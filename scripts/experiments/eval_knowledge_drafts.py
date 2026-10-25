"""Draft graph updates for chosen past releases without writing any files.

Use it to compare models or prompts on real release notes before changing the pipeline:

    KNOWLEDGE_PROVIDER=gemini KNOWLEDGE_API_KEY=... \\
        python scripts/experiments/eval_knowledge_drafts.py --news-file news.json 4.5.2 4.5.1

Provider settings match scripts/knowledge_pipeline.py. Each release is drafted against the
current graph, so releases already in the graph mainly test extraction and placement.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import knowledge_pipeline as pipeline  # noqa: E402
from stellaris_companion.knowledge_graph import (  # noqa: E402
    DEFAULT_KNOWLEDGE_DIR,
    load_knowledge_graph,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("versions", nargs="+", help="Release versions, such as 4.5.2.")
    parser.add_argument("--news-file", type=Path, help="Saved Steam news JSON.")
    parser.add_argument("--knowledge-dir", type=Path, default=DEFAULT_KNOWLEDGE_DIR)
    parser.add_argument("--chunk-chars", type=int, default=pipeline.DEFAULT_CHUNK_CHARS)
    parser.add_argument("--out", type=Path, help="Also write the combined report here.")
    args = parser.parse_args(argv)

    graph = load_knowledge_graph(args.knowledge_dir)
    if graph is None:
        raise SystemExit(f"No knowledge graph at {args.knowledge_dir}")
    releases = {
        release.version: release
        for release in pipeline.find_stable_releases(pipeline.load_news(args.news_file))
    }
    generator = pipeline.ModelRecorder(pipeline.create_generator())
    reports = []
    try:
        for version in args.versions:
            release = releases.get(version)
            if release is None:
                print(f"{version}: no stable release post in the news feed", file=sys.stderr)
                continue
            proposals, problems = pipeline.propose_facts(
                generator, release, graph, chunk_chars=args.chunk_chars
            )
            review = pipeline.review_proposals(proposals, release.text, graph)
            changed = sorted({proposal.note for proposal in review.accepted})
            reports.append(
                pipeline.render_summary(
                    release, review, changed, problems, graph, models=generator.served_models
                )
            )
    finally:
        generator.close()
    report = "\n\n".join(reports)
    print(report)
    if args.out:
        args.out.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
