---
name: self-improvement-loop-kit
description: >
  Interview for a self-improving loop (playbook + rails), then emit via silk.
  Use when the user wants /self-improvement-loop-kit, a probe-gated playbook,
  or to fill the SILK questions in Cursor, Claude Code, or Codex.
---

# Self Improvement Loop Kit

Clients: **Claude Code**, **Codex**, or **Cursor**. Same `scripts/` — do not fork lint, emit, record-run, or `silk`.

You **interview in this chat**, then emit. You do not run `/loop`. You do not write scoreboard lines. You do not build or populate the visualizer.

CLI `silk` is the other door to the same emit. If they already ran `silk` and have the closing block, do not interview again.

## First turn (mandatory)

**Install gate.** If `silk` is not on `PATH`, or the Claude / Codex / Cursor skill links are missing, do **not** interview. Tell them to run:

```
silk install
```

Then **stop**. Do not start the interview. If the `silk` command is not found, run this kit’s `silk install` yourself — do not print a path.

When install is already done:

Do **not** call `AskQuestion` or `AskUserQuestion`. Do **not** open a canvas. Do **not** open `http://127.0.0.1:8766`. Do **not** dump all nine as a markdown list and stop.

Ask **question 1 only**, then wait:

1. What should start this loop?

Then one at a time, waiting for each answer:

2. What should the agent do, step by step?
3. What must it not do?
4. Who runs it? (`cursor` / `claude-code` / `codex` only)
5. Allowed verbs? (comma-separated)
6. Shell command that means healthy?
7. If that command fails? (`revert` / `stop` / `page` only)
8. Max tries? (positive integer)
9. Blast radius?

If they send several answers at once, take them and continue from the first missing field. They may say “edit N” at any time and change that answer.

Do not copy their answers into this kit’s files. Answers live only in the consumer repo after emit.

## Review, then emit

After all nine, print a numbered review (question + their answer). Ask: type a number to edit, or `done` to emit.

On `done`, create `loop-kit/` if needed, write `loop-kit/.intake.json` in the **consumer** repo (cwd) with keys:

`trigger`, `steps`, `must_not`, `actor`, `allow`, `probe`, `on_fail`, `max_iterations`, `blast`

`max_iterations` is a number. Then from that repo:

```
silk build --json loop-kit/.intake.json --repo .
```

If `silk` is not on `PATH`, tell them `silk install`. Do not tell them to re-type the nine in the CLI.

Print silk’s stdout (closing block). Stop. Do not run `/loop`.

## After emit

If they already have the closing block, do not repeat the interview. You may confirm emit created `loop-kit/` and `playbook.md`.

You do **not** run the Play from this interview skill. The beats are:

1. **Play** — a normal agent turn. Paste `playbook.md`. The agent runs until the probe passes or hits the budget. Do not edit the probe, `loop.yaml`, or prior JSONL.
2. **Pass** — the probe command exits clean. That is the only yes.
3. **Learn** — after a real pass, `silk play --repo .` records the line and promotes one lesson. The next Play reads the playbook.

## Hard rules

- Playbook in git is the improve-base (written by `silk` / emit).
- Remediator must not edit playbook, probe, `loop.yaml`, or prior JSONL.
- Kit does not execute the incident.
- Never write a specific consumer project’s information, affiliation, or reference into SILK. User answers stay in the consumer repo.
- Lessons only under `## Learned (probe-gated)` via `silk learn` after a `pass: true` scoreboard line. `silk verdict` keeps or drops the last bullet. Evidence is `loop-kit/scoreboard.jsonl`. Not memory.
