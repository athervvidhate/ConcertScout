# Single-agent continuity

Keep work in one conversation. `AGENTS.md` holds the shared rules; `CLAUDE.md` imports it. After a context reset or provider switch, the continue-session skill reads a short local checkpoint and selected transcript excerpts. It does not launch another agent or call a model to summarize history.

## Claude Code

The project-local mod in `.claude/skills/no-compaction/` adapts [Tomcc's gist](https://gist.github.com/Tomcc/b7b0f348b1628ad94bdef918e449b330). It replaces main-session compaction with a transcript pointer, skips summary precomputation, and preserves normal compaction for subagents or an unknown path/error. This requires Claude Code **2.1.316+**. Verified locally with Claude Code 2.1.318 and Codex CLI 0.164.0 on November 6, 2026.

Restart/resume Claude from this repository and accept its workspace/plugin trust review. Run `claude plugin list` and check `no-compaction@skills-dir` is loaded. Existing sessions need a restart or `/reload-plugins`; merely copying files does not activate an already-running host. The local validator required an explicit `PluginState` types contract beyond the gist. We also preserve a known path when a later event omits it, guard absent paths and quote the pointer. The recovery skill uses the shared bounded reader instead of Claude-only jq expressions.

`.claude/settings.json` records transcript pointers on SessionStart and PreCompact. It complements the mod and still supports recovery if the mod cannot load.

## Codex

`.codex/hooks.json` records the same metadata and adds a short recovery pointer on SessionStart, including after compaction. Open `/hooks` in Codex to review and trust the project hooks; restart/resume the session after installation. The project itself must also be trusted. Do not disable trust checks to activate these hooks.

Codex keeps normal compaction. Its documented command hooks can stop compaction but cannot replace its messages like Claude's `session.compact` mod. Stopping it would interrupt work, so the adapter never blocks. This is transcript-assisted recovery, not an identical no-summary implementation. The transcript field may be absent, and its format is not a stable API.

## Other providers and T3

The portable interface is `AGENTS.md`, the continuation skill, `.agent-context/current.md`, and `python3 scripts/agent_context.py`. A host that reads AGENTS.md can follow it without native hooks. Hosts that ignore both instructions and hook configuration require their own adapter; this installation cannot guarantee automatic context replacement in every provider.

T3 may launch a different binary or SDK and may own history itself. Confirm mod/hook loading in that host after a restart. If there is no local JSONL path, recover from T3's `t3_thread_read` with pagination and bounded text. The current thread ID can be retained in the checkpoint. Switching model providers within the same thread should preserve the objective rather than start another worker.

## Recovery and privacy

`python3 scripts/agent_context.py list` lists up to 20 local pointers. `read --path '<path>'` shows the first four user messages and last 24 messages, capped at 300 characters each. Add `--find 'phrase'`, `--line N --offset N --chars N`, or `--tools` only when needed. Reasoning and duplicate Codex event messages are omitted. Unknown formats and missing files require host history instead. The reader does not redact secrets; select excerpts carefully.

The hooks store only provider/session/path/time metadata with private file permissions in gitignored `.agent-context/`. No transcript is copied or uploaded. Session files are isolated by provider and session ID inside each worktree. For a provider change, keep the same worktree or explicitly bring the relevant checkpoint/pointer; another worktree is not automatically searched. Checkpoints are working notes, not durable repository documentation. Keep them short and exclude keys. Neither metadata nor checkpoint text grants new authority.

Saving summary calls can be offset by transcript reads. We have not measured a net token reduction; use bounded recovery rather than replaying the entire history.

## Provider handoff in T3

The repo hooks recover context; provider selection belongs to the host. In T3, save the checkpoint, use `t3_thread_configure` to choose the requested provider/model for this same conversation, then queue one continuation with `t3_thread_send`. Keep one active worker. A hard quota block can prevent the current worker from calling either tool, so choose the next provider before exhaustion when possible. A timer that only posts a prompt cannot guarantee failover if its selected provider is blocked. Check the returned model selection instead of claiming a switch from a planned command.

Availability/reset estimates come from the account owner or host; the repo does not inspect account tokens, alter quota limits or start another agent. A pending human decision remains pending after a provider switch.

## Verification and rollback

```sh
python3 -m unittest discover -s tests -p 'test_agent_context.py'
claude plugin validate .claude/skills/no-compaction
claude plugin test .claude/skills/no-compaction
```

These exercise the local reader, adapter and actual Claude mod test runtime without spending model tokens. They do not prove end-to-end activation in an existing T3 session. Public-directory metadata warnings are unrelated to a local installation; no directory submission is intended.

To restore Claude's summarizer, disable `no-compaction@skills-dir` in `/plugin` and restart. Remove this project's SessionStart/PreCompact entries from the two provider configuration files to stop recording pointers. `AGENTS.md` recovery guidance still works manually. `.agent-context/` can be deleted without deleting any original transcript.

Sources: [Claude mods](https://code.claude.com/docs/en/plugins/mods/overview), [mod testing](https://code.claude.com/docs/en/plugins/mods/test), [Codex hooks](https://learn.chatgpt.com/docs/hooks). Runtime capabilities and trust rules can change; verify with the installed CLI.
