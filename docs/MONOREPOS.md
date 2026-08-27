# Monorepos and scoped verification

Fame keeps one `.fame` control plane per Git repository. Configure logical projects with `scopes` in `.fame/config.json`; legacy repositories can keep only `verification.commands` unchanged.

```json
{
  "scopes": [
    {
      "name": "frontend",
      "paths": ["web/**"],
      "priority": 10,
      "verification": {
        "required": ["npm --prefix web test"],
        "optional": ["npm --prefix web run build"],
        "optional_when_paths": ["web/package.json"]
      },
      "preparation": {"commands": ["npm --prefix web ci"]},
      "environment_notes": ["Node 20 is required"],
      "production_sensitive": true
    },
    {"name": "api", "paths": ["api/**"], "verification": {"required": ["python3 -m unittest discover -s api/tests"]}}
  ]
}
```

Fame selects scopes from explicit component names and configured path patterns, then combines required commands once in priority/configuration order. If no scope can be determined, MCP and CLI responses report candidate scopes and run no scoped command until target paths are known. `fame doctor` reports missing ownership patterns, patterns matching no tracked files, production-sensitive scopes without required checks, and legacy repository-wide mode. Optional checks stay available but run only when a configured path policy, explicit acceptance request, or required policy selects them.

For production worktrees, `preparation.commands` are explicit project-owned argv strings, executed without a shell only inside the persistent task worktree. Fame never infers installs from manifests and never links live `vendor`, `node_modules`, `.venv`, or build directories into a task worktree. A failed preparation is recorded and leaves the worktree recoverable; the live Remote SSH/VPS checkout remains untouched.
