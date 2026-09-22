# Promote a lesson

After `record-run` appends `"pass": true`, run:

```
silk learn
```

That appends **one** bullet under playbook `## Learned (probe-gated)`, built only from that line’s `actions` and `probe`.

Do **not** edit `probe`, `loop.yaml`, or prior JSONL lines. Do **not** write Learned while still remediating.

After later runs, apply the board verdict:

```
silk verdict
```

`KEEP` leaves the bullet. `REVERT` deletes the last Learned bullet. `INSUFFICIENT_N` and `PROBE_CHANGED` write nothing.
