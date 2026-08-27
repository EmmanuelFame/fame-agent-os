# Architecture

Fame has deterministic routing, configurable role-to-model resolution, isolated Codex phase runs, concise `.fame` state, deterministic verification, and append-only telemetry. Prompts receive task artifacts rather than prior transcripts.

Version 1.3 adds a frontend-neutral extension boundary. The stdio MCP server exposes deterministic Fame control-plane operations; the Codex extension invokes the installed skill and project custom agents, while the existing `CodexRunner` remains the CLI/headless execution backend. `fame_prepare_task` owns preflight and worktree allocation, and `fame_finish_task` owns verification and state recording. No MCP operation merges, deploys, restarts, or deletes persistent worktrees.

Context construction is bounded and does not embed repository contents. Each phase records prompt size and source-file limits alongside total, cached, and fresh (`total - cached`) input tokens. The verifier receives a concise builder handoff containing a bounded changed-file list and starts from the diff rather than a repository-wide re-ingestion. `fame benchmark` compares the telemetry of two task IDs without calling an LLM.
