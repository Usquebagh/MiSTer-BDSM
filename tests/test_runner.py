import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from runner import engine


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.core = self.root / "core"
        (self.core / "rtl").mkdir(parents=True)
        (self.core / "rtl/test.sv").write_text("original RTL\n")
        self.adapter_dir = self.root / "adapter"
        self.adapter_dir.mkdir()
        self.check = {"id": "test.assertion", "suite": "smoke", "required": True, "mode": "test", "timeout": 5,
                      "tools": [], "expectation": "Explicit expectation", "reference": "Independent fixture"}
        self.adapter = {"schema_version": 1, "id": "fixture", "version": "1", "source_roots": ["rtl"],
                        "source_files": [], "required_files": ["rtl/test.sv"], "limitations": ["Synthetic runner test"],
                        "checks": [self.check]}
        self.manifest = self.adapter_dir / "adapter.json"
        self.write_manifest()

    def tearDown(self):
        self.temp.cleanup()

    def write_manifest(self):
        self.manifest.write_text(json.dumps(self.adapter))

    def harness(self, event, code):
        (self.adapter_dir / "check.py").write_text("import json\nprint('BDSM ' + json.dumps(" + repr(event) + "))\nraise SystemExit(" + str(code) + ")\n")

    def execute(self):
        return engine.run_check(self.check, self.core, self.adapter_dir, self.root, 1)

    def test_required_skip_and_warning_never_satisfy_gate(self):
        self.assertEqual(engine.gate([]), (3, "INCOMPLETE"))
        for status in ("SKIP", "WARNING"):
            self.assertEqual(engine.gate([{"id": "x", "status": status, "required": True}]), (3, "INCOMPLETE"))
        self.assertEqual(engine.gate([{"id": "x", "status": "SKIP", "required": False}]), (0, "SATISFIED"))

    def test_tool_error_and_build_failure_exit_codes(self):
        self.assertEqual(engine.gate([{"id": "build.timing", "status": "FAIL", "required": True}])[0], 4)
        self.assertEqual(engine.gate([{"id": "x", "status": "FAIL", "required": True}])[0], 1)
        self.assertEqual(engine.gate([{"id": "x", "status": "ERROR", "required": True}])[0], 2)

    def test_assertion_is_fail_but_crash_after_pass_is_error(self):
        event = {"status": "FAIL", "cycle": 37, "label": "wrong_byte", "expected": 2, "observed": 3}
        self.harness(event, 1)
        self.assertEqual(self.execute()["status"], "FAIL")
        self.harness({"status": "PASS"}, 1)
        self.assertEqual(self.execute()["status"], "ERROR")

    def test_missing_or_malformed_evidence_is_error(self):
        (self.adapter_dir / "check.py").write_text("print('started successfully')\n")
        self.assertEqual(self.execute()["status"], "ERROR")

    def test_structured_warning_is_retained_and_blocks_required_gate(self):
        self.harness({"status": "WARNING", "reason": "Unreviewed lint diagnostic"}, 0)
        result = self.execute()
        self.assertEqual(result["status"], "WARNING")
        self.assertEqual(engine.gate([result])[0], 3)

    def test_audio_export_preserves_integer_samples_and_excludes_unlisted_game(self):
        import struct
        import wave
        folder = self.core / "build/sound"
        folder.mkdir(parents=True)
        data = struct.pack("<hhh", -32768, 0, 32767)
        with wave.open(str(folder / "synthetic.wav"), "wb") as audio:
            audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(96000); audio.writeframes(data)
        (folder / "game.wav").write_bytes(b"private game output")
        result = {}
        engine.retain_synthetic_audio({"suite": "audio", "audio_artifacts": ["build/sound/synthetic.wav"]}, self.core, self.root, result)
        self.assertEqual((self.root / "audio/synthetic.pcm").read_bytes(), data)
        self.assertEqual(result["audio_captures"][0]["sample_rate_hz"], 96000)
        self.assertFalse((self.root / "audio/game.wav").exists())
        with self.assertRaises(ValueError):
            engine.retain_synthetic_audio({"suite": "audio", "rom": "game.zip"}, self.core, self.root, {})

    def test_legacy_success_without_marker_is_error(self):
        script = self.core / "legacy.sh"
        script.write_text("#!/bin/bash\necho started\n")
        check = {**self.check, "script": "legacy.sh", "markers": ["PASS: actual assertion"]}
        del check["mode"]
        result = engine.run_check(check, self.core, self.adapter_dir, self.root, 1)
        self.assertEqual(result["status"], "ERROR")

    def test_missing_rom_is_skip_and_missing_tool_is_error(self):
        check = {**self.check, "rom": "private.zip"}
        self.assertEqual(engine.run_check(check, self.core, self.adapter_dir, self.root, 1)["status"], "SKIP")
        check = {**self.check, "tools": ["mister-bdsm-nonexistent-tool"]}
        self.assertEqual(engine.run_check(check, self.core, self.adapter_dir, self.root, 1)["status"], "ERROR")

    def test_snapshot_uses_content_hash_and_leaves_source_untouched(self):
        files = engine.inventory(self.core, self.adapter)
        destination = self.root / "snapshot"
        engine.snapshot(self.core, destination, files)
        (destination / "rtl/test.sv").write_text("mutant\n")
        self.assertEqual((self.core / "rtl/test.sv").read_text(), "original RTL\n")
        self.assertNotEqual(engine.input_hash(engine.inventory(destination, self.adapter)), engine.input_hash(files))
        (self.core / "rtl/test.sv").write_text("changed before copy\n")
        with self.assertRaises(ValueError):
            engine.snapshot(self.core, self.root / "racy-copy", files)

    def test_manifest_traversal_duplicate_and_symlink_rejected(self):
        self.adapter["source_files"] = ["../escape"]
        self.write_manifest()
        with self.assertRaises(ValueError):
            engine.load_adapter(self.manifest)
        self.adapter["source_files"] = []
        self.adapter["checks"].append(self.check)
        self.write_manifest()
        with self.assertRaises(ValueError):
            engine.load_adapter(self.manifest)
        os.symlink(self.core / "rtl/test.sv", self.core / "rtl/link.sv")
        with self.assertRaises(ValueError):
            engine.inventory(self.core, self.adapter)

    def test_timeout_is_error_and_kills_child_process_group(self):
        marker = self.root / "escaped-child"
        child = "import time,pathlib; time.sleep(1); pathlib.Path(" + repr(str(marker)) + ").write_text('escaped')"
        parent = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c'," + repr(child) + "]); time.sleep(5)"
        result = engine.process([sys.executable, "-c", parent], self.core, self.root / "timeout.log", 0.1)
        self.assertEqual(result["status"], "ERROR")
        # Reap-time grace is shorter than the child's write deadline; wait in a harmless subprocess.
        import subprocess
        subprocess.run([sys.executable, "-c", "import time; time.sleep(1.1)"], check=True)
        self.assertFalse(marker.exists())

    def test_source_or_snapshot_changes_invalidate_run(self):
        for change in ("source", "snapshot"):
            with patch.object(engine, "tools_metadata", return_value={}), patch.object(engine, "git_metadata", return_value={}):
                session = engine.Session(self.core, self.manifest, self.root / "results", 1)
            target = self.core if change == "source" else session.frozen
            (target / "rtl/test.sv").write_text("changed\n")
            code = session.finalize([{**self.check, "status": "PASS"}], "development")
            self.assertEqual(code, 2)
            report = json.loads((session.out / "results.json").read_text())
            self.assertEqual(report["gate"], "ERROR")
            self.assertFalse(session.work.exists())
            (self.core / "rtl/test.sv").write_text("original RTL\n")

    def test_required_skip_blocks_quartus_invocation(self):
        self.adapter["checks"] = [{"id": "reference.missing", "suite": "reference", "required": True,
                                   "expectation": "Independent audio evidence", "reference": "Absent", "skip_reason": "No reference"}]
        self.adapter["build"] = {"command": ["do-not-execute"], "artifact": "output/new.rbf"}
        self.write_manifest()
        with patch.object(engine, "tools_metadata", return_value={}), patch.object(engine, "git_metadata", return_value={}):
            session = engine.Session(self.core, self.manifest, self.root / "results", 1)
        with patch.object(engine, "process", side_effect=AssertionError("Quartus must not start")):
            self.assertEqual(session.build(), 3)
        self.assertEqual(session.report["build"]["status"], "BLOCKED")

    def test_surviving_and_invalid_mutants_do_not_pass_campaign(self):
        self.adapter["mutations"] = [{"id": "fault", "check": self.check["id"], "file": "rtl/test.sv",
                                      "old": "original RTL", "new": "broken RTL", "failure_label": "assertion", "reason": "Test fault"}]
        self.write_manifest()
        for status in ("PASS", "ERROR"):
            with patch.object(engine, "tools_metadata", return_value={}), patch.object(engine, "git_metadata", return_value={}):
                session = engine.Session(self.core, self.manifest, self.root / "results", 1)
            baseline = [{**self.check, "status": "PASS"}]
            mutant = [{**self.check, "status": status}]
            with patch.object(session, "run", side_effect=[baseline, mutant, mutant]):
                code = session.mutate(2)
            self.assertEqual(code, 1 if status == "PASS" else 2)
            self.assertEqual((self.core / "rtl/test.sv").read_text(), "original RTL\n")

    def test_timing_gate_rejects_missing_constraints_and_negative_slack(self):
        summary = "\n".join("Type : " + kind + "\nSlack : 0.5\nTNS : 0" for kind in ("Setup", "Hold", "Recovery", "Removal", "Minimum Pulse Width"))
        labels = ("Illegal Clocks", "Unconstrained Clocks", "Unconstrained Input Port Paths", "Unconstrained Output Port Paths")
        report = "\n".join("; " + label + " ; 0 ; 0 ;" for label in labels)
        self.assertEqual(engine.timing_gate(summary, report)["worst_slack_ns"]["Setup"], 0.5)
        with self.assertRaises(ValueError):
            engine.timing_gate(summary, report.replace("Output Port Paths ; 0", "Output Port Paths ; 1"))
        with self.assertRaises(ValueError):
            engine.timing_gate(summary.replace("Slack : 0.5", "Slack : -0.1", 1), report)
        with self.assertRaises(ValueError):
            engine.timing_gate(summary, "")

    def test_fresh_diagnostic_artifact_gets_hash_and_manifest(self):
        import subprocess
        self.adapter["build"] = {"command": ["fake-quartus"], "artifact": "output/Test.rbf", "timeout": 5,
                                 "project": "Test", "revision": "Test", "top": "sys_top", "device": "test-device", "image": "local-quartus"}
        self.write_manifest()
        with patch.object(engine, "tools_metadata", return_value={}), patch.object(engine, "git_metadata", return_value={}):
            session = engine.Session(self.core, self.manifest, self.root / "results", 1)
        def fake_flow(*args):
            output = session.frozen / "output"
            output.mkdir()
            (output / "Test.rbf").write_bytes(b"synthetic FPGA fixture")
            (output / "Test.fit.summary").write_text("Fitter Status : Successful\nDevice : test-device\nRevision Name : Test\nTop-level Entity Name : sys_top\nQuartus Prime Version : test-version\n")
            (output / "Test.sta.summary").write_text("\n".join("Type : " + kind + "\nSlack : 0.5\nTNS : 0" for kind in ("Setup", "Hold", "Recovery", "Removal", "Minimum Pulse Width")))
            (output / "Test.sta.rpt").write_text("\n".join("; " + label + " ; 0 ; 0 ;" for label in ("Illegal Clocks", "Unconstrained Clocks", "Unconstrained Input Port Paths", "Unconstrained Output Port Paths")))
            return {"returncode": 0}
        with patch.object(session, "run", return_value=[{**self.check, "status": "PASS"}]), patch.object(engine, "process", side_effect=fake_flow), patch.object(engine.shutil, "which", return_value="fake-docker"), patch.object(engine.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "sha256:test-image\n", "")):
            self.assertEqual(session.build(diagnostic=True), 0)
        report = json.loads((session.out / "results.json").read_text())
        self.assertEqual(report["build"]["sha256"], engine.digest(b"synthetic FPGA fixture"))
        self.assertEqual(report["build"]["quartus_version"], "test-version")
        self.assertFalse(report["build"]["release_ready"])
        self.assertTrue(Path(report["build"]["artifact"]).is_file())

    def test_stale_artifact_is_rejected_before_quartus(self):
        self.adapter["build"] = {"command": ["must-not-run"], "artifact": "output/stale.rbf"}
        self.write_manifest()
        with patch.object(engine, "tools_metadata", return_value={}), patch.object(engine, "git_metadata", return_value={}):
            session = engine.Session(self.core, self.manifest, self.root / "results", 1)
        (session.frozen / "output").mkdir()
        (session.frozen / "output/stale.rbf").write_bytes(b"stale")
        with patch.object(session, "run", return_value=[{**self.check, "status": "PASS"}]), patch.object(engine, "process", side_effect=AssertionError("Must not run")):
            with self.assertRaisesRegex(ValueError, "stale"):
                session.build(diagnostic=True)
        session.finalize([{"id": "build.stale", "status": "ERROR", "required": True}], "error")


if __name__ == "__main__":
    unittest.main()
