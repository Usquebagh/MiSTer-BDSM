# Local verification record

Verified locally on 2026-10-11 against Cinematronics source commit `2df11285789ce291fc9153fd03377cb646e97b63`. The maintained HDL was not changed. Generated JSON, traces, synthetic audio and all game data remain private local artifacts and are not committed. Reports contain exact source/adapter/runner input hashes so results from intermediate framework iterations are distinguishable.

Environment: Ubuntu 24.04.5 WSL2, Python 3.12.3, Verilator 5.020, Icarus 12.0, Yosys 0.33, GCC 13.3, Make 4.3. Existing local Quartus image reports Lite 17.0.2 Build 602 with Cyclone V support. No new toolchain was installed.

## Executed checks

| Experiment | Measured outcome |
| --- | --- |
| Runner unit suite | 17 tests pass: false-pass rejection, required skips/warnings, source isolation, timeouts killing child processes, surviving/invalid mutants, stale outputs, diagnostic artifact identity, strict timing and private integer-audio export |
| Focused synthetic smoke | Reset/loading/progress, both ROM maps and vector endpoints pass |
| Directed audio | Serial command/latch isolation, reset mute, 4800 samples in 2500000 clocks and 520/521-clock gaps pass |
| Existing synthetic sound suites | Star Castle, Rip Off and Armor Attack pass |
| Existing connected synthetic machine suite | CPU/video/input/watchdog checks pass |
| Star Castle local-ROM scenario | Existing 28-frame scenario passes |
| Rip Off local-ROM scenario | Existing 120-frame scenario passes |
| Armor Attack local-ROM scenario | 420 gameplay frames, 12696763 reference-checked retirements, 86174 vectors; complete scanout pixels pass; separate 12-frame service scenario passes |
| Unsuppressed machine lint | 14 unreviewed PINCONNECTEMPTY/UNUSEDSIGNAL warnings; WARNING, not a clean lint PASS |
| Complete regression profile | 11 PASS, 1 WARNING, 2 required SKIP; gate INCOMPLETE (exit 3) |
| Candidate build preflight | Required audio-reference and constraint reviews missing; gate INCOMPLETE, exit 3, no Quartus invocation or RBF |
| PowerShell launcher | Path conversion and focused ROM-map command pass |

An initial full regression exposed missing MRA files in the adapter's snapshot declaration. The three MRA dependencies were added; the repeated game regressions passed. This was a framework setup error, not an HDL fix. An initial baseline staging command also failed and existing scripts refreshed ignored client build outputs; all framework experiments used isolated snapshots.

## Deliberate fault evidence

The untouched baseline passed the same four directed checks. Each valid mutant then failed its designated assertion twice at identical cycles with identical expected/observed values. Bounded failure VCDs were retained locally; trace replay independently reproduced the first fault.

| Fault | Detecting assertion | Evidence |
| --- | --- | --- |
| Held machine reset | startup_deadline | Cycle 208193, expected ready=1, observed 0 |
| Wrong 8 KiB mirror map | rom_byte | Cycle 20481, expected byte 0, observed 17 |
| Shifted vector endpoint | pixel_count | Cycle 12, expected 5 pixels, observed 6 |
| Wrong audio increment | sample_interval | Cycle 1082, expected 520/521 clocks, observed 526 |

These four catches establish sensitivity to those fault classes only. MAME compatibility, schematic-informed behavioral audio and synthetic pixel correctness do not establish original-board accuracy. Audio calibration, external I/O constraints, multicycle endpoint review and physical hardware validation remain incomplete. Actual Quartus generation through this new framework has not been run; artifact/provenance handling was tested with synthetic build fixtures.
