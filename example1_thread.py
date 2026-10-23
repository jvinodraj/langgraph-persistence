"""
Example 1: a thread.

Session 1's graphs were stateless: `invoke()` returned a dict and the graph immediately forgot it.
Here we add two things - a checkpointer and a `thread_id` - and the same graph starts to remember.

    remember -> reply

`remember` pulls facts out of the newest message. `reply` answers using every fact it has seen so far.
The graph shape never changes; only where the state is stored changes.

Run:  python example1_thread.py

No API key needed. Every node here is deterministic on purpose - this example is about memory, not generation.
"""
import operator
from typing import Annotated

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict


# The shared data.
# Both keys use operator.add, so every node APPENDS instead of overwriting (that was Session 1's reducer lesson).
class State(TypedDict):
    messages: Annotated[list[str], operator.add]
    facts: Annotated[list[str], operator.add]


# (trigger phrase, the label to remember it under)
FACT_PATTERNS = (
    ("my name is ", "Name"),
    ("i live in ", "Lives in"),
    ("i work at ", "Works at"),
)


def remember(state: State):
    """Reads the newest message and pulls out anything worth remembering."""
    text = state["messages"][-1].lower()
    already_known = state["facts"]

    found = []
    for trigger, label in FACT_PATTERNS:
        if trigger in text:
            # "hi, my name is asha and i live in chennai." -> "asha" -> "Name: Asha"
            rest = text.split(trigger, 1)[1]
            value = rest.split(" and ")[0].split(",")[0].strip(" .!?")
            if not value:
                continue
            fact = f"{label}: {value.title()}"
            if fact not in already_known:
                found.append(fact)
    return {"facts": found}


def reply(state: State):
    """Answers using the facts currently in the state."""
    if not state["facts"]:
        text = "bot: I have not learned anything about you yet."
    else:
        text = "bot: so far I know " + "; ".join(state["facts"]) + "."
    return {"messages": [text]}


def build_graph(checkpointer=None):
    """Build the graph.

    checkpointer=None gives you Session 1 behaviour: every invoke starts from nothing.
    Pass a checkpointer (plus a thread_id at call time) and the state is remembered.
    """
    builder = StateGraph(State)
    builder.add_node("remember", remember)
    builder.add_node("reply", reply)

    builder.add_edge(START, "remember")
    builder.add_edge("remember", "reply")
    builder.add_edge("reply", END)

    return builder.compile(checkpointer=checkpointer)


def thread(name: str) -> dict:
    """A thread_id is the name of the drawer the checkpoints are filed in."""
    return {"configurable": {"thread_id": name}}


def say(graph, config, text: str) -> dict:
    """One turn of conversation: send a message, return the whole state."""
    result = graph.invoke({"messages": [f"user: {text}"]}, config)
    print(f"  you : {text}")
    print(f"  {result['messages'][-1]}")
    print()
    return result


if __name__ == "__main__":
    print("=" * 72)
    print("Without a checkpointer - every call starts from nothing")
    print("=" * 72)

    forgetful = build_graph()  # no checkpointer at all
    one_off = thread("asha")
    say(forgetful, one_off, "Hi, my name is Asha and I live in Chennai.")
    say(forgetful, one_off, "What do you know about me?")
    print("  The second call remembered nothing - the thread_id was ignored because there was no checkpointer.")
    print()

    print("=" * 72)
    print("With MemorySaver - thread 'asha' remembers, thread 'ravi' does not")
    print("=" * 72)

    graph = build_graph(checkpointer=MemorySaver())
    asha = thread("asha")
    ravi = thread("ravi")

    say(graph, asha, "Hi, my name is Asha and I live in Chennai.")
    say(graph, asha, "I work at Contoso.")
    say(graph, asha, "What do you know about me?")

    say(graph, ravi, "Hi, my name is Ravi and I live in Pune.")
    say(graph, ravi, "What do you know about me?")

    print("=" * 72)
    print("What each thread holds right now")
    print("=" * 72)
    for name in ("asha", "ravi"):
        snapshot = graph.get_state(thread(name))
        print(f"  thread {name!r}")
        print(f"    facts    : {snapshot.values['facts']}")
        print(f"    messages : {len(snapshot.values['messages'])}")
        print(f"    next     : {snapshot.next or '(nothing left - the run finished)'}")
    print()

    print("Two different thread_ids, two independent memories, one graph object.")
    print("The graph still runs from START on every call - only the STATE is carried over.")
