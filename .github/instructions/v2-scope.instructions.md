---
description: "Use when working in this repository. Restricts edits and deep code exploration to Version 2 code paths and files (simulation_v2, decision_engine_v2, risk_engine_v2, and *_v2.py)."
name: "Version 2 Scope Guard"
applyTo:
  - "simulation_v2/**"
  - "decision_engine_v2/**"
  - "risk_engine_v2/**"
  - "**/*_v2.py"
---
# Version 2 Scope Guard

- Treat Version 2 as the default and only active implementation area for this workspace.
- Limit code edits to:
  - `simulation_v2/**`
  - `decision_engine_v2/**`
  - `risk_engine_v2/**`
  - root or nested files matching `*_v2.py`
- Avoid reading or modifying non-v2 folders unless the user explicitly asks for cross-version comparison or migration work.
- If a requested change appears to require non-v2 files, pause and ask for confirmation before proceeding.
- Prefer tests under v2 paths when validating behavior (`simulation_v2/tests`, `decision_engine_v2/tests`, `risk_engine_v2/tests`).
