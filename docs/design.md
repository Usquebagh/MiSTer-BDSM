# Architecture and coverage

Generic orchestration lives in `runner/`. It validates manifests, hashes inputs, freezes snapshots, invokes commands with wall-clock timeouts, kills timed-out process groups, records results and enforces gates. It knows no CPU/vector/sound signals. `adapters/cinematronics/` declares the real boundary and compiles the thin C++ harnesses against client sources. Existing game/core tests remain in the client.

## Current boundaries

| Check | Boundary and expectation | Excluded claims |
| --- | --- | --- |
| rtl.lint | Full machine-boundary Verilator -Wall, all warning locations retained | No blanket suppression or unreviewed lint PASS |
| machine.reset_progress | `cinemat_machine`, direct 50 MHz; loading blocks retirement, startup <=200000 clocks, synthetic CPU/vector activity, reload blocking | Full opcode correctness, exact CPU/vector board timing, PLL/HPS/DDR, full game operation |
| rom.mapping | `cinemat_rom`, every 16-bit logical address in both maps; distinct synthetic bytes and synchronous reads | HPS download transport; actual copyrighted ROM content |
| vector.endpoints | `vector_line`, explicitly listed horizontal inclusive pixels and stall stability | All octants/clipping; those remain in the client's broader tests; physical monitor |
| audio.commands_cadence | `starcastle_sound`, non-symmetric serial command, latch isolation, reset mute and 50 MHz/96 kHz cadence | Analog fidelity, all sound voices, calibrated mix |
| audio.*_regression | Client's synthetic Star Castle/Rip Off/Armor Attack sound suites, including short triggers | Frozen thresholds are not board calibration |
| machine.regression | Existing connected machine suite using pinned MAME and integer pixel oracle | Independent proof of the physical CCPU |
| game.* | Optional existing scripted ROM scenarios for all three games | Comprehensive gameplay and sound reference correctness |
| audio.reference_coverage | Required SKIP until independently justified references and voice/event coverage exist | Prevents unqualified candidate/audio PASS |

The 200000-clock startup deadline is an engineering bound for the current framebuffer initialization, not an original hardware specification. The synthetic machine program is a subset of an existing pinned-MAME checked test fixture. Its vector activity assertion is deliberately a smoke check. The horizontal raster expectation is independently enumerated geometry. The 96 kHz cadence is an implementation contract; sound command wiring is supported by client documentation pointing to the original Star Castle schematic. No new claim of independently re-reviewed schematics is made by this framework.

## Evidence versus release

PASS means a declared check ran and met its expectation. FAIL means an assertion violated that expectation. ERROR means an invalid execution or setup. SKIP means it did not run. WARNING is qualified evidence; a required warning blocks the gate. Explicitly inapplicable subsystems are declared in adapter limitations, not fabricated skipped tests.

Results always say partial validation and hardware pending. A required calibrated audio reference is presently missing. Timing exceptions and omitted external I/O constraints need independent review; strict candidate qualification remains blocked until those gaps are addressed. Diagnostic builds are separate and cannot become release-ready.

## Planned increments

1. Current: reproducible smoke, audio regression bridges and four directed mutation catches.
2. Expand lint to explicit warning IDs and per-core waivers, add four-state reset/X tests, improve per-assertion legacy result export and complete the audio voice/event/reference matrix.
3. Review all TimeQuest constraint gaps and audio multicycle endpoints, then exercise the real gated Quartus flow from a tested snapshot.
4. Preserve a real reproduced hardware defect as a failing/passing regression. Onboard Millipede/Fire Trap/Jedi only after inspecting actual sources and expectations.

No universal signal interface, speculative architecture plugins or public ROM-based CI artifacts are required.
