# Session continuity — November 6, 2026

Published the previously local continuation setup: shared AGENTS instructions, a Claude import, a short recovery skill, bounded Claude/Codex transcript reader, private metadata hooks and a Claude no-compaction mod adapted from the requested gist. No transcript, checkpoint or credential is committed. The original root-checkout files remain untouched.

- `make check-context`: six contracts passed. They exercise real configured hook commands from a git subdirectory, private provider/session metadata, missing paths/unknown formats, bounded excerpts, explicit tool output and omission of reasoning/duplicate messages.
- Claude Code2.1.318 `plugin test`: five tests passed in the native mod runtime, without model/network requests. They cover transcript replacement, normal fallback, precompute skip and retaining a known transcript when a later event has an empty path.
- Claude `plugin validate` passed for local use. Public-directory license/icon submission requirements remain outside this local installation; no catalog submission is claimed.
- Claude `plugin list` showed `no-compaction@skills-dir` loaded from the active product worktree.
- The continue-session skill passed the skill validator using the API Python environment's YAML dependency.
- `make check`: lint/types,133 backend contracts and19 frontend data tests passed. CI now also runs the six transcript/adapter contracts.
- The local frontend/API remain running. No product runtime behavior or paid-provider path changes in this commit.

Official hook/mod references were rechecked. Codex CLI0.164.0 supports the configured SessionStart/PreCompact shape; it retains normal compaction and receives a recovery pointer. Claude can replace its main-session compaction through the mod. Other providers rely on shared instructions or their own host adapter. A future provider switch must verify host loading; local runtime tests do not prove every T3 integration path. No net token-saving measurement or automatic quota failover is claimed.
