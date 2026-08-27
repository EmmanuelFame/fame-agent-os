# Architecture

Fame has deterministic routing, configurable role-to-model resolution, isolated Codex phase runs, concise `.fame` state, deterministic verification, and append-only telemetry. Prompts receive task artifacts rather than prior transcripts.

Context construction is bounded and does not embed repository contents. Each phase records prompt size and source-file limits alongside total, cached, and fresh (`total - cached`) input tokens. The verifier receives a concise builder handoff containing a bounded changed-file list and starts from the diff rather than a repository-wide re-ingestion. `fame benchmark` compares the telemetry of two task IDs without calling an LLM.
