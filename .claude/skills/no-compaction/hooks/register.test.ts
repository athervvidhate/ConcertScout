import { expect, test } from 'claude-code/testing'

test('main-session compaction points to its transcript without summarizing', async ($, on) => {
  on('classic.SessionStart', () => ({}))
  on('session.compact', () => { throw new Error('summarizer must not run') })
  await $.classic.SessionStart({
    session_id: 'test', transcript_path: '/tmp/session.jsonl', cwd: '/tmp',
    hook_event_name: 'SessionStart', source: 'startup',
  })
  const result = await $.session.compact({ trigger: 'auto', messages: [] })
  expect(result.messages.length).toBe(1)
  expect(result.messages[0].text.includes('/tmp/session.jsonl')).toBe(true)
})

test('unknown transcript uses normal compaction', async ($, on) => {
  on('ui.toast', () => ({ value: undefined }))
  on('session.compact', () => ({ messages: [{ role: 'user', text: 'normal summary', toolUses: [] }] }))
  const result = await $.session.compact({ trigger: 'auto', messages: [] })
  expect(result.messages[0].text).toBe('normal summary')
})

test('subagents keep normal compaction', async ($, on) => {
  on('session.compact', () => ({ messages: [{ role: 'user', text: 'subagent summary', toolUses: [] }] }))
  const result = await $.session.compact({ trigger: 'auto', agentId: 'child', messages: [] })
  expect(result.messages[0].text).toBe('subagent summary')
})

test('precompute skips the summarizer', async ($, on) => {
  on('session.compact', () => { throw new Error('summarizer must not run') })
  const result = await $.session.compact({ trigger: 'precompute', messages: [] })
  expect(result.skip).toBe('no-compaction mod')
})

test('an empty later prompt path preserves the known session transcript', async ($, on) => {
  on('classic.SessionStart', () => ({}))
  on('classic.UserPromptSubmit', () => ({}))
  on('session.compact', () => { throw new Error('summarizer must not run') })
  await $.classic.SessionStart({
    session_id: 'test', transcript_path: '/tmp/history with spaces.jsonl', cwd: '/tmp',
    hook_event_name: 'SessionStart', source: 'startup',
  })
  await $.classic.UserPromptSubmit({
    session_id: 'test', transcript_path: '', cwd: '/tmp',
    hook_event_name: 'UserPromptSubmit', prompt: 'continue',
  })
  const result = await $.session.compact({ trigger: 'auto', messages: [] })
  expect(result.messages[0].text.includes('/tmp/history with spaces.jsonl')).toBe(true)
})
