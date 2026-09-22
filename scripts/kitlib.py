"""Shared helpers for Self Improvement Loop Kit. No network. No memory stores."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

LEARNED_HEADING = "## Learned (probe-gated)"
LEARNED_TITLE = "Learned (probe-gated)"
SEALED_HINTS = ("playbook", "probe", "loop.yaml", "scoreboard.jsonl")

SELF_GRADE_RE = re.compile(
    r"agent\s+says|looks\s+fixed|i\s+think\s+it.?s\s+(?:fine|fixed)|self[- ]?grade",
    re.I,
)
IN_SESSION_LEARN_RE = re.compile(
    r"update\s+(this\s+)?(file|runbook|playbook)|write\s+what\s+worked|remember\s+in\s+this\s+session|during[- ]loop|memory-store",
    re.I,
)


def kit_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_loop_schema() -> dict:
    return load_json(kit_root() / "schema" / "loop.schema.json")


def load_run_schema() -> dict:
    return load_json(kit_root() / "schema" / "run.schema.json")


def load_spec(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix in {".yaml", ".yml"}:
        spec = parse_simple_yaml(text)
    else:
        spec = json.loads(text)
    return _normalize_spec(spec)


def _normalize_spec(spec: dict) -> dict:
    probe = spec.get("probe")
    if isinstance(probe, dict):
        cmd = probe.get("command")
        if isinstance(cmd, bool):
            probe["command"] = "true" if cmd else "false"
    return spec


def parse_simple_yaml(text: str) -> dict:
    """Minimal YAML subset used by loop.yaml (no anchors, no merge)."""
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError("spec must be a mapping")
        return data
    except ImportError:
        return _tiny_yaml(text)


def _tiny_yaml(text: str) -> dict:
    lines: list[tuple[int, str]] = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        lines.append((indent, raw.strip()))
    data, _ = _parse_yaml_block(lines, 0, 0)
    if not isinstance(data, dict):
        raise ValueError("spec must be a mapping")
    return data


def _parse_yaml_block(lines: list[tuple[int, str]], i: int, min_indent: int):
    if i >= len(lines) or lines[i][0] < min_indent:
        return {}, i
    if lines[i][1].startswith("- "):
        seq: list = []
        while i < len(lines) and lines[i][0] >= min_indent and lines[i][1].startswith("- "):
            seq.append(_scalar(lines[i][1][2:].strip()))
            i += 1
        return seq, i
    mapping: dict = {}
    base = lines[i][0]
    while i < len(lines) and lines[i][0] == base and not lines[i][1].startswith("- "):
        key, _, rest = lines[i][1].partition(":")
        key, rest = key.strip(), rest.strip()
        i += 1
        if rest != "":
            mapping[key] = _scalar(rest)
            continue
        if i < len(lines) and lines[i][0] > base:
            child, i = _parse_yaml_block(lines, i, lines[i][0])
            mapping[key] = child
        else:
            mapping[key] = {}
    return mapping, i


def _scalar(value: str):
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def dump_yaml(data: dict) -> str:
    try:
        import yaml  # type: ignore

        return yaml.safe_dump(data, sort_keys=False)
    except ImportError:
        return _dump_tiny(data, 0)


def _dump_tiny(obj, indent: int) -> str:
    pad = "  " * indent
    if isinstance(obj, dict):
        lines = []
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                lines.append(f"{pad}{k}:")
                lines.append(_dump_tiny(v, indent + 1))
            else:
                lines.append(f"{pad}{k}: {_fmt(v)}")
        return "\n".join(lines) + ("\n" if indent == 0 else "")
    if isinstance(obj, list):
        lines = []
        for item in obj:
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}-")
                lines.append(_dump_tiny(item, indent + 1))
            else:
                lines.append(f"{pad}- {_fmt(item)}")
        return "\n".join(lines)
    return f"{pad}{_fmt(obj)}"


def _fmt(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str) and (
        ":" in v or v == "" or v in {"true", "false", "null"} or re.fullmatch(r"-?\d+", v)
    ):
        return json.dumps(v)
    return str(v)


def validate_required(spec: dict) -> list[str]:
    codes = []
    required = load_loop_schema()["required"]
    for key in required:
        if key not in spec or spec[key] in (None, "", [], {}):
            codes.append(f"MISSING_{key.upper()}")
    probe = spec.get("probe") or {}
    if isinstance(probe, dict) and not probe.get("command"):
        codes.append("NO_PROBE")
    elif "probe" not in spec:
        codes.append("NO_PROBE")
    promo = spec.get("promotion") or {}
    if promo.get("method") in {"during-loop", "during_loop"}:
        codes.append("IN_SESSION_LEARN")
    if promo.get("method") == "memory-store":
        codes.append("IN_SESSION_LEARN")
    if "promotion" not in spec or not promo:
        codes.append("NO_WRITEBACK")
    sb = spec.get("scoreboard") or {}
    if not sb.get("path"):
        codes.append("NO_SCOREBOARD")
    if spec.get("learned_section") not in (None, LEARNED_TITLE) and spec.get(
        "learned_section"
    ):
        if spec.get("learned_section") != LEARNED_TITLE:
            codes.append("NO_WRITEBACK")
    return codes


def lint_spec(spec: dict, *, playbook_text: str = "", promote_exists: bool = True) -> list[str]:
    codes = []
    codes.extend(validate_required(spec))

    probe_cmd = ""
    if isinstance(spec.get("probe"), dict):
        probe_cmd = str(spec["probe"].get("command") or "")
    if SELF_GRADE_RE.search(probe_cmd) or probe_cmd.strip().lower() in {
        "agent says so",
        "ask the agent",
    }:
        codes.append("SELF_GRADE")

    blob = playbook_text + "\n" + json.dumps(spec)
    if IN_SESSION_LEARN_RE.search(blob):
        codes.append("IN_SESSION_LEARN")

    promo = spec.get("promotion") or {}
    if promo.get("method") and promo.get("method") not in {"human-pr", "pass-gated"}:
        if "IN_SESSION_LEARN" not in codes:
            codes.append("IN_SESSION_LEARN")
    target = promo.get("target_path") or ""
    playbook = spec.get("playbook_path") or ""
    if target and playbook and Path(target) != Path(playbook):
        codes.append("NO_WRITEBACK")
    if spec.get("learned_section") != LEARNED_TITLE:
        codes.append("NO_WRITEBACK")
    if not promote_exists:
        codes.append("NO_WRITEBACK")

    deny = [str(x) for x in (spec.get("deny") or [])]
    sb_path = (spec.get("scoreboard") or {}).get("path") or ""
    sealed = True
    if playbook and not any(playbook in d or Path(playbook).name in d for d in deny):
        sealed = False
    if not any("probe" in d.lower() for d in deny):
        sealed = False
    if sb_path and not any("scoreboard" in d or sb_path in d for d in deny):
        sealed = False
    if not sealed:
        codes.append("PROBE_EDITABLE")

    # unique preserve order
    out = []
    for c in codes:
        if c not in out:
            out.append(c)
    return out


def learned_section_text(playbook: str) -> str:
    if LEARNED_HEADING not in playbook:
        return ""
    rest = playbook.split(LEARNED_HEADING, 1)[1]
    nxt = re.search(r"\n## ", rest)
    return rest if not nxt else rest[: nxt.start()]


def learned_hash(playbook: str) -> tuple[str, int]:
    section = learned_section_text(playbook)
    bullets = [ln for ln in section.splitlines() if ln.strip().startswith(("-", "*"))]
    digest = hashlib.sha256(section.encode("utf-8")).hexdigest()[:8]
    return digest, len(bullets)


def last_scoreboard_row(path: Path) -> dict | None:
    rows = load_jsonl(path)
    return rows[-1] if rows else None


def learn_bullet(row: dict) -> str:
    acts = [str(a) for a in (row.get("actions") or []) if a]
    via = " via " + ", ".join(acts) if acts else ""
    probe = str(row.get("probe") or "").strip()
    return f"- pass{via} (probe: {probe})"


def append_learned(playbook: str, bullet: str) -> str:
    text = ensure_learned_section(playbook)
    line = bullet if bullet.endswith("\n") else bullet + "\n"
    if not text.endswith("\n"):
        text += "\n"
    return text + line


def drop_last_learned(playbook: str) -> str:
    if LEARNED_HEADING not in playbook:
        return playbook
    pre, rest = playbook.split(LEARNED_HEADING, 1)
    nxt = re.search(r"\n## ", rest)
    section, tail = (rest, "") if not nxt else (rest[: nxt.start()], rest[nxt.start() :])
    lines = section.splitlines(keepends=True)
    idx = None
    for i, ln in enumerate(lines):
        if ln.strip().startswith(("-", "*")):
            idx = i
    if idx is None:
        return playbook
    del lines[idx]
    return pre + LEARNED_HEADING + "".join(lines) + tail


def ensure_learned_section(playbook: str) -> str:
    if LEARNED_HEADING in playbook:
        return playbook
    block = (
        f"\n{LEARNED_HEADING}\n"
        "\n"
        "Add bullets only via silk learn after a pass: true scoreboard line. "
        "Do not edit this section or the probe during remediation.\n"
    )
    return playbook.rstrip() + block + "\n"


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def median(nums: list[float]) -> float:
    if not nums:
        return 0.0
    s = sorted(nums)
    n = len(s)
    mid = n // 2
    if n % 2:
        return float(s[mid])
    return (s[mid - 1] + s[mid]) / 2.0


def summarize(rows: list[dict]) -> dict:
    if not rows:
        return {"verdict": "INSUFFICIENT_N", "groups": [], "probe": None}
    probes = {r.get("probe") for r in rows}
    if len(probes) > 1:
        return {"verdict": "PROBE_CHANGED", "groups": [], "probe": sorted(probes)}

    order: list[str] = []
    groups: dict[str, list] = {}
    for r in rows:
        h = r["learned_hash"]
        if h not in groups:
            order.append(h)
            groups[h] = []
        groups[h].append(r)

    packed = []
    for h in order:
        rs = groups[h]
        fails = sum(1 for x in rs if not x["pass"])
        packed.append(
            {
                "learned_hash": h,
                "n": len(rs),
                "fail_rate": fails / len(rs),
                "median_seconds": median([float(x["seconds_to_green"]) for x in rs]),
            }
        )

    verdict = "INSUFFICIENT_N"
    if len(packed) >= 2 and packed[-1]["n"] >= 3:
        prev, cur = packed[-2], packed[-1]
        better = cur["fail_rate"] < prev["fail_rate"] or (
            cur["fail_rate"] <= prev["fail_rate"]
            and cur["median_seconds"] < prev["median_seconds"]
        )
        verdict = "KEEP" if better else "REVERT"

    return {
        "verdict": verdict,
        "groups": packed,
        "probe": rows[0].get("probe"),
    }


def playbook_from_intake(data: dict) -> str:
    return (
        f"# {str(data['trigger']).strip()}\n\n"
        f"{str(data['steps']).strip()}\n\n"
        f"Do not:\n{str(data['must_not']).strip()}\n"
    )


def spec_from_intake(data: dict) -> dict:
    allow = [a.strip() for a in str(data.get("allow") or "").split(",") if a.strip()]
    if not allow:
        allow = ["remediate"]
    playbook = str(data.get("playbook_path") or "playbook.md")
    return {
        "trigger": str(data["trigger"]).strip(),
        "actor": str(data["actor"]).strip(),
        "playbook_path": playbook,
        "allow": allow,
        "deny": [
            playbook,
            "loop-kit/probe.sh",
            "loop-kit/scoreboard.jsonl",
            "loop-kit/loop.yaml",
        ],
        "probe": {"command": str(data["probe"]).strip()},
        "on_fail": str(data["on_fail"]).strip(),
        "budget": {
            "max_iterations": int(data["max_iterations"]),
            "blast": str(data["blast"]).strip(),
        },
        "promotion": {"method": "pass-gated", "target_path": playbook},
        "learned_section": LEARNED_TITLE,
        "scoreboard": {"path": "loop-kit/scoreboard.jsonl"},
    }
