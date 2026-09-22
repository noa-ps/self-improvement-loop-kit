# SILK UI - Visualize your loop

Local, read-only view of `loop-kit/scoreboard.jsonl`. Start it with `silk ui` in the harnessed repo. Prefer `http://127.0.0.1:9348`; if that port is busy, the command prints the URL it bound.

Nothing on this page is typed by hand. Nodes, filters, kinds, and the verdict come from `record-run` lines plus `scoreboard-summary`.

## Rail

**Filters**

| Row | JSONL field | Meaning |
| --- | --- | --- |
| `pass` / `fail` | `pass` | Probe exit code. Green node = pass, pink = fail. |
| Eight hex chars | `learned_hash` | Fingerprint of playbook `## Learned (probe-gated)` when that line was written. Same hash = same lesson set. After `silk learn` adds a bullet, later lines get a new hash. |

Click a row to show only those runs.

**Actions** — unique `actions` values (what the remediator reported). Click to filter.

**Runs** — scored plays, grouped as “lesson set” (same `## Learned (probe-gated)` fingerprint). Each row is run number, passed/failed, time, seconds to green.

**Trend** — human line for KEEP / REVERT / not enough runs / probe changed. One pass is not a trend. The probe command is labeled as the exam.

## Field

Each node is one JSONL line. Edges follow run order. The circle is a close-up of the same graph. Search matches any field on the line.

Empty board means no play has been recorded yet. First time: interview (`silk build` or `/self-improvement-loop-kit`), follow `playbook.md`, then `silk play --repo .`.
