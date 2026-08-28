# Codex Extension Native Mode

Fame v1.3 is intended to be used from the Codex VS Code extension. The project installer adds a stdio MCP server, the concise Fame skill, and role profiles for operator, builder, architect, and verifier work.

## Local setup

```bash
uv tool install --editable /path/to/fame-agent-os
cd /path/to/project
fame init
fame codex install --project
fame doctor
fame codex status
```

Reload the Codex extension after installation. Confirm that the MCP server is connected and the Fame skill is visible using the equivalent MCP/skills views in the installed extension. Then send either `$fame Add a harmless deterministic test change.` or the natural-language equivalent. Fame must route before broad exploration, return the selected agent, and verify before completion.

## Remote SSH / VPS

Install Fame on the VPS, open `/srv/project` through VS Code Remote SSH, then run:

```bash
fame init --production
# edit .fame/config.json and set verification.commands
fame codex install --project
fame doctor
fame codex status
```

Reload the remote extension. Production tasks are prepared in persistent sibling worktrees under `../.fame-worktrees/<repo>/FAME-####`; the live checkout must be clean and is never modified by the delegated agent. Review and merge manually. New requests never auto-resume failed or interrupted tasks; recovery is explicit through `fame_resume_task` or `fame resume`, and explicit closure is available through `fame_close_task` or `fame close`.

## Safety and limits

Fame blocks max-tier violations and F5 work without explicit approval before creating task resources. Deterministic verification runs without `shell=True`. F1/F2 extension tasks advertise a deterministic-first policy; higher-risk routes retain strong verifier review. When target paths are not yet known, the extension can provision first, inspect safely, then call `fame_bind_task_scope` before edits. Extension-native token usage is not counted with the same fidelity as CLI JSONL telemetry when the extension does not expose it; Fame reports only measured CLI usage.

If the Codex CLI is absent, extension-native operation can still be healthy because the MCP server is launched by the installed `fame` command. `fame doctor` distinguishes the CLI backend, MCP launchability, skill, and agent installation. The CLI remains the fallback for CI and headless operation.
