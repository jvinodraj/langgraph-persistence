# langgraph-persistence

Session 2 of LangGraph, for the FDE C4/C5 cohort. The companion repo to
[langgraph-graphs](../langgraph-graphs) and to the *LangGraph Pre-Read: What, Why, Nodes, Edges and Shared State*
document.

Session 1's graphs were stateless: `invoke()` returned a dict and the graph immediately forgot it. This repo adds one
thing - a **checkpointer** - and the same graphs start to remember, resume, and rewind.

Every example runs with **no API key**.

| Session | Repo | Topic |
|---|---|---|
| 1 | hopscotch-s1-openai-chatbot | Raw `openai` SDK + Streamlit, list-of-dicts history |
| 2 | hopscotch-s2-langchain-chatbot | LangChain: prompts, chains, memory, imperative triage |
| 3 | hopscotch-s3-lcel-chatbot | Runnables, LCEL, Parallel, Branch, streaming |
| 4 | langgraph-graphs | State, nodes, edges, reducers, branching, loops |
| **5** | **langgraph-persistence (you are here)** | **Checkpoints, threads, resume, time travel** |

## The one line that holds it all

> **A graph runs. A checkpointed graph is a process - it can be paused, resumed, and rewound.**

## Where Session 1 stops

Session 1 answered *"what path does the work take?"*. It did not answer *"what happens to the work after the run?"*.

| You need | Session 1 graph | With a checkpointer |
|---|---|---|
| Remember the last call | Forgotten as soon as `invoke` returns | State is saved after every step |
| Multi-turn conversation | Pass the whole history in by hand | `thread_id` |
| Resume after a crash | Start again from zero | `invoke(None, config)` |
| Rewind to an earlier step | Not possible | `get_state_history` + `update_state` |
| Survive a process restart | Impossible - it lived in RAM | `SqliteSaver` |
| An audit trail of every step | Manual logging | Every checkpoint is stored |
| Pause for a human to approve | Not possible | Session 3 (`interrupt`) |

**Rule of thumb:** use a checkpointer when the run is worth more than the process that started it.

## The analogy

Session 1 was a case file travelling from desk to desk. Session 2 is **the filing cabinet behind the counter**.

- Every time a clerk finishes at a desk, a **photocopy of the case file** goes into the cabinet. It is numbered, and
  stamped with which desk is next.
- The **`thread_id`** is the case number written on the drawer. Two cases never share a drawer.
- If the office loses power mid-case (a **crash**), nobody starts over. You pull the last photocopy, read which desk
  it was heading to, and carry on from there. The earlier desks are not asked to do their bit again.
- Because nothing is ever thrown away, you can pull out a photocopy from three steps ago, **change one line**, and
  let the case walk a different path. The old photocopies stay in the drawer.

That last point is the one people find surprising: **the history is not overwritten, it forks.**

## Concepts map

| Concept | Where to see it |
|---|---|
| `MemorySaver` - checkpoints kept in RAM | Examples 1, 2, 3 |
| `SqliteSaver` - checkpoints written to a file | Example 4 |
| `thread_id` - the name of the drawer | every example, via the `thread()` helper |
| `compile(checkpointer=...)` - what turns persistence on | every example's `build_graph()` |
| `get_state(config)` returns a `StateSnapshot` | Example 2 |
| `snapshot.values` - the state at that checkpoint | Example 2 |
| `snapshot.next` - which nodes would run next | Example 2 |
| `get_state_history(config)` - every checkpoint, newest first | Examples 2 and 3 |
| `snapshot.config` - a config you can pass straight back to `invoke` | Examples 2 and 3 |
| `update_state(config, values)` - edit the state, forking the history | Example 3 |
| `invoke(None, config)` - carry on, with no new input | Examples 3 and 4 |
| `parent_config` - the checkpoint before this one | Example 2 |
| A checkpointer adds no nodes and no edges | `graph_diagram.py` output |

## The four examples

### Example 1 - a thread

```
  __start__ --> remember --> reply --> __end__
```

The same graph run twice: once with no checkpointer, once with a `MemorySaver`. Two `thread_id`s keep two
conversations apart.

```
Without a checkpointer - every call starts from nothing
  you : Hi, my name is Asha and I live in Chennai.
  bot: so far I know Name: Asha; Lives in: Chennai.

  you : What do you know about me?
  bot: I have not learned anything about you yet.
```

```
With MemorySaver - thread 'asha' remembers, thread 'ravi' does not
  ...
  thread 'asha'
    facts    : ['Name: Asha', 'Lives in: Chennai', 'Works at: Contoso']
    messages : 6

  thread 'ravi'
    facts    : ['Name: Ravi', 'Lives in: Pune']
    messages : 4
```

**The most common misconception lives here.** The graph does *not* resume in the middle on the next call - it runs
from `START` again. What carries over is the **state**. Mid-graph resumption is `invoke(None, config)`, and you only
need it when a run actually stopped early.

