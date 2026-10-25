import test from 'node:test'
import assert from 'node:assert/strict'
import { callReducer, initialCallState } from '../src/state/callReducer.js'
import { selectVoiceState } from '../src/state/selectors.js'

const apply = (events, state = initialCallState) => events.reduce(callReducer, state)
const transcript = (turn_id, role, text, final) => ({ type: 'transcript', turn_id, role, text, final })
const liveState = () => callReducer(initialCallState, { type: 'status', state: 'live' })

test('transcript turns are replaced by turn_id for both roles', () => {
  const state = apply([transcript('u1', 'user', 'first', false), transcript('a1', 'aria', 'first', false), transcript('u1', 'user', 'replacement', false), transcript('a1', 'aria', 'replacement', false)])
  assert.equal(state.turns.length, 2)
  assert.equal(state.turns[0].text, 'replacement')
  assert.equal(state.turns[1].text, 'replacement')
})

test('a partial transcript is replaced by its final transcript', () => {
  const state = apply([transcript('t1', 'aria', 'Hel', false), transcript('t1', 'aria', 'Hello', true)])
  assert.deepEqual(state.turns[0], { turn_id: 't1', role: 'aria', text: 'Hello', final: true })
})

test('a late partial transcript cannot overwrite a final turn', () => {
  const state = apply([transcript('t1', 'user', 'Complete', true), transcript('t1', 'user', 'late partial', false)])
  assert.equal(state.turns[0].text, 'Complete')
  assert.equal(state.turns[0].final, true)
})

test('tool_call and tool_result pair by call_id', () => {
  const state = apply([{ type: 'tool_call', call_id: 'c1', name: 'lookup', args: {} }, { type: 'tool_result', call_id: 'c1', name: 'lookup', result: { ok: true } }])
  assert.equal(state.tools.length, 1)
  assert.deepEqual(state.tools[0].result, { ok: true })
})

test('tool_result arriving before tool_call is retained without crashing', () => {
  const result = { ok: true }
  const state = apply([{ type: 'tool_result', call_id: 'c1', result }, { type: 'tool_call', call_id: 'c1', name: 'lookup', args: {} }])
  assert.equal(state.tools.length, 1)
  assert.deepEqual(state.tools[0].result, result)
})

test('duplicate tool_result does not duplicate the call entry', () => {
  const state = apply([{ type: 'tool_call', call_id: 'c1' }, { type: 'tool_result', call_id: 'c1', result: { ok: true } }, { type: 'tool_result', call_id: 'c1', result: { ok: true, repeated: true } }])
  assert.equal(state.tools.length, 1)
  assert.deepEqual(state.tools[0].result, { ok: true, repeated: true })
})

test('interrupted finalizes the latest Aria turn and marks it interrupted', () => {
  const state = apply([transcript('a1', 'aria', 'Speaking', false), { type: 'interrupted' }])
  assert.equal(state.turns[0].final, true)
  assert.equal(state.turns[0].interrupted, true)
  assert.equal(state.interrupted, true)
})

for (const reason of ['user_ended', 'session_limit', 'error']) {
  test(`ended status preserves the ${reason} reason`, () => {
    const state = callReducer(initialCallState, { type: 'status', state: 'ended', reason })
    assert.equal(state.status.reason, reason)
    assert.equal(selectVoiceState(state), 'ended')
  })
}

test('unknown event types are ignored', () => {
  assert.equal(callReducer(initialCallState, { type: 'future_event' }), initialCallState)
})

test('summary event is stored', () => {
  const summary = { customer_intent: 'cancellation', order_id: 'ORD-103', resolution_status: 'resolved', call_summary: 'Done' }
  assert.deepEqual(callReducer(initialCallState, { type: 'summary', summary }).summary, summary)
})

test('call_requested and reset after ended clear prior call state', () => {
  const ended = apply([{ type: 'status', state: 'live' }, transcript('a1', 'aria', 'Hi', true), { type: 'tool_call', call_id: 'c1' }, { type: 'error', code: 'INTERNAL', message: 'failed', recoverable: false }, { type: 'summary', summary: { call_summary: 'old' } }, { type: 'status', state: 'ended', reason: 'error' }])
  const requested = callReducer(ended, { type: 'call_requested' })
  assert.equal(selectVoiceState(requested), 'connecting')
  assert.deepEqual(requested.turns, [])
  assert.deepEqual(requested.tools, [])
  assert.equal(requested.summary, null)
  assert.equal(requested.error, null)
  assert.deepEqual(callReducer(ended, { type: 'reset' }), initialCallState)
})

test('reducer does not mutate deeply frozen input state', () => {
  const state = Object.freeze({
    status: Object.freeze({ state: 'live', reason: null }),
    turns: Object.freeze([Object.freeze({ turn_id: 'a1', role: 'aria', text: 'Hi', final: false })]),
    tools: Object.freeze([Object.freeze({ call_id: 'c1', result: null })]),
    summary: null,
    error: null,
    interrupted: false,
  })
  assert.doesNotThrow(() => callReducer(state, { type: 'interrupted' }))
  assert.equal(state.turns[0].final, false)
  assert.equal(state.interrupted, false)
})

test('recoverable error is stored without changing call status', () => {
  const state = callReducer(liveState(), { type: 'error', code: 'BAD_MESSAGE', message: 'Malformed', recoverable: true })
  assert.equal(state.status.state, 'live')
  assert.equal(state.error.recoverable, true)
})

test('non-recoverable error sets call status to error', () => {
  const state = callReducer(liveState(), { type: 'error', code: 'SESSION_LIMIT', message: 'Full', recoverable: false })
  assert.deepEqual(state.status, { state: 'error', reason: 'error' })
  assert.equal(selectVoiceState(state), 'error')
})

test('selector returns idle', () => assert.equal(selectVoiceState(initialCallState), 'idle'))
test('selector returns connecting', () => assert.equal(selectVoiceState(callReducer(initialCallState, { type: 'status', state: 'connecting' })), 'connecting'))
test('selector returns listening', () => assert.equal(selectVoiceState(liveState()), 'listening'))
test('selector returns thinking for a pending tool call', () => assert.equal(selectVoiceState(callReducer(liveState(), { type: 'tool_call', call_id: 'c1' })), 'thinking'))
test('selector returns speaking for a non-final Aria turn', () => assert.equal(selectVoiceState(callReducer(liveState(), transcript('a1', 'aria', 'Hello', false))), 'speaking'))
test('selector returns ended', () => assert.equal(selectVoiceState(callReducer(initialCallState, { type: 'status', state: 'ended' })), 'ended'))
test('selector returns error', () => assert.equal(selectVoiceState(callReducer(initialCallState, { type: 'status', state: 'error' })), 'error'))

test('thinking clears when the matching tool_result arrives', () => {
  const pending = callReducer(liveState(), { type: 'tool_call', call_id: 'c1' })
  const resolved = callReducer(pending, { type: 'tool_result', call_id: 'c1', result: { ok: true } })
  assert.equal(selectVoiceState(pending), 'thinking')
  assert.equal(selectVoiceState(resolved), 'listening')
})
