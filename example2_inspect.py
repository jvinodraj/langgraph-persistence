"""
Example 2: inspecting the checkpoints.

A checkpointer does not just save the last state - it saves EVERY state, in order. That list is called the
history, and it is the thing that makes crash recovery and time travel possible.

This example runs Example 1's graph, then reads the history back:

    get_state(config)          -> the newest checkpoint (a StateSnapshot)
    get_state_history(config)  -> all of them, NEWEST FIRST

Run:  python example2_inspect.py
"""
from langgraph.checkpoint.memory import MemorySaver

from example1_thread import build_graph, thread


TURNS = [
    "Hi, my name is Asha.",
    "I live in Chennai.",
    "What do you know about me?",
]


def main():
    graph = build_graph(checkpointer=MemorySaver())
    config = thread("asha")

    for text in TURNS:
        graph.invoke({"messages": [f"user: {text}"]}, config)

    # --- the newest checkpoint -------------------------------------------------
    snapshot = graph.get_state(config)

    print("=" * 72)
    print("get_state(config) - the newest checkpoint")
    print("=" * 72)
    print(f"  values     : {snapshot.values}")
    print(f"  next       : {snapshot.next or '(nothing left - the run finished)'}")
    print(f"  step       : {snapshot.metadata.get('step')}")
    print(f"  source     : {snapshot.metadata.get('source')}")
    print(f"  created_at : {snapshot.created_at}")
    print(f"  checkpoint : {snapshot.config['configurable']['checkpoint_id']}")
    parent = snapshot.parent_config or {}
    print(f"  parent     : {parent.get('configurable', {}).get('checkpoint_id')}")
    print()
    print("  `next` is the important field: it lists the nodes that would run if you continued from here.")
    print("  An empty tuple means there is nothing left to run.")
    print()

    # --- the whole history -----------------------------------------------------
    history = list(graph.get_state_history(config))

    print("=" * 72)
    print("get_state_history(config) - every checkpoint, newest first")
    print("=" * 72)
    print(f"  {'#':>3}  {'next':<14} {'step':>4}  {'msgs':>4}  {'facts':>5}")
    print(f"  {'-' * 3}  {'-' * 14} {'-' * 4}  {'-' * 4}  {'-' * 5}")
    for index, item in enumerate(history):
        nxt = ", ".join(item.next) if item.next else "(done)"
        step = item.metadata.get("step")
        messages = len(item.values.get("messages", []))
        facts = len(item.values.get("facts", []))
        print(f"  {index:>3}  {nxt:<14} {str(step):>4}  {messages:>4}  {facts:>5}")
    print()

    oldest = history[-1]
    print(f"  The oldest checkpoint (#{len(history) - 1}) is the input, before any node ran:")
    print(f"    values = {oldest.values}")
    print(f"    next   = {oldest.next}")
    print()

    print("=" * 72)
    print("Continuing from an old checkpoint")
    print("=" * 72)
    print("  Every checkpoint carries its own config, and that config can be passed straight back to invoke().")
    print("  Pick the one where 'reply' had not run yet and continue from there:")
    print()

    target = next(item for item in history if item.next == ("reply",))
    print(f"    picked checkpoint with next={target.next}")
    print(f"    state at that moment: {target.values}")
    print()
    print("    graph.invoke(None, that_config)  # None = no new input, just carry on")
    print()
    print("  That is how a graph resumes in the middle instead of at START. Example 3 puts it to work.")


if __name__ == "__main__":
    main()
