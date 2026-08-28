---
name: fame
description: Route repository engineering work through Fame before broad exploration.
---

# Fame Agent OS

Use this skill for repository engineering requests, including explicit `$fame ...` requests.

1. Call `fame_route` before broad repository exploration.
2. Respect its classification, selected agent, phases, blocked state, max-tier, and production requirements.
3. Call `fame_preflight`, then `fame_prepare_task` to provision the isolated workspace before modifying files. If a worktree path is returned, work there only.
4. Perform bounded read-only target discovery, then call `fame_bind_task_scope` with the actual target paths before writing changes.
5. Delegate to the exact selected Fame custom agent. Do not independently choose Sol/Terra/Luna or duplicate its work.
6. Call `fame_finish_task` after implementation so scoped deterministic verification and state recording run before reporting completion; do not run unrelated monorepo suites.
7. Use `fame_resume_task` or `fame_close_task` only when the user explicitly asks to recover or close an existing task. New requests always get a new task ID.
8. Never merge, deploy, restart services, delete persistent worktrees, or bypass an F5 human gate.

Keep responses concise. Return paths and state references rather than large file bodies. For non-engineering conversation, do not activate this workflow.
