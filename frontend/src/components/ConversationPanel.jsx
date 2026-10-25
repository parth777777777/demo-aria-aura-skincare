import { AlertCircle, Leaf, Sparkles } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { ScrollArea } from "@/components/ui/scroll-area";
import { OrderResult } from "./OrderCard.jsx";
import { SampleOrders } from "./SampleOrders.jsx";

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
  transcriptRef,
  debug,
  micStats = { frames: 0, bytes: 0 },
  audioForwarded = { frames: 0, bytes: 0 },
  providerActivity = false,
}) {
  return (
    <section
      className="flex min-w-0 flex-col overflow-hidden rounded-3xl border border-border bg-card shadow-sm lg:min-h-[730px]"
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
      <ScrollArea
        className="min-h-[300px] flex-1 overflow-hidden px-4 py-5 sm:px-7"
        ref={transcriptRef}
        aria-live="polite"
      >
        <div className="min-w-0">
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
              <SampleOrders />
            </div>
          )}
          {state.turns.map((turn) => (
            <div
              className={`mb-5 flex max-w-[96%] gap-3 animate-in fade-in slide-in-from-bottom-2 duration-250 motion-reduce:animate-none ${turn.role === "user" ? "ml-auto flex-row-reverse" : ""}`}
              key={turn.turn_id}
            >
              <div className="grid size-[29px] shrink-0 place-items-center rounded-full bg-muted text-sm text-primary">
                {turn.role === "user" ? "Y" : <Leaf size={14} />}
              </div>
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
                {turn.role === "aria" &&
                  turn.turn_id ===
                    [...state.turns]
                      .reverse()
                      .find((item) => item.role === "aria")?.turn_id &&
                  state.tools
                    .filter((tool) => tool.name === "get_order_details")
                    .map((tool) => (
                      <OrderResult key={tool.call_id} tool={tool} />
                    ))}
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>
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
        </div>
      )}
      <footer className="border-t border-border px-5 py-3 text-sm text-muted-foreground sm:px-[29px]">
        <div>Aria answers questions about Aura orders. Sample data shown.</div>
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
