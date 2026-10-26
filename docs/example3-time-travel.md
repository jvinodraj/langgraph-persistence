# Example 3 — diagrams

Three views of `example3_time_travel.py`, from shape to behaviour.

---

## 1. The graph shape

What `build_graph()` compiles. Nothing here is about persistence — this is the same loop shape as Session 1.

```mermaid
flowchart TD
    START([START]) --> write
    write["<b>write</b><br/>drafts += 'Draft ' + (attempts+1)<br/>attempts += 1"]
    write --> review["<b>review</b><br/>feedback = 'Not good enough - try again.'"]
    review --> decide{"<b>should_continue</b><br/>feedback == 'OK'<br/>or attempts &gt;= 3 ?"}
    decide -->|"yes"| END([END])
    decide -->|"no"| write
```

`should_continue` is a router, not a node. It has no state of its own and returns a name, not an update.
The `path_map={"write": "write", END: END}` is what gives both branches a label in the Mermaid output.

---

## 2. The checkpoint timeline of the original run

`graph.invoke({...}, config)` writes **8 checkpoints**. Read top to bottom.

```mermaid
flowchart TD
    C0["(1) __start__<br/><i>your input: attempts 0, drafts []</i>"]
    C1["(2) next: write<br/>attempts 0 · drafts []"]
    C2["(3) next: review<br/>attempts 1 · drafts [Draft 1]"]
    C3["(4) next: write<br/>attempts 1 · drafts [Draft 1]"]
    C4["(5) next: review<br/>attempts 2 · drafts [Draft 1, Draft 2]"]
    C5["(6) next: write<br/>attempts 2 · drafts [Draft 1, Draft 2]"]
    C6["(7) next: review<br/>attempts 3 · drafts [Draft 1, Draft 2, Draft 3]"]
    C7["(8) next: ( )<br/>done · attempts 3"]

    C0 --> C1 --> C2 --> C3 --> C4 --> C5 --> C6 --> C7

    classDef target fill:#ffe9b0,stroke:#b8860b,stroke-width:2px
    class C3 target
```

Two things to read off it:

- **`next` says where the run would continue.** `( )` means finished. This is the field that makes resume possible.
- Checkpoint **(4)** is the one the code picks: `next == ("write",)` and `attempts == 1`. It is highlighted.
- The run stops at **(7)**, not by writing a fourth draft: `attempts` is already 3 when `should_continue` is asked, so it returns `END`.

---

## 3. The fork — replay vs rewind

Both start from checkpoint **(4)**. One changes nothing; the other edits the state first.

```mermaid
flowchart TD
    C0["(1) __start__"] --> C1["(2) attempts 0"]
    C1 --> C2["(3) attempts 1 · [Draft 1]"]
    C2 --> C3["(4) attempts 1 · [Draft 1]<br/><b>rewind target</b>"]
    C3 --> C4["(5) attempts 2 · [Draft 1, Draft 2]"]
    C4 --> C5["(6) attempts 2 · [Draft 1, Draft 2]"]
    C5 --> C6["(7) attempts 3 · [Draft 1, Draft 2, Draft 3]"]
    C6 --> C7["(8) done<br/>[Draft 1, Draft 2, Draft 3]"]

    C3 -.->|"(2) replay<br/>invoke(None, C3.config)"| R1["walks write → review → ... again"]
    R1 -.-> R2["same ending<br/>[Draft 1, Draft 2, Draft 3]"]

    C3 ==>|"(3) rewind<br/>update_state(C3, attempts=0)"| F["fork<br/>attempts 0 · [Draft 1]"]
    F ==> G["attempts 1 · [Draft 1, <b>Draft 1</b>]"]
    G ==> H["attempts 2 · [Draft 1, Draft 1, Draft 2]"]
    H ==> I["attempts 3 · [Draft 1, Draft 1, Draft 2, Draft 3]"]
    I ==> J["done<br/>[Draft 1, Draft 1, Draft 2, Draft 3]"]

    classDef target fill:#ffe9b0,stroke:#b8860b,stroke-width:2px
    class C3 target
    classDef branch fill:#e3f2e1,stroke:#4a7c46
    class F,G,H,I,J branch
```

The duplicate **`Draft 1`** is the whole proof: after `update_state` sets `attempts` back to `0`, `write`
recomputes `OFFLINE_DRAFTS[0]` and appends it to a `drafts` list that still holds the first one. The
`operator.add` reducer keeps both.

The solid chain is never touched. `update_state` did not delete or edit checkpoint (4) — it wrote a **new**
checkpoint whose `parent_config` points at (4), and returned the config that addresses it.

### How the history grows

| After | Checkpoints | Added |
|---|---|---|
| original run | 8 | — |
| replay | 13 | +5 |
| `update_state` | 14 | +1 (the fork) |
| rewound run | **20** | +6 |

`graph.get_state_history(config)` now returns 20 entries, newest first. Both branches are in that flat list —
`parent_config` is what recovers the tree.

---

## 4. The five calls, as a cheat sheet

```mermaid
flowchart LR
    A["invoke(input, config)"] --> A2["restore the thread's latest<br/>checkpoint, then run<br/><b>from START</b>"]
    B["invoke(None, config)"] --> B2["restore that checkpoint<br/>and continue at <b>next</b>"]
    C["get_state(config)"] --> C2["newest StateSnapshot<br/>values · next · config · parent_config"]
    D["get_state_history(config)"] --> D2["every checkpoint<br/><b>newest first</b>"]
    E["update_state(config, values)"] --> E2["write a new checkpoint that<br/>forks here · <b>returns a config</b>"]
```

The distinction in the first two rows is the one that gets misremembered: a checkpointer does not make
`invoke` resume mid-graph. It restores **state**. Continuing at `next` is a separate, explicit call.
