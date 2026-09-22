# Cursor locks

During a remediating Agent turn that follows the playbook, do not write:

- the playbook (`playbook_path`)
- `loop-kit/loop.yaml`
- the probe command’s file
- `loop-kit/scoreboard.jsonl` (except via `record-run` append)

Do not put lessons in Cursor memory or an Agent Store. Promotion is a later human PR using `promote.md`.
`CODEOWNERS` lists the same sealed paths.
