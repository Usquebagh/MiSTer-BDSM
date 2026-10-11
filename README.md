# MiSTer-BDSM

**Build Diagnostics, Simulation & Mutation-testing** for MiSTer FPGA cores.

A small PC-side RTL validation framework. It records what ran, freezes and hashes the inputs, reports missing coverage, and tests assertions against deliberate faults in disposable copies. It does not emulate an RBF or certify original-board accuracy. Hardware testing remains necessary.

## First client and current scope

Cinematronics: Star Castle v3, Rip Off and Armor Attack. The framework repository contains no client HDL or ROMs. Its adapter consumes a separately supplied Cinematronics checkout. The first increment includes three synthetic smoke checks, a directed Star Castle command/cadence check, bridges to the existing machine and three audio regression suites, optional validated local-ROM game scenarios, and four repeatable mutations with bounded VCD failure captures.

Independent calibrated audio references are not supplied. The candidate gate is intentionally incomplete. A successful development suite is partial validation, never an overall accuracy PASS. Millipede, Jedi and Fire Trap adapters are future work and require their source repositories and expectations.

## Reuse your Linux/WSL toolchain

No new Python packages are required when running from the checkout. Python 3.10+ is required (`Path.is_relative_to` and modern typing/runtime APIs). Tested setup: Ubuntu 24.04 WSL2, Python 3.12.3, Verilator 5.020, GCC 13.3, Make 4.3, Icarus 12.0 and Yosys 0.33. Existing Quartus flow uses `theypsilon/quartus-lite-c5:17.0.2` with Cyclone V support. A different tool version is recorded, not silently treated as equivalent; repeat the baseline/mutation campaign before adopting it.

Verilator/Make/G++ compile the new harnesses. Icarus/Yosys are needed only by existing suites that use them. GTKWave is optional for viewing VCDs; Questa is not required by the first boundary. Verilator does not prove CDC, analog behaviour or physical timing and its predominantly two-state execution does not provide complete X/Z coverage.

From WSL/Linux:

```sh
python3 /path/to/MiSTer-BDSM/mister-bdsm test /path/to/core --suite smoke
python3 /path/to/MiSTer-BDSM/mister-bdsm test /path/to/core --suite lint
python3 /path/to/MiSTer-BDSM/mister-bdsm test /path/to/core --suite audio
python3 /path/to/MiSTer-BDSM/mister-bdsm test /path/to/core --check cinematronics.rom.mapping
python3 /path/to/MiSTer-BDSM/mister-bdsm mutate /path/to/core --seed 1 --repeats 2
python3 /path/to/MiSTer-BDSM/mister-bdsm regression /path/to/core --rom-dir /private/roms
python3 /path/to/MiSTer-BDSM/mister-bdsm build /path/to/core --rom-dir /private/roms
```

The last command requests a candidate: missing references/required ROMs block Quartus. Known missing required references are checked first, so an impossible candidate does not rerun expensive suites; those checks are explicitly SKIP for that run. An explicitly requested `build --profile diagnostic` can compile despite incomplete behavioural coverage, but remains unqualified and exits nonzero for failed/incomplete gates. It may retain a fresh diagnostic RBF for hardware investigation; it never marks it release-ready. The full Quartus flow has not yet been exercised by this framework against the real client.

From PowerShell, the launcher converts paths and runs the installed WSL distribution:

```powershell
.\mister-bdsm.ps1 test 'C:\path\to\Cinematronics' -Suite smoke
.\mister-bdsm.ps1 mutate 'C:\path\to\Cinematronics'
.\mister-bdsm.ps1 test 'C:\path\to\Cinematronics' -Suite audio
```

Optional installation: `python3 -m venv .venv`, then `.venv/bin/pip install .` exposes `mister-bdsm`. The checkout command avoids any dependency download. Defaults select the Cinematronics adapter; use `--adapter /path/adapter.json` for another inspected core. Generic execution supports a core-specific `check.py` or an existing script with declared evidence markers.

## Results and privacy

