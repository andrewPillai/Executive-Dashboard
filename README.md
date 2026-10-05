# Executive Dashboard

Northstar Scientific is a fictional, Avantor-inspired operations demo for eight executive and department audiences.

## Complete runnable handoff

Download `northstar-handoff-2026-10-05.zip` from [Releases](https://github.com/andrewPillai/Executive-Dashboard/releases). It includes source, compiled frontend, the complete 1.85-million-record synthetic database, saved workflow state, research, dependency locks, and verification results. Extract it and follow `START_HERE.txt`. Another LLM should read `LLM_HANDOFF.txt` first.

## Repository contents

Editable source, tests, data generation tools, research, and handoff documents are checked in here. SQLite databases and the compiled frontend are provided in the release ZIP. To run from this checkout, copy `application/data/northstar.sqlite`, `application/backend/workflow.sqlite`, and `application/frontend/dist/` from the extracted release into the same paths here, then follow `START_HERE.txt`.

The file manifest and its verifier describe the complete release bundle, including those release-only files.

## Status

React/TypeScript CSR frontend and FastAPI backend; eight audience dashboards; six connected business cases; human-approved workflow simulation. 13 backend tests and data integrity checks passed during packaging. Live AI, SAP integration, and enterprise authentication are not implemented. Role switching is not access control.

Read `application/integration-boundary.txt` before implementing live connections. Dependency environments and credentials are not included.
