# Using MiSTer-BDSM during core development

Before edits, inspect the supplied core, adapter, references and actual tools. Run affected baseline checks and record failures. A new core has no verified baseline until one is demonstrated. Establish independent expectations before implementation where practical.

Use small HDL changes and focused checks. Diagnose assertions using cycle, expected/observed values and traces; fix the implementation or justify an expectation correction with independent evidence. Reproduce a defect on the broken source before fixing it where possible. If a hardware defect cannot be reproduced in simulation, retain the observation and label the simulation gap.

## Suggested client AGENTS.md section

Merge this section into existing guidance; do not replace it:

> Locate the project's MiSTer-BDSM adapter and installed runner. Before HDL edits run affected baseline checks. Record the subsystem, intended behaviour and supporting reference. After changes run focused lint/simulation and preserve regressions for reproduced defects. Do not weaken assertions or replace expected output to get PASS. Exercise an appropriate disposable mutation for important new assertions. Before a candidate run shared/game/audio regressions and the gated Quartus build from the same frozen input snapshot. Interpret required SKIP/WARNING as incomplete. Report artifact paths and hardware testing pending.

## Minimal new adapter

Inspect before defining ports. Declare all simulation and synthesis input roots, files, required files, applicable subsystems and excluded hardware. Include generated assets, IP/QIP/SDC dependencies and references in input identity. The first client manifest is the example format; schema version is 1.

Each check declares stable `id`, `suite`, `required`, `expectation`, `reference`, positive `timeout`, required `tools`, and either a harness `mode`, a `script` with required evidence `markers`, or `skip_reason`. A thin `check.py` accepts mode/seed and emits a final `BDSM {JSON}` event. PASS exits 0; FAIL exits 1 and includes label/cycle/expected/observed; ERROR exits 2. The runner rejects inconsistent exits and missing events. Legacy scripts remain aggregate results until their harnesses expose individual assertions.

Start with synthetic reset/clock/memory checks. Add video, inputs and directed audio as they become implemented. Add local-ROM scenarios later. Declare vendor models and their assumptions explicitly, including reset/read latency/collision semantics. Do not infer full-system correctness from a smaller boundary.

Mutation anchors are exact, single-occurrence source replacements in a disposable snapshot. Declare the expected failing check and assertion label. A baseline and two identical failures are required. A compilation error is an invalid experiment, not a successful mutation detection.
