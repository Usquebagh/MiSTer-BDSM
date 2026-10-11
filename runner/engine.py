"""Dependency-free runner with frozen inputs and strict evidence/gate semantics."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import wave

STATUSES = {"PASS", "FAIL", "WARNING", "SKIP", "ERROR"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def relative(value):
    path = Path(value)
    if path.is_absolute() or not value or ".." in path.parts or "\\" in value:
        raise ValueError(f"Unsafe manifest path: {value}")
    return path


def load_adapter(path):
    adapter = json.loads(path.read_text(encoding="utf-8"))
    if adapter.get("schema_version") != 1:
        raise ValueError("Unsupported adapter schema_version")
    for key in ("id", "version", "checks", "source_roots", "source_files", "required_files", "limitations"):
        if key not in adapter:
            raise ValueError(f"Adapter missing {key}")
    if not isinstance(adapter["checks"], list) or not adapter["checks"]:
        raise ValueError("Adapter needs at least one check")
    ids = set()
    for check in adapter["checks"]:
        if check.get("id") in ids or not isinstance(check.get("required"), bool):
            raise ValueError("Duplicate check ID or invalid required flag")
        ids.add(check["id"])
        for key in ("id", "suite", "expectation", "reference"):
            if not isinstance(check.get(key), str) or not check[key]:
                raise ValueError(f"Check missing {key}")
        kinds = [key for key in ("mode", "script", "skip_reason") if key in check]
        if len(kinds) != 1:
            raise ValueError("Check must declare exactly one execution mode")
        if "skip_reason" not in check and (not isinstance(check.get("timeout"), int) or check["timeout"] <= 0):
            raise ValueError("Check needs a positive timeout")
        if "script" in check:
            relative(check["script"])
            if not check.get("markers"):
                raise ValueError("Legacy script needs explicit evidence markers")
    for value in adapter["source_roots"] + adapter["source_files"] + adapter["required_files"]:
        relative(value)
    for mutant in adapter.get("mutations", []):
        relative(mutant["file"])
        if mutant["check"] not in ids or not mutant.get("old") or not mutant.get("failure_label"):
            raise ValueError("Invalid mutation declaration")
    if "build" in adapter:
        relative(adapter["build"]["artifact"])
    return adapter


def inventory(core, adapter):
    files = {}
    for root in adapter["source_roots"]:
        folder = core / relative(root)
        if folder.is_symlink():
            raise ValueError(f"Source symlink is not supported: {root}")
        if folder.exists():
            for path in sorted(folder.rglob("*")):
                if path.is_symlink():
                    raise ValueError("Source symlinks must be resolved explicitly in an adapter")
                if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                    files[path.relative_to(core).as_posix()] = digest(path.read_bytes())
    for value in adapter["source_files"]:
        path = core / relative(value)
        if path.is_symlink():
            raise ValueError("Source symlinks are not supported")
        if path.is_file():
            files[value] = digest(path.read_bytes())
    for value in adapter["required_files"]:
        if value not in files:
            raise ValueError(f"Required source missing: {value}")
    return dict(sorted(files.items()))


def input_hash(files):
    return digest(json.dumps(files, sort_keys=True, separators=(",", ":")).encode())


def snapshot(core, destination, files):
    for name, expected in files.items():
        data = (core / name).read_bytes()
        if digest(data) != expected:
            raise ValueError("Core changed while freezing input snapshot")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def process(command, cwd, logfile, timeout):
    started = time.monotonic()
    with logfile.open("w", encoding="utf-8") as log:
        try:
            proc = subprocess.Popen(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True, env={**os.environ, "LC_ALL": "C", "TZ": "UTC"})
        except OSError as exc:
            return {"status": "ERROR", "reason": str(exc), "command": command}
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            return {"status": "ERROR", "reason": f"Wall-clock timeout after {timeout}s", "command": command}
    # Read a bounded tail. Full raw output remains in the local log.
    with logfile.open("rb") as stream:
        stream.seek(max(0, logfile.stat().st_size - 8 * 1024 * 1024))
        output = stream.read().decode("utf-8", errors="replace")
    return {"returncode": code, "output": output, "seconds": round(time.monotonic() - started, 3), "command": command}


def tools_metadata(names):
    versions = {}
    for name in sorted(set(names) | {"python3", "git"}):
        path = shutil.which(name)
        if not path:
            versions[name] = {"available": False}
            continue
        option = "-V" if name in ("iverilog", "vvp", "yosys") else "--version"
        try:
            result = subprocess.run([path, option], capture_output=True, text=True, timeout=15)
            lines = (result.stdout + result.stderr).splitlines()
            versions[name] = {"available": True, "path": path, "version": lines[0] if lines else "unreported"}
        except (OSError, subprocess.TimeoutExpired) as exc:
            versions[name] = {"available": True, "path": path, "version_error": str(exc)}
    return versions


def git_metadata(core):
    def run(*args):
        result = subprocess.run(["git", "-C", str(core), *args], capture_output=True, text=True, timeout=20)
        return result.stdout.strip() if result.returncode == 0 else None
    if not shutil.which("git"):
        return {"revision": None, "reason": "Git unavailable"}
    return {"revision": run("rev-parse", "HEAD"), "dirty": bool(run("status", "--porcelain")),
            "submodules": run("submodule", "status")}


def run_check(check, frozen, adapter_dir, out, seed, rom_dir=None):
    result = {key: check[key] for key in ("id", "suite", "required", "expectation", "reference")}
    log = out / (check["id"] + ".log")
    result["log"] = str(log)
    if "skip_reason" in check:
        return {**result, "status": "SKIP", "reason": check["skip_reason"]}
    missing = [tool for tool in check["tools"] if not shutil.which(tool)]
    if missing:
        return {**result, "status": "ERROR", "reason": "Missing tools: " + ", ".join(missing)}
    args = []
    if "rom" in check:
        if rom_dir is None or not (rom_dir / check["rom"]).is_file():
            return {**result, "status": "SKIP", "reason": "Local ROM fixture not supplied: " + check["rom"]}
        private_rom = frozen / "build" / "roms" / (check["game"] + ".bin")
        archive = rom_dir / check["rom"]
        before = digest(archive.read_bytes())
        prepared = process([sys.executable, str(frozen / "tools" / check["prepare"]), str(archive),
                            "--output", str(private_rom)], frozen, log, 30)
        if "status" in prepared or prepared["returncode"]:
            return {**result, "status": "ERROR", "reason": "ROM identity/preparation failed; see local log"}
        if digest(archive.read_bytes()) != before:
            return {**result, "status": "ERROR", "reason": "ROM archive changed during preparation"}
        result["rom"] = {"name": check["rom"], "archive_sha256": before, "image_sha256": digest(private_rom.read_bytes()), "bytes": private_rom.stat().st_size}
        args = [str(private_rom)]
    command = ([sys.executable, str(adapter_dir / "check.py"), check["mode"], "--seed", str(seed)]
               if "mode" in check else ["bash", check["script"], *args])
    ran = process(command, frozen, log, check["timeout"])
    if "status" in ran:
        return {**result, **ran}
    result.update({key: ran[key] for key in ("command", "seconds", "returncode")})
    if "mode" in check:
        try:
            events = [json.loads(line[5:]) for line in ran["output"].splitlines() if line.startswith("BDSM ")]
            event = events[-1] if events else None
            if event is None or event.get("status") not in STATUSES:
                raise ValueError("Missing or invalid structured simulation result")
            if event["status"] == "FAIL" and ("label" not in event or "cycle" not in event or "expected" not in event or "observed" not in event):
                raise ValueError("Incomplete assertion failure evidence")
            expected_code = {"PASS": 0, "WARNING": 0, "FAIL": 1, "ERROR": 2}.get(event["status"])
            if expected_code is None or ran["returncode"] != expected_code:
                raise ValueError("Exit code disagrees with structured result")
            result.update(event)
        except (ValueError, TypeError, KeyError) as exc:
            result.update(status="ERROR", reason=str(exc))
    else:
        observations = [line for line in ran["output"].splitlines() if line.startswith("PASS:")]
        result["observations"] = observations
        # Legacy suites are aggregate results; their stderr/exit alone cannot classify an assertion.
        if ran["returncode"]:
            result.update(status="ERROR", reason="Legacy suite failed; raw assertion/tool classification requires log review")
        elif not all(marker in ran["output"] for marker in check["markers"]):
            result.update(status="ERROR", reason="Successful process omitted required evidence markers")
        else:
            result.update(status="PASS", observed="Declared legacy suite markers present; see individual observations")
    return result


def retain_synthetic_audio(check, frozen, out, result):
    """Explicit synthetic-only allowlist; no game capture discovery or copying."""
    if "rom" in check or check.get("suite") != "audio":
        raise ValueError("Audio export allowlist is only valid for synthetic audio checks")
    captures = []
    for name in check.get("audio_artifacts", []):
        source = frozen / relative(name)
        if not source.is_file():
            continue
        target = out / "audio" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(source), "rb") as audio:
            if audio.getsampwidth() != 2 or audio.getcomptype() != "NONE":
                raise ValueError("Expected uncompressed signed 16-bit synthetic audio")
            frames, rate, channels = audio.getnframes(), audio.getframerate(), audio.getnchannels()
            raw = audio.readframes(frames)
        shutil.copyfile(source, target)
        pcm = target.with_suffix(".pcm")
        pcm.write_bytes(raw)
        captures.append({"wav": str(target), "raw_pcm": str(pcm), "encoding": "signed-16-bit-little-endian",
                         "sample_rate_hz": rate, "channels": channels, "frames": frames,
                         "amplitude_units": "integer PCM", "full_scale_magnitude": 32768,
                         "sha256": digest(raw), "provenance": "synthetic regression stimulus; not calibrated board reference"})
    if captures:
        result["audio_captures"] = captures


def gate(results):
    if not results:
        return 3, "INCOMPLETE"
    if any(r["status"] == "ERROR" for r in results):
        return 2, "ERROR"
    if any(r["status"] == "FAIL" for r in results):
        return (4 if all(r["id"].startswith("build.") for r in results if r["status"] == "FAIL") else 1), "FAILED"
    if any(r["required"] and r["status"] != "PASS" for r in results):
        return 3, "INCOMPLETE"
    return 0, "SATISFIED"


def timing_gate(summary, report):
    rows = re.findall(r"Type\s*:\s*(.*?)\nSlack\s*:\s*([-\d.]+)\nTNS\s*:\s*([-\d.]+)", summary)
    categories = ["Setup", "Hold", "Recovery", "Removal", "Minimum Pulse Width"]
    if any(not any(kind.startswith(category) for kind, *_ in rows) for category in categories):
        raise ValueError("Missing required timing categories")
    if any(float(slack) < 0 or float(tns) != 0 for _, slack, tns in rows):
        raise ValueError("Timing slack/TNS gate failed")
    counts = {}
    for label in ("Illegal Clocks", "Unconstrained Clocks", "Unconstrained Input Port Paths", "Unconstrained Output Port Paths"):
        found = re.search(r";\s*" + label + r"\s*;\s*(\d+)\s*;\s*(\d+)\s*;", report)
        if not found:
            raise ValueError("Missing constraint diagnostic: " + label)
        counts[label] = [int(n) for n in found.groups()]
        if any(counts[label]):
            raise ValueError("Unreviewed constraint gap: " + label)
    return {"worst_slack_ns": {category: min(float(s) for k, s, _ in rows if k.startswith(category)) for category in categories}, "constraint_counts": counts}


class Session:
    def __init__(self, core, manifest, output, seed):
        self.core, self.manifest, self.seed = core.resolve(), manifest.resolve(), seed
        self.adapter = load_adapter(self.manifest)
        output.mkdir(parents=True, exist_ok=True)
        self.out = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-"), dir=output)).resolve()
        # /tmp path has no spaces; GNU Make cannot handle source paths with spaces.
        self.work = Path(tempfile.mkdtemp(prefix="mister-bdsm-"))
        self.frozen = self.work / "baseline"
        self.files = inventory(self.core, self.adapter)
        self.hash = input_hash(self.files)
        snapshot(self.core, self.frozen, self.files)
        if inventory(self.core, self.adapter) != self.files:
            raise ValueError("Core changed during snapshot")
        self.adapter_dir = self.work / "adapter"
        shutil.copytree(self.manifest.parent, self.adapter_dir, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        harness_inputs = {str(p.relative_to(self.adapter_dir)): digest(p.read_bytes()) for p in self.adapter_dir.rglob("*") if p.is_file()}
        runner_inputs = {p.name: digest(p.read_bytes()) for p in Path(__file__).parent.glob("*.py")}
        self.report = {"schema_version": 1, "framework_version": "0.1.0", "started_utc": datetime.now(timezone.utc).isoformat(),
                       "core": git_metadata(self.core), "source_sha256": self.hash, "source_files": self.files,
                       "adapter": {"id": self.adapter["id"], "version": self.adapter["version"], "sha256": input_hash(harness_inputs)},
                       "runner_sha256": input_hash(runner_inputs), "seed": seed, "games": self.adapter.get("games", []),
                       "tools": tools_metadata([name for check in self.adapter["checks"] for name in check.get("tools", [])]),
                       "execution": {"platform": sys.platform, "python": sys.version, "kernel": os.uname().release},
                       "limitations": self.adapter["limitations"], "hardware_validation": "pending", "results": []}

    def run(self, checks, rom_dir=None, frozen=None, output=None):
        results = []
        for check in checks:
            print("RUN  " + check["id"], flush=True)
            result = run_check(check, frozen or self.frozen, self.adapter_dir, output or self.out, self.seed, rom_dir)
            if check.get("audio_artifacts"):
                retain_synthetic_audio(check, frozen or self.frozen, output or self.out, result)
            results.append(result)
            print(result["status"] + " " + check["id"] + (": " + result["reason"] if "reason" in result else ""), flush=True)
        return results

    def finalize(self, results, profile, extra=None):
        try:
            stable = inventory(self.core, self.adapter) == self.files
            frozen_stable = inventory(self.frozen, self.adapter) == self.files
        except (OSError, ValueError):
            stable = frozen_stable = False
        if not stable:
            results.append({"id": "framework.source_stability", "required": True, "status": "ERROR", "reason": "Maintained core source changed; run a fresh baseline before building"})
        if not frozen_stable:
            results.append({"id": "framework.snapshot_stability", "required": True, "status": "ERROR", "reason": "A tool modified frozen source inputs; run is invalid"})
        code, state = gate(results)
        self.report.update(results=results, profile=profile, gate=state, exit_code=code,
                           validation_scope="partial", audio_validation="incomplete", **(extra or {}))
        # Preserve diagnostic files and logs, never ROM images or memory contents.
        diagnostics = self.out / "diagnostics"
        for p in sorted(self.work.rglob("*")):
            if p.is_file() and p.suffix in (".vcd", ".log") and p.stat().st_size < 32 * 1024 * 1024:
                target = diagnostics / p.relative_to(self.work)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(p, target)
        for result in results:
            for key in ("diagnostics",):
                if key in result:
                    result[key] = [str(diagnostics / Path(v).relative_to(self.work)) if Path(v).is_relative_to(self.work) else v for v in result[key]]
        self.report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        save(self.out / "results.json", self.report)
        shutil.rmtree(self.work)
        print(f"Gate: {state}; validation partial; hardware testing pending\nResults: {self.out / 'results.json'}", flush=True)
        return code

    def mutate(self, repeats):
        checks = {check["id"]: check for check in self.adapter["checks"]}
        baseline_checks = [checks[m["check"]] for m in self.adapter["mutations"]]
        baseline = self.run(baseline_checks)
        if gate(baseline)[0]:
            return self.finalize(baseline, "mutation-baseline", {"campaign": "BLOCKED"})
        campaign = []
        for mutation in self.adapter["mutations"]:
            mutant = self.work / mutation["id"]
            snapshot(self.frozen, mutant, self.files)
            target = mutant / mutation["file"]
            original = target.read_text()
            if original.count(mutation["old"]) != 1:
                campaign.append({"id": mutation["id"], "required": True, "status": "ERROR", "reason": "Mutation anchor absent or ambiguous"})
                continue
            target.write_text(original.replace(mutation["old"], mutation["new"]))
            evidence = []
            for repetition in range(repeats):
                out = self.out / mutation["id"] / str(repetition + 1)
                out.mkdir(parents=True)
                result = self.run([checks[mutation["check"]]], frozen=mutant, output=out)[0]
                if result.get("diagnostics"):
                    for trace in result["diagnostics"]:
                        path = Path(trace)
                        if path.is_file():
                            copied = out / path.name
                            shutil.copyfile(path, copied)
                    result["diagnostics"] = [str(out / Path(v).name) for v in result["diagnostics"]]
                evidence.append(result)
            caught = all(r["status"] == "FAIL" and r.get("label") == mutation["failure_label"] for r in evidence)
            stable = len({(r.get("cycle"), r.get("expected"), r.get("observed")) for r in evidence}) == 1
            campaign.append({"id": "mutation." + mutation["id"], "required": True,
                             "status": "PASS" if caught and stable else "ERROR" if any(r["status"] == "ERROR" for r in evidence) else "FAIL",
                             "reason": "Expected assertion reproduced" if caught and stable else "Surviving, invalid or nondeterministic mutant; investigate",
                             "mutation": mutation, "mutated_source_sha256": input_hash(inventory(mutant, self.adapter)), "evidence": evidence})
        return self.finalize(baseline + campaign, "mutation", {"mutation_repeats": repeats, "campaign": "COMPLETE"})

    def build(self, diagnostic=False, rom_dir=None):
        blockers = [check for check in self.adapter["checks"] if check["required"] and "skip_reason" in check]
        if blockers and not diagnostic:
            results = self.run(blockers)
            results += [{"id": check["id"], "suite": check["suite"], "required": check["required"], "status": "SKIP",
                         "expectation": check["expectation"], "reference": check["reference"],
                         "reason": "Candidate preflight blocked; this check did not execute in this run"}
                        for check in self.adapter["checks"] if check not in blockers]
            return self.finalize(results, "candidate", {"build": {"status": "BLOCKED", "artifact": None}})
        results = self.run(self.adapter["checks"], rom_dir)
        code, _ = gate(results)
        if not diagnostic and code:
            return self.finalize(results, "candidate", {"build": {"status": "BLOCKED", "artifact": None}})
        if inventory(self.core, self.adapter) != self.files or inventory(self.frozen, self.adapter) != self.files:
            return self.finalize(results, "candidate" if not diagnostic else "diagnostic", {"build": {"status": "BLOCKED", "artifact": None}})
        build = self.adapter["build"]
        artifact = self.frozen / build["artifact"]
        if artifact.exists():
            raise ValueError("Refusing stale build artifact")
        docker_meta = subprocess.run(["docker", "image", "inspect", build["image"], "--format", "{{.Id}}"], capture_output=True, text=True, timeout=30) if shutil.which("docker") else None
        if docker_meta is None or docker_meta.returncode:
            results.append({"id": "build.toolchain", "status": "ERROR", "required": True, "reason": "Configured Quartus image is unavailable locally; no automatic download"})
            return self.finalize(results, "diagnostic" if diagnostic else "candidate")
        ran = process(build["command"], self.frozen, self.out / "quartus.log", build["timeout"])
        info = {**build, "image_id": docker_meta.stdout.strip(), "release_ready": False, "status": "ERROR", "artifact": None}
        try:
            if "status" in ran or ran["returncode"] or not artifact.is_file() or artifact.stat().st_size == 0:
                raise ValueError("Quartus flow failed or produced no fresh RBF")
            if inventory(self.core, self.adapter) != self.files or inventory(self.frozen, self.adapter) != self.files:
                raise ValueError("Source changed during Quartus build; artifact is invalid")
            image_after = subprocess.run(["docker", "image", "inspect", build["image"], "--format", "{{.Id}}"], capture_output=True, text=True, timeout=30)
            if image_after.returncode or image_after.stdout.strip() != info["image_id"]:
                raise ValueError("Quartus image tag changed during build")
            fit = (artifact.parent / (build["project"] + ".fit.summary")).read_text()
            for label, value in (("Device", build["device"]), ("Revision Name", build["revision"]), ("Top-level Entity Name", build["top"])):
                if not re.search(r"^" + re.escape(label) + r"\s*:\s*" + re.escape(value) + r"\s*$", fit, re.MULTILINE):
                    raise ValueError("Fitter settings disagree with adapter: " + label)
            if "Fitter Status : Successful" not in fit:
                raise ValueError("Fitting did not complete successfully")
            info["quartus_version"] = next((line.split(":", 1)[1].strip() for line in fit.splitlines() if line.startswith("Quartus Prime Version")), "unreported")
            timing = timing_gate((artifact.parent / (build["project"] + ".sta.summary")).read_text(),
                                 (artifact.parent / (build["project"] + ".sta.rpt")).read_text())
            results.append({"id": "build.timing", "status": "PASS", "required": True, "observed": timing})
            destination = self.out / artifact.name
            shutil.copyfile(artifact, destination)
            info.update(status="DIAGNOSTIC" if diagnostic else "CANDIDATE", artifact=str(destination), sha256=digest(destination.read_bytes()), timing=timing)
        except (OSError, ValueError) as exc:
            results.append({"id": "build.timing", "status": "FAIL", "required": True, "reason": str(exc)})
            # Diagnostic binaries may still be retained with failed timing, explicitly unqualified.
            if diagnostic and artifact.is_file() and artifact.stat().st_size and inventory(self.core, self.adapter) == self.files and inventory(self.frozen, self.adapter) == self.files:
                destination = self.out / artifact.name
                shutil.copyfile(artifact, destination)
                info.update(status="DIAGNOSTIC_UNQUALIFIED", artifact=str(destination), sha256=digest(destination.read_bytes()))
        self.report["build"] = info
        return self.finalize(results, "diagnostic" if diagnostic else "candidate")
