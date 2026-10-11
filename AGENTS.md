# Working on MiSTer-BDSM

Inspect the adapter, reference provenance, installed tools and existing baseline before edits. Generic runner code must not know Cinematronics signal names. Keep hardware-specific commands and expectations in adapters.

Run `python3 -m unittest discover -s tests -v` for runner/gate changes. Against a supplied core, run the relevant focused checks before and after harness or HDL changes. Run `mutate` to demonstrate important assertion sensitivity. Never classify a compilation failure or timeout as a killed mutant.

Preserve expected results unless independent evidence justifies changing them. Never weaken a gate, suppress warnings broadly or replace reference output merely to obtain PASS. Disclose whether a reference is a schematic, independent model, MAME compatibility observation or frozen regression.

Do not add ROMs, generated ROM images, archival manuals, game audio, memory dumps, private paths, credentials, Quartus binaries or generated FPGA artifacts to this repository. Synthetic test fixtures are permitted. Results stay local by default.

Before a candidate, run the full configured regression set, required audio/reference coverage and Quartus constraint/timing gates from one frozen snapshot. Report incomplete coverage explicitly and say hardware testing pending until hardware evidence exists.