### Example 2 - looking inside the history

Three turns produce twelve checkpoints. `get_state_history` returns them newest first:

```
    #  next           step  msgs  facts
  ---  -------------- ----  ----  -----
    0  (done)           10     6      2
    1  reply             9     5      2
    2  remember          8     5      2
    3  __start__         7     4      2
    4  (done)            6     4      2
  ...
   11  __start__        -1     0      0
```

Reading the columns:

- `next` is the checkpoint's **resume point**. `(done)` means nothing is left to run; `reply` means "if you continue
  from here, `reply` is the node that runs".
- `step` is the super-step counter across the whole thread, not per call.
- The oldest checkpoint is the input itself - which is why it shows `{'messages': [], 'facts': []}` rather than `{}`.
  Reducers initialise their keys, and the checkpointer stored that initialised state.

### Example 3 - time travel

The Session 1 loop, now with a checkpointer underneath:

```
  __start__ --> write --> review -.-> write      (not happy - go back)
                                 -.-> __end__    (OK, or 3 attempts used)
```

Because every step is saved, the same graph can be **replayed** or **rewound**:

```
1. original run      drafts: ['Draft 1', 'Draft 2', 'Draft 3']    attempts: 3
2. replay, no change drafts: ['Draft 1', 'Draft 2', 'Draft 3']    attempts: 3
3. rewind + edit     drafts: ['Draft 1', 'Draft 1', 'Draft 2', 'Draft 3']
```

The duplicate `Draft 1` is the proof: the graph went back to the checkpoint where one draft existed, the counter was
reset to `0`, and it wrote a first draft all over again - in a new branch.

```
  checkpoints before the replay : 8
  checkpoints now               : 20
```

Nothing was deleted. The eight originals are still there; the replay and the rewind added their own.

### Example 4 - persistence that survives the process

```
  __start__ --> reserve_stock --> charge_card --> ship --> __end__
```

`charge_card` fails the first time it runs. Run the script twice:

```
$ python example4_sqlite.py
First run - no checkpoint in the database yet
  reserve_stock  -> stock reserved
  charge_card    -> CRASH: payment gateway timeout

  What survived in SQLite:
    steps_done : ['reserve_stock']
    next       : charge_card

$ python example4_sqlite.py
Resuming a saved run
  steps already done : ['reserve_stock']
  next node          : charge_card

  charge_card    -> payment taken
  ship           -> dispatched

  steps done : ['reserve_stock', 'charge_card', 'ship']
```

**`reserve_stock` ran exactly once, across two operating-system processes.** That is durable execution: a retry
re-runs the step that failed, not the steps that already succeeded.

This is the difference between memory and durability. `MemorySaver` would have lost everything when the first process
died.

## Project structure

```
example1_thread.py        A thread: the same graph with and without a checkpointer.
example2_inspect.py       get_state and get_state_history - read the checkpoints back.
example3_time_travel.py   Replay, then rewind and edit. Nothing is deleted.
example4_sqlite.py        SqliteSaver, a simulated crash, and a resume in a new process.
graph_diagram.py          Prints the Mermaid source for every graph (--out writes .md files).
llm.py                    Not used here - the ready-made model hook for Session 3.
conftest.py               Makes the project root importable for the tests.
tests/test_persistence.py 10 offline pytest tests - no API key needed.
```

## Setup

Python 3.10+ (3.12 recommended).

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
python -m pip install -r requirements.txt
```

> Use `python -m pip`, not bare `pip`. A globally installed `pip` can point at a different interpreter than your
> `python`, and then the packages land in the wrong place.

## Run

```bash
python example1_thread.py
python example2_inspect.py
python example3_time_travel.py

python example4_sqlite.py --reset   # start clean
python example4_sqlite.py           # first run: crashes at charge_card
python example4_sqlite.py           # second run: resumes and finishes

