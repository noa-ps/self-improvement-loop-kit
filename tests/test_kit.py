#!/usr/bin/env python3
"""WI-015: schema, lint, emit, record-run, summary, visualize, seals."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from http.client import HTTPConnection
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from kitlib import (  # noqa: E402
    LEARNED_HEADING,
    dump_yaml,
    learned_hash,
    lint_spec,
    load_jsonl,
    load_run_schema,
    load_spec,
    summarize,
    validate_required,
)


def run(args, **kw):
    return subprocess.run(
        args,
        cwd=kw.pop("cwd", ROOT),
        text=True,
        capture_output=True,
        **kw,
    )


class SchemaTests(unittest.TestCase):
    def test_missing_probe_promotion_scoreboard_rejected(self):
        spec = {
            "trigger": "x",
            "actor": "x",
            "playbook_path": "p.md",
            "allow": ["a"],
            "deny": ["p.md"],
            "on_fail": "stop",
            "budget": {"max_iterations": 1, "blast": "one"},
            "learned_section": "Learned (probe-gated)",
        }
        codes = validate_required(spec)
        self.assertIn("NO_PROBE", codes)
        self.assertTrue(any(c in {"NO_WRITEBACK", "MISSING_PROMOTION"} for c in codes))
        self.assertIn("NO_SCOREBOARD", codes)

    def test_during_loop_and_memory_store_rejected(self):
        base = load_spec(ROOT / "fixtures" / "good" / "loop.yaml")
        base["promotion"] = {"method": "during-loop", "target_path": base["playbook_path"]}
        self.assertIn("IN_SESSION_LEARN", validate_required(base))
        base["promotion"] = {"method": "memory-store", "target_path": base["playbook_path"]}
        self.assertIn("IN_SESSION_LEARN", validate_required(base))

    def test_example_run_line_has_required_fields(self):
        row = json.loads((ROOT / "fixtures" / "runs" / "example.jsonl").read_text().splitlines()[0])
        for key in load_run_schema()["required"]:
            self.assertIn(key, row)
        self.assertIsInstance(row["pass"], bool)


class LintTests(unittest.TestCase):
    def test_naive_prints_required_codes(self):
        proc = run(
            [
                sys.executable,
                str(SCRIPTS / "lint-loop"),
                str(ROOT / "fixtures" / "naive" / "loop.yaml"),
                "--playbook",
                str(ROOT / "fixtures" / "naive" / "playbook.md"),
            ]
        )
        self.assertNotEqual(proc.returncode, 0)
        text = proc.stdout + proc.stderr
        self.assertIn("IN_SESSION_LEARN", text)
        self.assertTrue("SELF_GRADE" in text or "NO_PROBE" in text)
        self.assertIn("NO_SCOREBOARD", text)

    def test_good_spec_exits_0(self):
        proc = run(
            [
                sys.executable,
                str(SCRIPTS / "lint-loop"),
                str(ROOT / "fixtures" / "good" / "loop.yaml"),
                "--playbook",
                str(ROOT / "fixtures" / "good" / "playbook.md"),
                "--promote",
                str(ROOT / "templates" / "promote.md"),
            ]
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OK", proc.stdout)

    def test_good_yaml_parses_lists_and_true_command(self):
        spec = load_spec(ROOT / "fixtures" / "good" / "loop.yaml")
        self.assertEqual(spec["allow"], ["rollback"])
        self.assertIn("playbook.md", spec["deny"])
        self.assertEqual(spec["probe"]["command"], "true")


class EmitTests(unittest.TestCase):
    def _emit(self, repo: Path) -> subprocess.CompletedProcess:
        playbook = repo / "playbook.md"
        playbook.write_text(
            "# checkout-5xx\n\nIf 5xx after a deploy, rollback this release.\n",
            encoding="utf-8",
        )
        spec_src = (ROOT / "fixtures" / "good" / "loop.yaml").read_text(encoding="utf-8")
        spec_path = repo / "spec.yaml"
        spec_path.write_text(spec_src, encoding="utf-8")
        return run(
            [
                sys.executable,
                str(SCRIPTS / "emit"),
                "--repo",
                str(repo),
                "--spec",
                str(spec_path),
            ]
        )

    def test_emit_paths_empty_scoreboard_no_visualize(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            proc = self._emit(repo)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            kit = repo / "loop-kit"
            for name in ("loop.yaml", "promote.md", "scoreboard.jsonl", "record-run"):
                self.assertTrue((kit / name).exists(), name)
            self.assertEqual((kit / "scoreboard.jsonl").read_text(encoding="utf-8"), "")
            self.assertFalse((kit / "visualize").exists())
            self.assertFalse((repo / "visualize").exists())
            spec = load_spec(kit / "loop.yaml")
            codes = lint_spec(
                spec,
                playbook_text=(repo / "playbook.md").read_text(encoding="utf-8"),
                promote_exists=True,
            )
            self.assertEqual(codes, [])
            pb = (repo / "playbook.md").read_text(encoding="utf-8")
            self.assertIn(LEARNED_HEADING, pb)
            self.assertNotIn("memory/MEMORY.md", proc.stdout)

    def test_patch_idempotent_on_actions(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self.assertEqual(self._emit(repo).returncode, 0)
            first = (repo / "playbook.md").read_text(encoding="utf-8")
            actions = first.split(LEARNED_HEADING, 1)[0]
            self.assertEqual(self._emit(repo).returncode, 0)
            second = (repo / "playbook.md").read_text(encoding="utf-8")
            self.assertEqual(second.split(LEARNED_HEADING, 1)[0], actions)
            self.assertEqual(second.count(LEARNED_HEADING), 1)

    def test_emit_does_not_wipe_existing_scoreboard(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self.assertEqual(self._emit(repo).returncode, 0)
            sb = repo / "loop-kit" / "scoreboard.jsonl"
            sb.write_text('{"ts":"keep"}\n', encoding="utf-8")
            self.assertEqual(self._emit(repo).returncode, 0)
            self.assertEqual(sb.read_text(encoding="utf-8"), '{"ts":"keep"}\n')

    def test_emit_writes_playbook_from_interview_body(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            spec_path = repo / "spec.yaml"
            spec_path.write_text(
                (ROOT / "fixtures" / "good" / "loop.yaml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            body = repo / "collected.md"
            body.write_text(
                "# checkout-5xx\n\nIf 5xx after a deploy, rollback this release.\n",
                encoding="utf-8",
            )
            proc = run(
                [
                    sys.executable,
                    str(SCRIPTS / "emit"),
                    "--repo",
                    str(repo),
                    "--spec",
                    str(spec_path),
                    "--playbook-body",
                    str(body),
                ]
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            pb = (repo / "playbook.md").read_text(encoding="utf-8")
            self.assertIn("rollback this release", pb)
            self.assertIn(LEARNED_HEADING, pb)

    def test_refuse_home_memory_paths(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / ".claude" / "projects" / "memory" / "MEMORY.md-repo"
            repo.mkdir(parents=True)
            (repo / "playbook.md").write_text("# p\n", encoding="utf-8")
            spec = (ROOT / "fixtures" / "good" / "loop.yaml").read_text(encoding="utf-8")
            (repo / "spec.yaml").write_text(spec, encoding="utf-8")
            proc = run(
                [
                    sys.executable,
                    str(SCRIPTS / "emit"),
                    "--repo",
                    str(repo),
                    "--spec",
                    str(repo / "spec.yaml"),
                ]
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("memory", (proc.stdout + proc.stderr).lower())


class RecordRunTests(unittest.TestCase):
    def test_append_only_and_exit_code(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / "playbook.md").write_text(
                "# p\n\n## Learned (probe-gated)\n\n", encoding="utf-8"
            )
            spec = load_spec(ROOT / "fixtures" / "good" / "loop.yaml")
            spec["probe"] = {"command": "false"}
            (repo / "loop-kit").mkdir()
            (repo / "loop-kit" / "loop.yaml").write_text(dump_yaml(spec), encoding="utf-8")
            env = os.environ.copy()
            first = run(
                [
                    sys.executable,
                    str(SCRIPTS / "record-run"),
                    "--repo",
                    str(repo),
                    "--spec",
                    "loop-kit/loop.yaml",
                    "--actions",
                    "rollback",
                ],
                cwd=repo,
                env=env,
            )
            self.assertEqual(first.returncode, 1, first.stdout + first.stderr)
            sb = repo / "loop-kit" / "scoreboard.jsonl"
            line1 = sb.read_text(encoding="utf-8")
            self.assertEqual(line1.count("\n"), 1)
            spec["probe"] = {"command": "true"}
            (repo / "loop-kit" / "loop.yaml").write_text(dump_yaml(spec), encoding="utf-8")
            second = run(
                [
                    sys.executable,
                    str(SCRIPTS / "record-run"),
                    "--repo",
                    str(repo),
                    "--spec",
                    "loop-kit/loop.yaml",
                ],
                cwd=repo,
            )
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            after = sb.read_text(encoding="utf-8")
            self.assertTrue(after.startswith(line1))
            rows = load_jsonl(sb)
            self.assertEqual(len(rows), 2)
            self.assertFalse(rows[0]["pass"])
            self.assertTrue(rows[1]["pass"])


class SummaryTests(unittest.TestCase):
    def test_keep_revert_probe_changed(self):
        keep = summarize(load_jsonl(ROOT / "fixtures" / "summary" / "keep.jsonl"))
        self.assertEqual(keep["verdict"], "KEEP")
        revert = summarize(load_jsonl(ROOT / "fixtures" / "summary" / "revert.jsonl"))
        self.assertEqual(revert["verdict"], "REVERT")
        changed = summarize(load_jsonl(ROOT / "fixtures" / "summary" / "probe-changed.jsonl"))
        self.assertEqual(changed["verdict"], "PROBE_CHANGED")
        proc = run(
            [
                sys.executable,
                str(SCRIPTS / "scoreboard-summary"),
                str(ROOT / "fixtures" / "summary" / "keep.jsonl"),
            ]
        )
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(proc.stdout.startswith("KEEP"))


class SilCliTests(unittest.TestCase):
    def test_sil_emits_from_json(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            answers = repo / "answers.json"
            answers.write_text(
                json.dumps(
                    {
                        "trigger": "5xx after deploy",
                        "steps": "Rollback the release.",
                        "must_not": "Do not restart blindly.",
                        "actor": "cursor",
                        "allow": "rollback",
                        "probe": "true",
                        "on_fail": "revert",
                        "max_iterations": 3,
                        "blast": "one pod",
                    }
                ),
                encoding="utf-8",
            )
            proc = run(
                [
                    sys.executable,
                    str(SCRIPTS / "silk"),
                    "build",
                    "--repo",
                    str(repo),
                    "--json",
                    str(answers),
                ],
                env={**os.environ, "SILK_NO_VIZ": "1"},
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("SILK | Self Improvement Loop Kit", proc.stdout)
            self.assertNotIn("SOL", proc.stdout)
            pb = (repo / "playbook.md").read_text(encoding="utf-8")
            self.assertIn("Rollback the release", pb)
            self.assertIn(LEARNED_HEADING, pb)
            self.assertTrue((repo / "loop-kit" / "loop.yaml").exists())
            self.assertEqual((repo / "loop-kit" / "scoreboard.jsonl").read_text(encoding="utf-8"), "")
            self.assertIn("scoreboard.jsonl", proc.stdout)

    def test_silk_review_can_edit_before_emit(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            stdin = "\n".join(
                [
                    "5xx after deploy",
                    "Rollback the release.",
                    "Do not restart blindly.",
                    "cursor",
                    "rollback",
                    "true",
                    "revert",
                    "3",
                    "one pod",
                    "1",
                    "5xx on checkout after deploy",
                    "done",
                    "",
                ]
            )
            proc = run(
                [sys.executable, str(SCRIPTS / "silk"), "build", "--repo", str(repo)],
                input=stdin,
                env={**os.environ, "SILK_NO_VIZ": "1"},
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("review", proc.stdout)
            pb = (repo / "playbook.md").read_text(encoding="utf-8")
            self.assertIn("5xx on checkout after deploy", pb)
            self.assertNotIn("# 5xx after deploy\n", pb)

    def test_silk_install_flag_skips_interview(self):
        proc = run([sys.executable, str(SCRIPTS / "silk"), "install"])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("first use", proc.stdout)
        self.assertNotIn("What should start this loop?", proc.stdout)
        help_proc = run([sys.executable, str(SCRIPTS / "silk")])
        self.assertEqual(help_proc.returncode, 0, help_proc.stdout + help_proc.stderr)
        self.assertIn("silk install", help_proc.stdout)
        self.assertIn("silk build", help_proc.stdout)
        self.assertIn("silk ui", help_proc.stdout)
        self.assertNotIn("What should start this loop?", help_proc.stdout)


class VisualizeTests(unittest.TestCase):
    def test_binds_loopback_only(self):
        src = (SCRIPTS / "visualize-server").read_text(encoding="utf-8")
        self.assertIn('HOST = "127.0.0.1"', src)
        self.assertNotIn("0.0.0.0", src)
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        proc = run([sys.executable, str(SCRIPTS / "visualize-server"), "--once", "--port", str(port)])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("127.0.0.1", proc.stdout)

    def test_empty_state_and_readonly_and_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            sb = repo / "loop-kit" / "scoreboard.jsonl"
            sb.parent.mkdir()
            sb.write_text("", encoding="utf-8")
            sock = socket.socket()
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
            sock.close()
            proc = subprocess.Popen(
                [
                    sys.executable,
                    str(SCRIPTS / "visualize-server"),
                    "--repo",
                    str(repo),
                    "--port",
                    str(port),
                ],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                deadline = time.time() + 3
                while time.time() < deadline:
                    try:
                        c = HTTPConnection("127.0.0.1", port, timeout=0.2)
                        c.request("GET", "/")
                        html = c.getresponse().read().decode()
                        break
                    except OSError:
                        time.sleep(0.05)
                else:
                    self.fail("server did not start")
                self.assertIn("Self Improvement Loop Kit", html)
                self.assertIn("silk play", html)
                self.assertIn("silk build", html)
                self.assertNotIn("loop-nodes.html", html)
                self.assertNotIn("frontend-dome", html)
                c = HTTPConnection("127.0.0.1", port, timeout=1)
                c.request("GET", "/scoreboard.jsonl")
                body = c.getresponse().read()
                self.assertEqual(body, b"")
                c = HTTPConnection("127.0.0.1", port, timeout=1)
                c.request("POST", "/", body=b"{}", headers={"Content-Length": "2"})
                self.assertEqual(c.getresponse().status, 405)
            finally:
                proc.terminate()
                proc.wait(timeout=3)

    def test_shipped_ui_has_no_dome(self):
        viz = ROOT / "visualize"
        self.assertFalse((viz / "loop-nodes.html").exists())
        blob = ""
        for p in viz.iterdir():
            if p.is_file():
                blob += p.read_text(encoding="utf-8", errors="ignore")
        self.assertNotIn("frontend-dome", blob)
        self.assertNotIn("loop-nodes.html", blob)
        self.assertNotIn("directory.css", blob)


class SkillTests(unittest.TestCase):
    def test_skill_closing_names_writeback(self):
        paths = [
            ROOT / "self-improvement-loop-kit" / "SKILL.md",
            ROOT / ".agents" / "skills" / "self-improvement-loop-kit" / "SKILL.md",
            ROOT / ".cursor" / "skills" / "self-improvement-loop-kit" / "SKILL.md",
        ]
        for path in paths:
            skill = path.read_text(encoding="utf-8")
            self.assertIn("Learned (probe-gated)", skill, path)
            self.assertIn("scoreboard.jsonl", skill, path)
            self.assertIn("Cursor", skill, path)
            self.assertIn("What should start this loop?", skill, path)
            self.assertIn("Install gate", skill, path)
            self.assertIn("```\nsilk install\n```", skill, path)
            self.assertIn("silk build", skill, path)
            self.assertNotIn("./scripts/install", skill, path)
            self.assertNotIn("silk --install", skill, path)
            self.assertIn("AskQuestion", skill, path)
            self.assertIn("Do **not** call `AskQuestion`", skill, path)
        self.assertTrue((ROOT / "scripts" / "silk").exists())
        self.assertTrue((ROOT / "scripts" / "install").exists())
        inst = (ROOT / "scripts" / "install").read_text(encoding="utf-8")
        self.assertIn(".claude/skills", inst)
        self.assertIn(".agents/skills", inst)
        self.assertIn(".cursor/skills", inst)
        self.assertIn(".cursor/commands", inst)
        dry = (ROOT / "fixtures" / "interview-dry-run.md").read_text(encoding="utf-8")
        self.assertIn("Learned (probe-gated)", dry)
        self.assertIn("scoreboard.jsonl", dry)
        self.assertIn("silk install", dry)
        self.assertIn("silk build", dry)

    def test_learned_hash_changes_after_bullet(self):
        empty = "# loop\n\n## Learned (probe-gated)\n"
        filled = empty + "- After a deploy, rollback first.\n"
        h0, n0 = learned_hash(empty)
        h1, n1 = learned_hash(filled)
        self.assertEqual(n0, 0)
        self.assertGreaterEqual(n1, 1)
        self.assertNotEqual(h0, h1)
        rows = load_jsonl(ROOT / "fixtures" / "summary" / "probe-changed.jsonl")
        self.assertTrue(any(r["learned_hash"] != rows[0]["learned_hash"] for r in rows[1:]))

    def test_deny_hook_blocks_playbook(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "deny-write.py"), "playbook.md"],
            input=json.dumps({"tool_input": {"file_path": "/tmp/playbook.md"}}),
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 2)


class ClosedLoopTests(unittest.TestCase):
    def _repo(self, td: Path, jsonl: str, playbook: str) -> Path:
        repo = td
        (repo / "loop-kit").mkdir()
        (repo / "loop-kit" / "loop.yaml").write_text(
            (ROOT / "fixtures" / "good" / "loop.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (repo / "loop-kit" / "scoreboard.jsonl").write_text(jsonl, encoding="utf-8")
        (repo / "playbook.md").write_text(playbook, encoding="utf-8")
        return repo

    def test_learn_requires_pass(self):
        with tempfile.TemporaryDirectory() as td:
            fail = (
                '{"ts":"t","loop_id":"x","probe":"true","pass":false,'
                '"seconds_to_green":1,"actions":["restart"],'
                '"learned_hash":"aaaa0000","learned_count":0}\n'
            )
            repo = self._repo(Path(td), fail, "# loop\n")
            yaml_b = (repo / "loop-kit" / "loop.yaml").read_bytes()
            sb_b = (repo / "loop-kit" / "scoreboard.jsonl").read_bytes()
            proc = run(
                [sys.executable, str(SCRIPTS / "learn"), "--repo", str(repo)]
            )
            self.assertEqual(proc.returncode, 2)
            self.assertNotIn("- pass", (repo / "playbook.md").read_text())
            self.assertEqual((repo / "loop-kit" / "loop.yaml").read_bytes(), yaml_b)
            self.assertEqual((repo / "loop-kit" / "scoreboard.jsonl").read_bytes(), sb_b)

    def test_learn_appends_one_bullet_from_line(self):
        with tempfile.TemporaryDirectory() as td:
            ok = (ROOT / "fixtures" / "runs" / "example.jsonl").read_text(encoding="utf-8")
            if not ok.endswith("\n"):
                ok += "\n"
            repo = self._repo(Path(td), ok, "# loop\n")
            proc = run(
                [sys.executable, str(SCRIPTS / "learn"), "--repo", str(repo)]
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            body = (repo / "playbook.md").read_text(encoding="utf-8")
            self.assertIn(LEARNED_HEADING, body)
            self.assertIn("- pass via rollback (probe: true)", body)
            self.assertEqual(body.count("- pass via rollback"), 1)

    def test_verdict_keep_and_revert(self):
        learned = (
            "# loop\n\n## Learned (probe-gated)\n\n"
            "- keep this\n- drop me\n"
        )
        with tempfile.TemporaryDirectory() as td:
            keep = (ROOT / "fixtures" / "summary" / "keep.jsonl").read_text(encoding="utf-8")
            repo = self._repo(Path(td), keep, learned)
            proc = run(
                [sys.executable, str(SCRIPTS / "verdict"), "--repo", str(repo)]
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("KEEP", proc.stdout)
            self.assertIn("- drop me", (repo / "playbook.md").read_text())
        with tempfile.TemporaryDirectory() as td:
            rev = (ROOT / "fixtures" / "summary" / "revert.jsonl").read_text(encoding="utf-8")
            repo = self._repo(Path(td), rev, learned)
            yaml_b = (repo / "loop-kit" / "loop.yaml").read_bytes()
            sb_b = (repo / "loop-kit" / "scoreboard.jsonl").read_bytes()
            proc = run(
                [sys.executable, str(SCRIPTS / "verdict"), "--repo", str(repo)]
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("REVERT", proc.stdout)
            body = (repo / "playbook.md").read_text()
            self.assertIn("- keep this", body)
            self.assertNotIn("- drop me", body)
            self.assertEqual((repo / "loop-kit" / "loop.yaml").read_bytes(), yaml_b)
            self.assertEqual((repo / "loop-kit" / "scoreboard.jsonl").read_bytes(), sb_b)
        with tempfile.TemporaryDirectory() as td:
            chg = (ROOT / "fixtures" / "summary" / "probe-changed.jsonl").read_text(
                encoding="utf-8"
            )
            repo = self._repo(Path(td), chg, learned)
            proc = run(
                [sys.executable, str(SCRIPTS / "verdict"), "--repo", str(repo)]
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("PROBE_CHANGED", proc.stdout)
            self.assertIn("- drop me", (repo / "playbook.md").read_text())

    def test_play_pass_learns_fail_skips(self):
        with tempfile.TemporaryDirectory() as td:
            repo = self._repo(Path(td), "", "# loop\n")
            (repo / "loop-kit" / "scoreboard.jsonl").write_text("", encoding="utf-8")
            proc = run(
                [
                    sys.executable,
                    str(SCRIPTS / "play"),
                    "--repo",
                    str(repo),
                    "--actions",
                    "rollback",
                ]
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            rows = load_jsonl(repo / "loop-kit" / "scoreboard.jsonl")
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0]["pass"])
            self.assertIn("- pass via rollback (probe: true)", (repo / "playbook.md").read_text())
            self.assertIn("INSUFFICIENT_N", proc.stdout)
        with tempfile.TemporaryDirectory() as td:
            repo = self._repo(Path(td), "", "# loop\n")
            yaml = (repo / "loop-kit" / "loop.yaml").read_text(encoding="utf-8")
            (repo / "loop-kit" / "loop.yaml").write_text(
                yaml.replace('command: "true"', 'command: "false"'),
                encoding="utf-8",
            )
            (repo / "loop-kit" / "scoreboard.jsonl").write_text("", encoding="utf-8")
            proc = run(
                [sys.executable, str(SCRIPTS / "play"), "--repo", str(repo)]
            )
            self.assertNotEqual(proc.returncode, 0)
            rows = load_jsonl(repo / "loop-kit" / "scoreboard.jsonl")
            self.assertEqual(len(rows), 1)
            self.assertFalse(rows[0]["pass"])
            self.assertNotIn("- pass", (repo / "playbook.md").read_text())

    def test_play_template_exists(self):
        text = (ROOT / "templates" / "play.github-action.yml").read_text(encoding="utf-8")
        self.assertIn("silk play", text)
        self.assertIn("workflow_dispatch", text)
        self.assertIn("schedule", text)


if __name__ == "__main__":
    unittest.main()
