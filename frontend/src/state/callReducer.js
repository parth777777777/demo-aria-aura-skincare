export const initialCallState = {
  status: { state: "idle", reason: null },
  turns: [],
  tools: [],
  summary: null,
  error: null,
  interrupted: false,
  audioForwarded: { frames: 0, bytes: 0 },
  providerActivity: false,
};

export function callReducer(state = initialCallState, event) {
  if (!event || typeof event.type !== "string") return state;

  switch (event.type) {
    case "call_requested":
      return {
        ...initialCallState,
        status: { state: "connecting", reason: null },
      };
    case "reset":
      return initialCallState;
    case "connection_lost":
      return {
        ...state,
        status: { state: "error", reason: "error" },
        error: {
          code: "CONNECTION_LOST",
          message: "Connection lost. Please try again.",
          recoverable: false,
        },
      };
    case "call_cancelled":
      return { ...state, status: { state: "idle", reason: null } };
    case "status":
      return {
        ...state,
        status: { state: event.state, reason: event.reason ?? null },
      };
    case "audio_forwarded":
      return {
        ...state,
        audioForwarded: {
          frames: Number(event.frames) || 0,
          bytes: Number(event.bytes) || 0,
        },
      };
    case "provider_activity":
      return { ...state, providerActivity: true };
    case "transcript": {
      if (typeof event.turn_id !== "string") return state;
      const turn = {
        turn_id: event.turn_id,
        role: event.role,
        text: event.text,
        final: Boolean(event.final),
      };
      const index = state.turns.findIndex(
        (item) => item.turn_id === event.turn_id,
      );
      const turns = [...state.turns];
      if (index < 0) turns.push(turn);
      else if (!state.turns[index].final || turn.final) turns[index] = turn;
      return { ...state, turns };
    }
    case "tool_call": {
      if (typeof event.call_id !== "string") return state;
      const index = state.tools.findIndex(
        (tool) => tool.call_id === event.call_id,
      );
      const tools = [...state.tools];
      const item = { ...event, result: index < 0 ? null : tools[index].result };
      if (index < 0) tools.push(item);
      else tools[index] = item;
      return { ...state, tools };
    }
    case "tool_result": {
      if (typeof event.call_id !== "string") return state;
      const index = state.tools.findIndex(
        (tool) => tool.call_id === event.call_id,
      );
      const tools = [...state.tools];
      const item =
        index < 0
          ? { call_id: event.call_id, name: event.name, result: event.result }
          : { ...tools[index], result: event.result };
      if (index < 0) tools.push(item);
      else tools[index] = item;
      return { ...state, tools };
    }
    case "interrupted": {
      const turns = [...state.turns];
      const index = turns.findLastIndex((turn) => turn.role === "aria");
      if (index < 0 || turns[index].final) return state;
      turns[index] = { ...turns[index], final: true, interrupted: true };
      return { ...state, turns, interrupted: true };
    }
    case "summary":
      return { ...state, summary: event.summary };
    case "error":
      return {
        ...state,
        status:
          event.recoverable === false
            ? { state: "error", reason: "error" }
            : state.status,
        error: {
          code: event.code,
          message: event.message,
          recoverable: event.recoverable,
        },
      };
    default:
      return state;
  }
}