python graph_diagram.py             # add --out docs to write one .md file per graph
python -m pytest -q                 # 10 offline tests
```

## Teaching flow (30 to 45 minutes)

| Time | Activity |
|---|---|
| 0:00-0:05 | Session 1 recap. Run a Session 1 graph twice and point out it remembers nothing |
| 0:05-0:10 | The filing-cabinet analogy: checkpoint, thread_id, drawer |
| 0:10-0:20 | Example 1 live. First without a checkpointer, then with. Then a second thread |
| 0:20-0:28 | Example 2. Read the history table: what does `next` mean? |
| 0:28-0:38 | Example 3. Replay is boring, then rewind - and `Draft 1` appears twice |
| 0:38-0:45 | Example 4. Two processes, one pipeline. `reserve_stock` ran once |

## Preparation checklist

- [ ] Run Example 1. Confirm `asha` ends with **3** facts and `ravi` with **2**.
- [ ] Run Example 2. One sentence: *what does an empty `next` mean?*
      **There is nothing left to run - the graph finished.**
- [ ] Run Example 3. One sentence: *why does `Draft 1` appear twice?*
      **The state was rewound to the point where one draft existed, so the timeline redid its first draft.**
- [ ] Run Example 4 twice (with `--reset` first). Watch that `reserve_stock` does not run again.
- [ ] On paper, draw the checkpoint timeline for a two-node graph and mark where a crash would resume.

### Questions to be ready for

1. **What does a checkpointer actually store?**
   A copy of the whole state after every step of the graph, filed under a `thread_id`, with a note of which node would
   run next.
2. **What is a `thread_id` for?**
   It names the conversation. Same `thread_id` means the next call continues that memory; a different one starts
   clean. It is how one graph object serves many users without mixing them up.
3. **Does a checkpointer make the graph resume in the middle automatically?**
   No. A normal `invoke(input, config)` still starts at `START` - it just starts from the *saved state*. Resuming in
   the middle is `invoke(None, config)`, and it is what you use after a crash or an interrupt.
4. **What is the difference between `MemorySaver` and `SqliteSaver`?**
   Where the checkpoints live. `MemorySaver` holds them in RAM and loses them when the process exits; `SqliteSaver`
   writes to a file, so a new process can pick them up. Same API, one-line change.
5. **What does `update_state` do?**
   Writes a new checkpoint whose values you choose, and makes it the newest one. It does not delete or edit anything
   that already happened - it forks the history.
6. **Why does anyone care about durable execution?**
   Because in a real pipeline some steps cannot be safely repeated - charging a card, sending an email. A checkpointer
   means a retry continues from the failure instead of replaying the whole run.

## Common mistakes

| Symptom | Likely cause | Fix |
|---|---|---|
| `ValueError: Checkpointer requires ... 'thread_id'` | Called `invoke` without a config | `{"configurable": {"thread_id": "..."}}` |
| Every call forgets again | `compile()` had no checkpointer | `builder.compile(checkpointer=MemorySaver())` |
| Two users see each other's history | They share a `thread_id` | One `thread_id` per conversation |
| Memory is gone after a restart | You used `MemorySaver` | Use `SqliteSaver` |
| The history looks longer than it should | You forked with `update_state`; both branches are listed | Follow `parent_config` to see the branch |
| `update_state` seems to do nothing | You ignored the config it returned | `fork = graph.update_state(...)` then `invoke(None, fork)` |
| A node runs twice after resuming | You passed new input instead of `None` | `invoke(None, config)` |
| `next` is not empty but the run "finished" | The last run crashed or was edited | That is your resume point - call `invoke(None, config)` |
| State has keys you did not pass in | Reducers initialise their keys | Expect `[]` for an `operator.add` list, not a missing key |

**Good habits:** one `thread_id` per conversation, `MemorySaver` for demos and `SqliteSaver` for anything real, and
treat the history as append-only.
**Habits to avoid:** putting a `thread_id` in a global variable, and calling `update_state` to "fix" state that a node
should have computed.

## Notes and differences

A few things behave differently from what people expect, and they are worth saying out loud in class:

- **The graph re-runs from `START` on a normal call.** Persistence restores *state*, not *position*. Position only
  matters when a run stopped early - then `invoke(None, config)` continues from `next`.
- **`get_state_history` is newest-first.** The first item is the current head; the last item is the original input.
- **A rewind does not shrink the history.** Both branches stay in the list, because every checkpoint keeps its
  `parent_config`. It is a tree stored as a flat, append-only log.
- **History grows by one checkpoint per node, per run.** That is fine for teaching and needs a retention policy in
  production.
- **A checkpointer changes nothing about the graph's shape.** `graph_diagram.py` output is identical with and without
  one - because persistence is storage, not topology.

## Where the model goes

Nothing in this repo calls a model, and that is deliberate: persistence is about *where state is stored*, not about
what a node computes. Keeping the nodes deterministic means every output above is reproducible in class.

When you do want a real model, `llm.py` is already wired up. Example 1's `reply` node becomes:

```python
from llm import get_llm

def reply(state):
    llm = get_llm(temperature=0.3)
    text = llm.invoke(f"Facts about the user: {state['facts']}. Reply in one short sentence.").content
    return {"messages": [text]}
```

The graph, the checkpointer, the `thread_id` and the history are all unchanged. That is the point worth making:
**a node is a function from state to state, and the checkpointer does not care what is inside it.**

## What's next

Session 3: human-in-the-loop. Now that a graph can save its position, it can stop in the middle and wait for a person -
`interrupt()` to pause, `Command(resume=...)` to continue. After that, long-term memory with a `BaseStore`, and
LangSmith for tracing a run step by step.

The nice detail for Session 3: the reject-and-redirect pattern is Example 3's loop with a human where the reviewer is.
