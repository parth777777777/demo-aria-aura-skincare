import {
  AudioLines,
  Check,
  CircleAlert,
  Leaf,
  LoaderCircle,
  Mic,
} from "lucide-react";

export function VoiceOrb({ state }) {
  const icons = {
    idle: <Leaf />,
    connecting: <LoaderCircle className="orb-spin" />,
    listening: <Mic />,
    thinking: <span aria-hidden="true">•••</span>,
    speaking: <AudioLines />,
    ended: <Check />,
    error: <CircleAlert />,
  };
  return (
    <div
      className={`grid size-[62px] shrink-0 place-items-center rounded-full bg-muted text-primary orb-${state}`}
      aria-hidden="true"
    >
      <div
        className={`grid size-12 place-items-center rounded-full border border-primary ${state === "connecting" ? "border-dotted border-2" : state === "thinking" ? "border-dashed border-2" : ["listening", "speaking"].includes(state) ? "border-2" : ""}`}
      >
        {icons[state]}
      </div>
    </div>
  );
}
