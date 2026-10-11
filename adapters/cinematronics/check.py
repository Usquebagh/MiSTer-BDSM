#!/usr/bin/env python3
"""Thin Cinematronics harness compiler. Compile errors never count as assertion FAILs."""
import argparse
import json
import re
from pathlib import Path
import subprocess
import sys


def emit(status, **details):
    print("BDSM " + json.dumps({"status": status, **details}), flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["machine", "rom", "vector", "audio", "lint"])
    p.add_argument("--seed", type=int, default=1)
    args = p.parse_args()
    adapter = Path(__file__).resolve().parent
    core = Path.cwd()
    tops = {"machine": "cinemat_machine", "rom": "cinemat_rom", "vector": "vector_line", "audio": "starcastle_sound"}
    sources = {
        "machine": [str(f) for d in ["ccpu", "games", "io", "machine", "vector", "sound"] for f in sorted((core / "rtl" / d).glob("*.sv"))],
        "rom": ["rtl/games/cinemat_rom.sv"],
        "vector": ["rtl/vector/vector_line.sv"],
        "audio": ["rtl/sound/starcastle_sound.sv"],
    }
    work = core / "build" / ("bdsm-" + args.mode)
    work.mkdir(parents=True, exist_ok=True)
    if args.mode == "lint":
        with (work / "lint.log").open("w") as log:
            lint = subprocess.run(["verilator", "--lint-only", "--top-module", "cinemat_machine", "-Wall", "-Wno-fatal", *sources["machine"]], stdout=log, stderr=subprocess.STDOUT)
        text = (work / "lint.log").read_text()
        if lint.returncode:
            emit("ERROR", reason="Verilator lint could not complete", diagnostics=[str(work / "lint.log")])
            return 2
        findings = re.findall(r"%Warning-([^:]+): ([^\n]+)", text)
        emit("WARNING" if findings else "PASS", reason="Unreviewed lint warnings" if findings else "No lint warnings",
             observed=[{"code": code, "location": location} for code, location in findings], diagnostics=[str(work / "lint.log")])
        return 0
    command = ["verilator", "--cc", "--exe", "--build", "--trace", "--trace-depth", "2",
               "--top-module", tops[args.mode], "-Wall", "-Wno-UNUSEDSIGNAL", "-Wno-PINCONNECTEMPTY",
               "--Mdir", str(work), "-CFLAGS", "-std=c++17 -I" + str(adapter),
               *sources[args.mode], str(adapter / (args.mode + ".cpp"))]
    with (work / "compile.log").open("w") as log:
        compiled = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    if compiled.returncode:
        emit("ERROR", reason="Verilator/C++ compilation failed", diagnostics=[str(work / "compile.log")])
        return 2
    binary = work / ("V" + tops[args.mode])
    ran = subprocess.run([str(binary), "+verilator+seed+" + str(args.seed)], cwd=work, capture_output=True, text=True)
    print(ran.stdout, end="", flush=True)
    print(ran.stderr, end="", file=sys.stderr, flush=True)
    events = [json.loads(line[5:]) for line in ran.stdout.splitlines() if line.startswith("BDSM ")]
    if not events or events[-1]["status"] not in ("PASS", "FAIL"):
        emit("ERROR", reason="Simulation returned no valid assertion result")
        return 2
    event = events[-1]
    if event["status"] == "PASS" and ran.returncode:
        emit("ERROR", reason="Simulation crashed after reporting PASS")
        return 2
    if event["status"] == "FAIL":
        # Deterministic replay captures at most 2048 clocks around the first fault.
        traced = subprocess.run([str(binary), "+verilator+seed+" + str(args.seed), "--trace-start",
                                 str(max(0, event.get("cycle", 0) - 1024))], cwd=work, capture_output=True, text=True)
        replay = [json.loads(line[5:]) for line in traced.stdout.splitlines() if line.startswith("BDSM ")]
        if not replay or replay[-1] != event or traced.returncode != 1:
            emit("ERROR", reason="Failure did not reproduce during trace replay")
            return 2
        event["diagnostics"] = [str(work / "failure.vcd")]
        emit(**event)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
