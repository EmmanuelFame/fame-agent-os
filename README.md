# Fame Agent OS

Fame is a portable Python CLI above Codex that optimizes verified engineering work per token. It routes work through abstract `architect`, `builder`, and `operator` roles, rather than permanently coupling policy to model names.

Install once per machine with `uv tool install --editable .`, then run `fame init` in each Git project. Machine configuration lives in `~/.config/fame/config.json` (or `$XDG_CONFIG_HOME/fame`); portable project knowledge is in `.fame/`.

`fame route` deterministically selects F0–F5: F0 is tooling without an LLM; F1 is mechanical operator work; F2/F3 are normal/difficult builder work; F4/F5 isolate architect, builder, and verifier phases. `--budget` controls escalation and `--max-tier` is a hard stop. `fame task --dry-run` never calls Codex.

Graphify is optional navigation memory; source remains authoritative. Fame records concise task state, phase handoffs, JSONL telemetry, and deterministic verification. Production projects (`fame init --production`) require an explicit worktree for modifying tasks; Fame never merges, deploys, restarts services, uses `--yolo`, or enables Fast tier by default.

Useful commands: `fame doctor`, `fame models`, `fame route "Change button label"`, `fame task "Add a CRUD endpoint" --dry-run`, `fame status`, and `fame usage`.
