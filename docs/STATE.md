# State

Graphify answers what exists; `DECISIONS.md` explains why; `CURRENT.json` records current work. Detailed history is stored per task and logs are gitignored.

Run `fame self-check` to validate this state without an LLM. It checks the schema version, required state files and config, task directory/artifact identities, and that `CURRENT.json` agrees with its referenced task. The command returns a nonzero status and per-file diagnostics for any inconsistency.
