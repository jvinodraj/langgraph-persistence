"""
graph_diagram.py - print the Mermaid source for every graph in this project.

Run:  python graph_diagram.py             # print to the terminal
      python graph_diagram.py --out docs  # also write one .md file per graph into ./docs

Paste the Mermaid source into https://mermaid.live to get a picture, or into any Markdown file that renders Mermaid.

Note: a checkpointer does not change the SHAPE of a graph, so these diagrams look the same as they would without one.
What the checkpointer adds is not a node or an edge - it is a saved copy of the state after every step.
"""
import argparse
from pathlib import Path

from example1_thread import build_graph as build_example1
from example3_time_travel import build_graph as build_example3
from example4_sqlite import build_graph as build_example4


GRAPHS = [
    ("example1-thread", "Example 1 - a thread (remember -> reply)", build_example1),
    ("example3-loop", "Example 3 - the loop used for time travel", build_example3),
    ("example4-order", "Example 4 - the order pipeline (crash and resume)", build_example4),
]


def mermaid_for(builder) -> str:
    """Return the Mermaid source for a compiled graph."""
    return builder().get_graph().draw_mermaid()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", metavar="DIR", help="also write one .md file per graph into this directory")
    args = parser.parse_args()

    out_dir = Path(args.out) if args.out else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    for slug, title, builder in GRAPHS:
        source = mermaid_for(builder)

        print("=" * 72)
        print(title)
        print("=" * 72)
        print(source)
        print()

        if out_dir:
            path = out_dir / f"{slug}.md"
            path.write_text(f"# {title}\n\n```mermaid\n{source}\n```\n", encoding="utf-8")
            print(f"wrote {path}\n")


if __name__ == "__main__":
    main()
