import { FileText, Phone, PhoneOff, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Persona } from "@/components/ai-elements/persona.jsx";

const labels = {
  idle: "Ready when you are",
  connecting: "Connecting",
  listening: "Listening",
  thinking: "Aria is thinking",
  speaking: "Aria is speaking",
  ended: "Call ended",
  error: "Call error",
};

export function CallPanel({
  state,
  voiceState,
  time,
  callActive,
  debug,
  runReplay,
  runCall,
  navigateSummary,
  startAnother,
  scenario,
  ScenarioPicker,
  runScenario,
  playTestTone,
}) {
  return (
    <section
      className="flex min-h-[650px] flex-col overflow-hidden bg-[#f0ede6] lg:min-h-0"
      aria-labelledby="call-title"
    >
      <div className="relative h-[190px] shrink-0 overflow-hidden bg-gradient-to-br from-[#dce5d6] via-[#9daf99] to-[#758b76] sm:h-[230px] 2xl:h-[250px]">
        <img
          src="/src/assets/laura-jaeger-7LAbLSKbkaQ-unsplash.jpg"
          alt=""
          className="absolute size-full object-cover"
          onError={(event) => {
            event.currentTarget.style.display = "none";
          }}
        />
      </div>
      <div className="flex flex-1 flex-col items-center px-6 py-8 text-center sm:px-10 sm:py-9">
        <span className="text-xs font-medium tracking-[.2em] text-muted-foreground">
          YOUR AURA CARE COMPANION
        </span>
        <h1
          id="call-title"
          className="mt-5 max-w-[540px] font-heading text-[36px] font-medium leading-tight tracking-[-.045em] sm:text-[42px] 2xl:text-[46px]"
        >
          You’re in good hands.
        </h1>
        <div className="my-7 flex flex-col items-center gap-4 sm:my-8">
          <div
            className="grid size-[124px] shrink-0 place-items-center"
            aria-hidden="true"
          >
            <Persona
              variant="opal"
              state={
                ["listening", "thinking", "speaking"].includes(voiceState)
                  ? voiceState
                  : "idle"
              }
              className="size-[124px]"
            />
          </div>
          <div className="flex flex-col items-center gap-1">
            <strong className="text-lg" aria-live="polite">
              {labels[voiceState]}
            </strong>
            <span
              className="text-sm tabular-nums text-muted-foreground"
              aria-live="off"
            >
              {state.status.state === "live" ? time : " "}
            </span>
          </div>
        </div>
        <div className="mt-auto flex w-full flex-col items-center gap-3">
          {state.status.state === "ended" ? (
            <div className="grid w-full max-w-[300px] gap-2">
              {state.status.reason === "error" ? null : state.summary ? (
                <Button
                  className="h-[48px] w-full rounded-full text-base"
                  onClick={navigateSummary}
                >
                  <FileText />
                  View call summary
                </Button>
              ) : (
                <p className="py-2 text-center text-sm text-muted-foreground">
                  A summary isn't available for this call.
                </p>
              )}
              <Button
                className="h-[48px] w-full rounded-full text-base"
                variant="outline"
                onClick={startAnother}
              >
                <RotateCcw />
                Start another call
              </Button>
            </div>
          ) : (
            <>
              <Button
                size="icon"
                className="size-[76px] rounded-full shadow-sm"
                variant={callActive ? "destructive" : "default"}
                onClick={runCall}
                aria-label={callActive ? "End call" : "Start a call"}
              >
                {callActive ? <PhoneOff /> : <Phone />}
              </Button>
              <span className="text-sm font-medium text-foreground">
                {callActive ? "End call" : "Start a call"}
              </span>
            </>
          )}
        </div>
        <p className="mt-6 max-w-[320px] text-center text-sm leading-relaxed text-muted-foreground">
          You’re talking to an AI care agent. Your live transcript appears
          alongside.
        </p>
        {debug && import.meta.env.DEV && ScenarioPicker && (
          <ScenarioPicker
            scenario={scenario}
            runReplay={runReplay}
            runScenario={runScenario}
          />
        )}
        {debug && import.meta.env.DEV && (
          <Button
            variant="outline"
            className="mt-2 w-full"
            onClick={playTestTone}
          >
            Play test tone
          </Button>
        )}
      </div>
    </section>
  );
}
