# Codex locks

During a remediating `/loop` or `/goal`, do not write:

- the playbook (`playbook_path`)
- `loop-kit/loop.yaml`
- the probe command’s file
- `loop-kit/scoreboard.jsonl` (except via `record-run` append)

`CODEOWNERS` lists the same paths. Promotion is a later human PR using `promote.md`.
