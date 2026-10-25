export function selectVoiceState(state) {
  const status = state.status?.state
  if (status === 'connecting') return 'connecting'
  if (status === 'error') return 'error'
  if (status === 'ended') return 'ended'
  if (status !== 'live') return 'idle'
  if (state.tools.some((tool) => tool.result == null)) return 'thinking'
  const latestAria = [...state.turns].reverse().find((turn) => turn.role === 'aria')
  return latestAria && !latestAria.final ? 'speaking' : 'listening'
}
