# VPS

Install Fame once on a server and initialize each repository. Commit portable state, not local logs or caches. Set `production: true` for projects that need worktree isolation. Fame never deploys or merges automatically.

For a production change, run `fame task "…" --worktree`. Fame allocates the real task ID before execution, creates `fame/FAME-0001` (for example), and runs every phase and configured verification command in a persistent sibling worktree at `../.fame-worktrees/<repository>/FAME-0001`. The live checkout must be clean; Fame refuses dirty repositories, existing unregistered directories, and branch collisions. If a registered task worktree already exists, it is reported for manual review rather than overwritten or deleted.

Review the reported worktree and branch, run any additional checks there, and merge/deploy/restart manually under your VPS change process. Configure at least one deterministic command in `.fame/config.json` under `verification.commands`; `fame doctor` marks production projects without one unsafe, and such tasks fail verification rather than claiming success.
