"""
Offline tests - no API key, no network.

Run:  python -m pytest -q
"""
import sqlite3

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

from example1_thread import build_graph as build_example1
from example3_time_travel import MAX_ATTEMPTS
from example3_time_travel import build_graph as build_example3
from example4_sqlite import build_graph as build_example4


def thread(name: str) -> dict:
    return {"configurable": {"thread_id": name}}


# --- Example 1: threads --------------------------------------------------------

def test_a_thread_remembers_between_calls():
    graph = build_example1(MemorySaver())
    config = thread("asha")

    graph.invoke({"messages": ["user: my name is Asha"]}, config)
    result = graph.invoke({"messages": ["user: i live in Chennai"]}, config)

    assert result["facts"] == ["Name: Asha", "Lives in: Chennai"]
    assert len(result["messages"]) == 4


def test_different_threads_do_not_share_memory():
    graph = build_example1(MemorySaver())

    graph.invoke({"messages": ["user: my name is Asha"]}, thread("asha"))
    ravi = graph.invoke({"messages": ["user: my name is Ravi"]}, thread("ravi"))

    assert ravi["facts"] == ["Name: Ravi"]


def test_without_a_checkpointer_every_call_starts_from_nothing():
    graph = build_example1()  # no checkpointer

    graph.invoke({"messages": ["user: my name is Asha"]}, thread("asha"))
    result = graph.invoke({"messages": ["user: what do you know?"]}, thread("asha"))

    assert result["facts"] == []
    assert result["messages"] == [
        "user: what do you know?",
        "bot: I have not learned anything about you yet.",
    ]


# --- Example 2: inspecting checkpoints ----------------------------------------

def test_get_state_returns_the_finished_state():
    graph = build_example1(MemorySaver())
    config = thread("state")

    graph.invoke({"messages": ["user: my name is Asha"]}, config)
    snapshot = graph.get_state(config)

    assert snapshot.next == ()
    assert snapshot.values["facts"] == ["Name: Asha"]
    assert snapshot.config["configurable"]["checkpoint_id"]


def test_history_is_newest_first_and_keeps_every_step():
    graph = build_example1(MemorySaver())
    config = thread("history")

    for text in ("hello", "again", "and again"):
        graph.invoke({"messages": [f"user: {text}"]}, config)

    history = list(graph.get_state_history(config))

    assert len(history) > 3
    assert history[0].values == graph.get_state(config).values
    assert history[-1].values == {"messages": [], "facts": []}  # the input, before any node ran


def test_a_stopped_checkpoint_knows_which_node_runs_next():
    graph = build_example1(MemorySaver())
    config = thread("next")

    graph.invoke({"messages": ["user: my name is Asha"]}, config)
    history = list(graph.get_state_history(config))

    halfway = next(item for item in history if item.next)
    assert halfway.next == ("reply",)


# --- Example 3: time travel ----------------------------------------------------

def test_time_travel_can_rewind_and_change_the_outcome():
    graph = build_example3(MemorySaver())
    config = thread("time-travel")

    first = graph.invoke({"drafts": [], "feedback": "", "attempts": 0}, config)
    assert first["attempts"] == MAX_ATTEMPTS
    assert first["drafts"] == ["Draft 1", "Draft 2", "Draft 3"]

    target = next(
        item
        for item in graph.get_state_history(config)
        if item.next == ("write",) and item.values["attempts"] == 1
    )

    fork = graph.update_state(target.config, {"attempts": 0, "feedback": ""})
    assert graph.get_state(fork).next == ("write",)

    rewound = graph.invoke(None, fork)

    # 'Draft 1' twice - the second is the rewound timeline starting over.
    assert rewound["drafts"] == ["Draft 1", "Draft 1", "Draft 2", "Draft 3"]
    assert rewound["attempts"] == MAX_ATTEMPTS


def test_rewinding_does_not_delete_the_original_checkpoints():
    graph = build_example3(MemorySaver())
    config = thread("keep-history")

    graph.invoke({"drafts": [], "feedback": "", "attempts": 0}, config)
    before = len(list(graph.get_state_history(config)))

    target = next(
        item
        for item in graph.get_state_history(config)
        if item.next == ("write",) and item.values["attempts"] == 1
    )
    fork = graph.update_state(target.config, {"attempts": 0, "feedback": ""})
    graph.invoke(None, fork)

    after = len(list(graph.get_state_history(config)))
    assert after > before


# --- Example 4: persistence that survives the process -------------------------

def test_sqlite_state_survives_a_new_connection(tmp_path):
    db = tmp_path / "checkpoints.db"
    already_crashed = tmp_path / "already-crashed.flag"
    already_crashed.write_text("x", encoding="utf-8")
    config = thread("persist")

    conn = sqlite3.connect(db, check_same_thread=False)
    build_example4(SqliteSaver(conn), crash_flag=already_crashed).invoke(
        {"order_id": "A-1", "steps_done": [], "charged": False}, config
    )
    conn.close()

    conn = sqlite3.connect(db, check_same_thread=False)
    snapshot = build_example4(SqliteSaver(conn), crash_flag=already_crashed).get_state(config)
    conn.close()

    assert snapshot.values["steps_done"] == ["reserve_stock", "charge_card", "ship"]
    assert snapshot.values["charged"] is True
    assert snapshot.next == ()


def test_resume_after_a_crash_does_not_repeat_completed_steps(tmp_path):
    crash_once = tmp_path / "crash-once.flag"
    graph = build_example4(MemorySaver(), crash_flag=crash_once)
    config = thread("order")

    with pytest.raises(RuntimeError):
        graph.invoke({"order_id": "A-1", "steps_done": [], "charged": False}, config)

    stopped = graph.get_state(config)
    assert stopped.values["steps_done"] == ["reserve_stock"]
    assert stopped.next == ("charge_card",)

    resumed = graph.invoke(None, config)

    # reserve_stock is present exactly once - it did not run again.
    assert resumed["steps_done"] == ["reserve_stock", "charge_card", "ship"]
    assert resumed["charged"] is True
