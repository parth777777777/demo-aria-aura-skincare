import { FileText, Phone, PhoneOff, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { VoiceOrb } from "./VoiceOrb.jsx";

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
      className="flex min-h-0 flex-col overflow-hidden rounded-3xl border border-border bg-card shadow-sm lg:min-h-[730px]"
      aria-labelledby="call-title"
    >
      <div className="relative h-[155px] overflow-hidden bg-gradient-to-br from-[#dce5d6] via-[#9daf99] to-[#758b76] sm:h-[190px] lg:h-[206px]">
        <img
          src="/src/assets/companion.webp"
          alt=""
          className="absolute size-full object-cover"
          onError={(event) => {
            event.currentTarget.style.display = "none";
          }}
        />
        <span className="absolute bottom-[18px] left-6 font-heading text-lg italic text-[#263b2e]">
          A little care goes a long way
        </span>
      </div>
      <div className="w-full p-5 sm:p-8 lg:px-[34px] lg:py-[27px]">
        <h1
          id="call-title"
          className="my-3 font-heading text-[39px] font-medium leading-tight tracking-[-.045em] sm:text-5xl"
        >
          Ask Aria about
          <br />
          your order.
        </h1>
        <div className="my-4 flex items-center gap-3.5">
          <VoiceOrb state={voiceState} />
          <div className="flex flex-col gap-1">
            <strong className="text-base" aria-live="polite">
              {labels[voiceState]}
            </strong>
            <span className="text-sm tabular-nums text-muted-foreground">
              {state.status.state === "live" ? time : " "}
            </span>
          </div>
        </div>
        {state.status.state === "ended" ? (
          <div className="grid gap-2">
            {state.status.reason === "error" ? null : state.summary ? (
              <Button
                className="h-[52px] w-full rounded-full text-base"
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
              className="h-[52px] w-full rounded-full text-base"
              variant="outline"
              onClick={startAnother}
            >
              <RotateCcw />
              Start another call
            </Button>
          </div>
        ) : (
          <Button
            className="h-[52px] w-full rounded-full text-base"
            variant={callActive ? "destructive" : "default"}
            onClick={runCall}
          >
            {callActive ? (
              <>
                <PhoneOff /> End call
              </>
            ) : (
              <>
                <Phone /> Start a call
              </>
            )}
          </Button>
        )}
        <p className="mt-3 text-center text-sm text-muted-foreground">
          You're talking to an AI care agent
        </p>
        {import.meta.env.DEV && ScenarioPicker && (
          <ScenarioPicker
            scenario={scenario}
            runReplay={runReplay}
            runScenario={runScenario}
          />
        )}
        {import.meta.env.DEV && (
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
