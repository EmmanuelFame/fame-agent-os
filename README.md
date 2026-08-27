# Fame Agent OS

Fame is a portable Python CLI above Codex that optimizes verified engineering work per token. It routes work through abstract `architect`, `builder`, and `operator` roles, rather than permanently coupling policy to model names.

Install once per machine with `uv tool install --editable .`, then run `fame init` in each Git project. Machine configuration lives in `~/.config/fame/config.json` (or `$XDG_CONFIG_HOME/fame`); portable project knowledge is in `.fame/`.

`fame route` deterministically selects F0–F5: F0 is tooling without an LLM; F1 is mechanical operator work; F2/F3 are normal/difficult builder work; F4/F5 isolate architect, builder, and verifier phases. `--budget` controls escalation and `--max-tier` is a hard stop. `fame task --dry-run` never calls Codex.

Graphify is optional navigation memory; source remains authoritative. Fame records concise task state, phase handoffs, JSONL telemetry, and deterministic verification. Production projects (`fame init --production`) require `fame task "…" --worktree`; phases run in a persistent `../.fame-worktrees/<repo>/FAME-####` task branch, while the live checkout remains unchanged. `fame doctor` reports production projects without configured verification commands as unsafe. Fame never merges, deploys, restarts services, uses `--yolo`, or enables Fast tier by default.

Useful commands: `fame doctor`, `fame models`, `fame route "Change button label"`, `fame task "Add a CRUD endpoint" --dry-run`, `fame status`, `fame self-check`, and `fame usage`.

## Context efficiency

Every phase log records total input, cached input, and fresh input (`total - cached`), plus cache ratio, a bounded-prompt diagnostic, and warnings for unusually high total/fresh input or low cache reuse. `fame usage --task FAME-0001 --json` reports the metrics by role. Compare runs with `fame benchmark --before FAME-0001 --after FAME-0002 --json`; it reports absolute deltas and fresh-input reduction ratio.

Prompts reference task state and bounded artifact paths instead of injecting repository contents. Builder work is limited to a small targeted source surface by default; verifier work begins from the bounded builder handoff and changed-file list, then uses deterministic checks. Limits are configurable under `.fame/config.json` `context` (`max_prompt_chars`, `max_source_files`, `total_input_warning_tokens`, `fresh_input_warning_tokens`, `min_cache_ratio`). A limit can be exceeded only when acceptance evidence needs it, with the reason recorded in the handoff.

`fame self-check` reads only `.fame` project state and exits nonzero when its schema marker, core state files, task artifacts, or current-task references are inconsistent. It never invokes Codex; use `--json` for machine-readable diagnostics.