Each run gets a unique directory under `~/.local/state/mister-bdsm/results`; override with `--output`. `results.json` contains stable check IDs, resolved source hashes, revision/dirty state, adapter and runner hashes, tool versions, seed, expectations, observations, limitations and diagnostic paths. Compile errors, simulator crashes, missing tools and timeouts are ERROR; directed assertion violations are FAIL. Missing fixtures/references are SKIP. Legacy suite failures are conservatively ERROR until their log establishes assertion versus tool failure. Legacy PASS is an aggregate suite result with the actual PASS lines retained.

Dedicated `--suite lint` runs full machine-boundary `-Wall` without warning suppressions. Unreviewed warnings become required WARNING and block qualification. Focused executable compilation preserves the client's existing unused-signal/empty-pin suppressions for building its harness; that compile is not presented as a clean standalone lint check. Exact warning review/waivers are a later increment.

| Exit | Meaning |
| --- | --- |
| 0 | Selected profile satisfied; validation remains partial |
| 1 | Assertion or mutation-campaign failure |
| 2 | Configuration/tool/execution problem |
| 3 | Required coverage incomplete |
| 4 | FPGA build/timing failure |

Precedence: ERROR, behavioural FAIL, build FAIL, incomplete, satisfied. WARNING on a required check is incomplete; inapplicable hardware must be omitted with a declared rationale. No empty selection can succeed.

Source snapshots include adapter-declared directories/files and are isolated under Linux `/tmp` to avoid GNU Make's path-with-spaces limitation. The framework verifies maintained and frozen input hashes; source changes invalidate evidence. Mutations never edit the client. Temporary ROM images disappear with the snapshot. Logs, bounded VCDs and explicitly allowlisted synthetic audio captures are retained locally. Synthetic captures preserve the original signed 16-bit integer PCM and WAV, with rate/scaling/identity metadata; they are regression observations, not calibrated references. Game-derived WAVs are never discovered or copied automatically. Results remain private and may contain sensitive observations. There is no public artifact-upload feature. Never upload private results blindly. The repository includes no ROMs or game recordings.

Local ROMs: supply `starcas.zip`, `ripoff.zip`, `armora.zip` via `--rom-dir`. Existing preparation scripts validate sizes/CRC/SHA-1/interleave; the report records archive/image SHA-256 without recording the input directory. Missing data is SKIP, incompatible data is ERROR. ROM scenarios check compatibility/activity, not calibrated audio correctness.

## Reproducible mutation proof

The untouched baseline must pass before mutations begin. Each mutant must fail its designated assertion twice with identical cycle/expected/observed evidence. Compilation errors/timeouts do not count as catches. A survivor fails the campaign and needs investigation. Failure replay captures a maximum 2048 clocks at the first fault. Current faults: held reset, wrong mirrored ROM bank, one extra vector endpoint pixel and wrong audio cadence. This is sensitivity evidence for those four fault classes, not a general coverage percentage.

## FPGA generation boundary

The adapter invokes the client's established `bash build.sh`, preserving QPF/QSF/QIP/SDC and MiSTer sources. A fresh snapshot excludes old outputs. The hardware top is `sys_top`, project/revision `Arcade-Cinematronics`, device `5CSEBA6U23I7`. Simulator-only harnesses and mutations are never synthesized into the RBF.

Candidate checks include all declared suites, game fixtures and independent audio-reference coverage. The strict timing gate requires setup/hold/recovery/removal/pulse-width categories, nonnegative slack, zero TNS and no unreviewed unconstrained clock/I/O paths. Reviewed exception/waiver support is intentionally not implemented yet. Existing external I/O omissions therefore block qualification; broad waivers are not an acceptable workaround. Audio multicycle endpoint validation remains a required review gap. A binary SHA-256, exact source/dependency hashes, image ID, build settings and test/timing evidence accompany retained outputs in `results.json`.

No RBF is copied to MiSTer and nothing is released by this CLI.

## Development

```sh
python3 -m unittest discover -s tests -v
```

See [architecture and coverage](docs/design.md), [agent onboarding](docs/onboarding.md) and [local evidence](docs/evidence.md). Framework/harness code is MIT licensed. Client HDL, imported MiSTer/MAME sources, artwork and reference material retain their own licenses; they are not redistributed here.
