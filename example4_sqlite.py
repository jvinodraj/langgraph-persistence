"""
Example 4: persistence that survives the process.

MemorySaver lives in RAM, so it dies with the Python process. That is fine for a notebook, useless for a server.
SqliteSaver writes each checkpoint to a file, so a brand new process can pick up exactly where the last one stopped.

The scenario: a three-step order pipeline that crashes half way through.

    reserve_stock -> charge_card -> ship

`charge_card` fails the first time it runs (a simulated payment gateway timeout). The graph stops with the state
saved and `next = ('charge_card',)`. Start the script again and it resumes AT `charge_card` - `reserve_stock`
does not run a second time.

Run it twice:

    python example4_sqlite.py      # first run: reserve_stock, then CRASH at charge_card
    python example4_sqlite.py      # second run: resumes at charge_card, ships, done

    python example4_sqlite.py --reset   # start over

The database and the crash flag live in .data/ and are gitignored.
"""
import operator
import sqlite3
import sys
from pathlib import Path
from typing import Annotated

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict


DATA_DIR = Path(__file__).resolve().parent / ".data"
DB_PATH = DATA_DIR / "checkpoints.db"
CRASH_FLAG = DATA_DIR / "crash-once.flag"
THREAD_ID = "order-1001"


class State(TypedDict):
    order_id: str
    steps_done: Annotated[list[str], operator.add]
    charged: bool


def reserve_stock(state: State):
    print("  reserve_stock  -> stock reserved")
    return {"steps_done": ["reserve_stock"]}


def make_charge_node(crash_flag: Path):
    """charge_card, but it raises the first time it is ever called."""

    def charge_card(state: State):
        if not crash_flag.exists():
            crash_flag.parent.mkdir(parents=True, exist_ok=True)
            crash_flag.write_text("crashed once, on purpose\n", encoding="utf-8")
            print("  charge_card    -> CRASH: payment gateway timeout")
            raise RuntimeError("payment gateway timeout")
        print("  charge_card    -> payment taken")
        return {"steps_done": ["charge_card"], "charged": True}

    return charge_card


def ship(state: State):
    print("  ship           -> dispatched")
    return {"steps_done": ["ship"]}


def build_graph(checkpointer=None, crash_flag: Path = CRASH_FLAG):
    builder = StateGraph(State)
    builder.add_node("reserve_stock", reserve_stock)
    builder.add_node("charge_card", make_charge_node(crash_flag))
    builder.add_node("ship", ship)

    builder.add_edge(START, "reserve_stock")
    builder.add_edge("reserve_stock", "charge_card")
    builder.add_edge("charge_card", "ship")
    builder.add_edge("ship", END)

    return builder.compile(checkpointer=checkpointer)


def reset() -> None:
    for path in (DB_PATH, CRASH_FLAG):
        if path.exists():
            path.unlink()
    print("Removed the saved database and the crash flag. The next run starts fresh.")


def main():
    if "--reset" in sys.argv:
        reset()
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    graph = build_graph(SqliteSaver(conn))
    config = {"configurable": {"thread_id": THREAD_ID}}

    snapshot = graph.get_state(config)

    if snapshot.next:
        # A checkpoint exists and it is pointing at a node that has not run yet.
        print("=" * 72)
        print("Resuming a saved run")
        print("=" * 72)
        print(f"  steps already done : {snapshot.values['steps_done']}")
        print(f"  next node          : {', '.join(snapshot.next)}")
        print()
        print("  invoke(None, config) - no new input, just carry on from the checkpoint.")
        print()
        result = graph.invoke(None, config)

    elif snapshot.values:
        print("=" * 72)
        print("This order is already finished")
        print("=" * 72)
        print(f"  steps done : {snapshot.values['steps_done']}")
        print(f"  charged    : {snapshot.values['charged']}")
        print()
        print("  Run  python example4_sqlite.py --reset  to start over.")
        conn.close()
        return

    else:
        print("=" * 72)
        print("First run - no checkpoint in the database yet")
        print("=" * 72)
        try:
            result = graph.invoke(
                {"order_id": "A-1001", "steps_done": [], "charged": False},
                config,
            )
        except RuntimeError as exc:
            print()
            print(f"  The graph stopped: {exc}")
            print("  (the crash is simulated - it happens on purpose, once)")
            print()
            saved = graph.get_state(config)
            print("  What survived in SQLite:")
            print(f"    steps_done : {saved.values['steps_done']}")
            print(f"    next       : {', '.join(saved.next)}")
            print()
            print("  Now run the same command again, in a NEW process:")
            print("      python example4_sqlite.py")
            print()
            print("  charge_card will succeed, and reserve_stock will NOT run a second time.")
            conn.close()
            return

    print()
    print("=" * 72)
    print("Finished")
    print("=" * 72)
    print(f"  steps done : {result['steps_done']}")
    print(f"  charged    : {result['charged']}")
    print()
    print("  Every step ran exactly once, even though the pipeline spanned two processes.")
    print("  That is what a checkpointer buys you: durable execution, not just memory.")

    conn.close()


if __name__ == "__main__":
    main()
