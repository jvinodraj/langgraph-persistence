"""
Example 3: time travel.

The loop from Session 1, now with a checkpointer underneath it.

    write -> review -> should_continue --(not happy)--> write
                       |
                       +--(OK, or 3 attempts used)--> END

Because every step is checkpointed, we can:

  1. replay from an old checkpoint, unchanged  -> same ending
  2. rewind to an old checkpoint and EDIT the state -> a different ending
  3. keep every checkpoint that ever existed   -> nothing is overwritten

Run:  python example3_time_travel.py

No API key needed - the writer and reviewer are deterministic on purpose, so the output is reproducible.
"""
import operator
from typing import Annotated

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict


MAX_ATTEMPTS = 3
OFFLINE_DRAFTS = ["Draft 1", "Draft 2", "Draft 3"]


class State(TypedDict):
    drafts: Annotated[list[str], operator.add]
    feedback: str
    attempts: int


def write(state: State):
    index = min(state["attempts"], len(OFFLINE_DRAFTS) - 1)
    return {"drafts": [OFFLINE_DRAFTS[index]], "attempts": state["attempts"] + 1}


def review(state: State):
    """A reviewer that is never happy - so the loop always runs out of attempts."""
    return {"feedback": "Not good enough - try again."}


def should_continue(state: State):
    if state["feedback"] == "OK" or state["attempts"] >= MAX_ATTEMPTS:
        return END
    return "write"


def build_graph(checkpointer=None):
    builder = StateGraph(State)
    builder.add_node("write", write)
    builder.add_node("review", review)

    builder.add_edge(START, "write")
    builder.add_edge("write", "review")
    builder.add_conditional_edges("review", should_continue, path_map={"write": "write", END: END})

    return builder.compile(checkpointer=checkpointer)


def show(label: str, snapshot) -> None:
    print(f"  {label}")
    print(f"    drafts   : {snapshot.values['drafts']}")
    print(f"    attempts : {snapshot.values['attempts']}")
    print(f"    next     : {snapshot.next or '(done)'}")
    print()


def main():
    from langgraph.checkpoint.memory import MemorySaver

    graph = build_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "time-travel-demo"}}

    # ------------------------------------------------------------------ 1
    print("=" * 72)
    print("1. The original run - three drafts, then the safety stop")
    print("=" * 72)
    first = graph.invoke({"drafts": [], "feedback": "", "attempts": 0}, config)
    print(f"  drafts   : {first['drafts']}")
    print(f"  attempts : {first['attempts']} (hard stop at {MAX_ATTEMPTS})")
    print(f"  feedback : {first['feedback']}")
    print()

    history = list(graph.get_state_history(config))
    print(f"  {len(history)} checkpoints were written for this one run.")
    print()

    # The checkpoint to rewind to: right after draft 1, before the second write.
    target = next(
        item for item in history if item.next == ("write",) and item.values["attempts"] == 1
    )

    print("=" * 72)
    print("2. Replay from that checkpoint, with no changes")
    print("=" * 72)
    replayed = graph.invoke(None, target.config)
    print(f"  drafts   : {replayed['drafts']}")
    print(f"  attempts : {replayed['attempts']}")
    print()
    print("  Same ending. Replaying is safe: invoke(None, config) means 'carry on, no new input'.")
    print()

    # ------------------------------------------------------------------ 3
    print("=" * 72)
    print("3. Rewind to the same checkpoint and EDIT the state")
    print("=" * 72)
    print(f"  at the checkpoint, attempts = {target.values['attempts']}")
    print("  update_state(..., {'attempts': 0, 'feedback': ''})  -> pretend the first draft just happened")
    print()

    fork = graph.update_state(target.config, {"attempts": 0, "feedback": ""})
    edited = graph.get_state(fork)
    show("state right after the edit", edited)

    print("  now continue from the edited checkpoint:")
    print()
    rewound = graph.invoke(None, fork)
    print(f"  drafts   : {rewound['drafts']}")
    print(f"  attempts : {rewound['attempts']}")
    print()
    print("  'Draft 1' appears twice. The second one is the rewound timeline doing its first draft again.")
    print()

    # ------------------------------------------------------------------ 4
    print("=" * 72)
    print("4. Nothing was thrown away")
    print("=" * 72)
    after = list(graph.get_state_history(config))
    print(f"  checkpoints before the replay : {len(history)}")
    print(f"  checkpoints now               : {len(after)}")
    print()
    print("  The originals are still there. Every checkpoint keeps a pointer to its parent, so the")
    print("  history is really a tree - and the newest entry is whichever branch ran last.")


if __name__ == "__main__":
    main()
