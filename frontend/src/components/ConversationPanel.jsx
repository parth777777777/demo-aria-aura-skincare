import { AlertCircle, Sparkles } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ui/conversation";
import { Persona } from "@/components/ai-elements/persona.jsx";
import { OrderCard } from "./OrderCard.jsx";
import { SampleOrders } from "./SampleOrders.jsx";
import { getOrderDisplays } from "../lib/orderRendering.js";

const labels = {
  idle: "Ready when you are",
  connecting: "Connecting",
  listening: "Listening",
  thinking: "Aria is thinking",
  speaking: "Aria is speaking",
  ended: "Call ended",
  error: "Call error",
};

export function ConversationPanel({
  state,
  voiceState,
  errorMessage,
  sessionLimit,
  debug,
  micStats = { frames: 0, bytes: 0 },
  audioForwarded = { frames: 0, bytes: 0 },
  providerActivity = false,
  isAccountMode = false,
}) {
  const actionTools = state.tools.filter((tool) =>
    ["cancel_order", "place_order"].includes(tool.name),
  );
  const orderDisplays = getOrderDisplays(state.tools);
  return (
    <section
      className="flex min-w-0 flex-col overflow-hidden rounded-none border border-border bg-card shadow-sm lg:min-h-[730px]"
      aria-labelledby="conversation-title"
    >
      <div className="flex items-center justify-between border-b border-border px-5 py-5 sm:px-[29px]">
        <div>
          {state.status.state === "live" && (
            <span className="text-[13px] font-bold tracking-[.16em] text-muted-foreground">
              LIVE CALL
            </span>
          )}
          <h2
            id="conversation-title"
            className="mt-1 font-heading text-[28px] sm:text-[30px]"
          >
            Your conversation
          </h2>
        </div>
        <span className="flex items-center gap-2 rounded-full border border-border px-2.5 py-2 text-sm text-muted-foreground">
          <i
            className={`size-1.5 rounded-full ${voiceState === "live" ? "bg-green-700" : "bg-border"}`}
          />
          {voiceState === "live" ? "In call" : labels[voiceState]}
        </span>
      </div>
      {sessionLimit && (
        <Alert className="mx-4 mt-4 w-auto min-w-0 max-w-[calc(100%-2rem)] border-amber-300 bg-amber-50 text-amber-950 sm:mx-7">
          <AlertCircle />
          <AlertDescription>
            This call ended because its time limit was reached.
          </AlertDescription>
        </Alert>
      )}
      {errorMessage && (
        <Alert
          variant="destructive"
          className="mx-4 mt-4 w-auto min-w-0 max-w-[calc(100%-2rem)] text-[var(--error-ink)] [&_[data-slot=alert-description]]:text-current sm:mx-7"
        >
          <div>
            Microphone frames: {micStats.frames} · bytes sent: {micStats.bytes}
          </div>
          <AlertCircle />
          <AlertDescription>{errorMessage}</AlertDescription>
        </Alert>
      )}
      {isAccountMode &&
        state.tools.some(
          (tool) => tool.result?.error?.code === "ACCOUNT_FEATURES_NOT_READY",
        ) && (
          <Alert className="mx-4 mt-4 w-auto border-amber-300 bg-amber-50 text-amber-950 sm:mx-7">
            <AlertCircle />
            <AlertDescription>
              Demo-account order actions aren’t available yet. No order action
              was completed.
            </AlertDescription>
          </Alert>
        )}
      {actionTools.length > 0 && (
        <div className="grid gap-2 px-4 pt-4 sm:px-7" aria-live="polite">
          {actionTools.map((tool) => {
            const code = tool.result?.error?.code;
            let message = null;
            if (tool.result?.ok === true) {
              message =
                tool.name === "cancel_order"
                  ? "Aura confirmed the cancellation."
                  : "Aura confirmed the order placement.";
            } else if (code === "CONFIRMATION_REQUIRED") {
              message =
                "Waiting for confirmation in your conversation with Aria.";
            } else if (tool.result?.ok === false) {
              message =
                "Aura did not complete this action. Aria can explain what happened.";
            } else if (tool.result == null) {
              message = "Aria is checking this action with Aura…";
            }
            return message ? (
              <p
                key={tool.call_id}
                className="rounded-xl border border-border bg-muted px-4 py-3 text-sm"
                role="status"
              >
                {message}
              </p>
            ) : null;
          })}
        </div>
      )}
      <Conversation
        className="min-h-[300px] flex-1 overflow-hidden"
        aria-label="Conversation transcript"
      >
        <ConversationContent className="min-w-0 px-4 py-5 sm:px-7">
          {state.turns.length === 0 && (
            <div className="mx-auto flex min-h-[300px] max-w-[420px] flex-col items-center justify-center text-center">
              <div className="mb-4 grid size-11 place-items-center rounded-full bg-muted text-primary">
                <Sparkles size={19} />
              </div>
              <h3 className="mb-2 font-heading text-xl">
                Your conversation will appear here
              </h3>
              <p className="text-sm leading-relaxed text-muted-foreground">
                When you start a call, Aria's replies and helpful order details
                will show up in this space.
              </p>
              {!isAccountMode && <SampleOrders />}
            </div>
          )}
          {state.turns.map((turn) => (
            <div
              className={`mb-5 flex max-w-[96%] gap-3 animate-in fade-in slide-in-from-bottom-2 duration-250 motion-reduce:animate-none ${turn.role === "user" ? "ml-auto flex-row-reverse" : ""}`}
              key={turn.turn_id}
            >
              {turn.role === "user" ? (
                <div className="grid size-[29px] shrink-0 place-items-center rounded-full bg-muted text-sm text-primary">
                  Y
                </div>
              ) : (
                <div
                  className="grid size-[29px] shrink-0 place-items-center overflow-hidden rounded-full bg-muted"
                  aria-hidden="true"
                >
                  <Persona
                    variant="opal"
                    state={
                      ["listening", "thinking", "speaking"].includes(voiceState)
                        ? voiceState
                        : "idle"
                    }
                    className="size-[29px]"
                  />
                </div>
              )}
              <div className="min-w-0">
                <div
                  className={`mb-1.5 mt-0.5 flex items-center gap-2 text-sm ${turn.role === "user" ? "justify-end" : ""}`}
                >
                  <strong>{turn.role === "user" ? "You" : "Aria"}</strong>
                  {turn.interrupted && (
                    <span className="rounded-full bg-amber-100 px-2 py-1 text-sm text-amber-950">
                      Interrupted
                    </span>
                  )}
                </div>
                <div
                  className={`break-words rounded-[4px_16px_16px] bg-muted p-3.5 text-base leading-relaxed ${turn.role === "user" ? "rounded-[16px_4px_16px_16px]" : ""}`}
                >
                  {turn.text}
                </div>
              </div>
            </div>
          ))}
          {orderDisplays.length > 0 && (
            <section className="mt-5" aria-label="Orders from Aura">
              {orderDisplays.some(
                (order) => order.source === "mock_db_sample_data",
              ) && (
                <p className="mb-3 text-sm text-muted-foreground">
                  Sample demo orders
                </p>
              )}
              <ul className="grid gap-3">
                {orderDisplays.map((order) => (
                  <OrderCard key={order.id} order={order} />
                ))}
              </ul>
            </section>
          )}
          {state.tools.some(
            (tool) =>
              tool.name === "list_orders" &&
              tool.result?.ok === true &&
              Array.isArray(tool.result.orders) &&
              tool.result.orders.length === 0,
          ) && (
            <p
              className="mt-5 rounded-xl border border-border bg-muted p-4 text-sm"
              role="status"
            >
              {state.tools.findLast(
                (tool) =>
                  tool.name === "list_orders" && tool.result?.ok === true,
              )?.result.source === "mock_db_sample_data"
                ? "No sample demo orders were found."
                : "Aura found no orders for this demo identity."}
            </p>
          )}
        </ConversationContent>
        <ConversationScrollButton aria-label="Scroll to latest message" />
      </Conversation>
      {debug && (
        <div
          className="mx-4 mb-3 max-h-24 overflow-auto rounded border border-border bg-muted p-2 font-mono text-sm text-muted-foreground sm:mx-7"
          aria-label="Tool event log"
        >
          {state.tools.length
            ? state.tools.map((tool) => (
                <div key={tool.call_id}>
                  {tool.call_id}:{" "}
                  {tool.result == null
                    ? "pending"
                    : tool.result.ok === false
                      ? "failed"
                      : "complete"}
                </div>
              ))
            : "No tool events"}
          <div>
            Mic rejected: not live={micStats.rejected?.not_live ?? 0}, socket
            closed={micStats.rejected?.socket_not_open ?? 0}, backpressure=
            {micStats.rejected?.buffered_amount ?? 0}; bufferedAmount=
            {micStats.bufferedAmount ?? 0}
          </div>
          <div>
            Input transcripts={micStats.inputTranscripts ?? 0}, output
            transcripts={micStats.outputTranscripts ?? 0}, audio bytes received=
            {micStats.audioBytesReceived ?? 0}
          </div>
        </div>
      )}
      <footer className="border-t border-border px-5 py-3 text-sm text-muted-foreground sm:px-[29px]">
        <div>
          {isAccountMode
            ? "Aria answers questions about orders linked to this temporary demo identity."
            : "Aria answers questions about Aura orders. Sample data shown."}
        </div>
        {state.status.state === "live" && (
          <div className="mt-2 text-xs" aria-live="polite">
            Mic sent: {micStats.frames} frames · Backend forwarded:{" "}
            {audioForwarded.frames} frames · Gemini activity:{" "}
            {providerActivity ? "observed" : "waiting"}
          </div>
        )}
      </footer>
    </section>
  );
}
