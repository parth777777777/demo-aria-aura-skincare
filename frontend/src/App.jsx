import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import { Sparkles } from "lucide-react";
import { callReducer, initialCallState } from "./state/callReducer.js";
import { selectVoiceState } from "./state/selectors.js";
import { useMockReplay } from "./hooks/useMockReplay.js";
import { useCallSocket } from "./hooks/useCallSocket.js";
import { useHashRoute } from "./hooks/useHashRoute.js";
import { getVisibleNotice } from "./lib/display.js";
import { SummaryPage } from "./components/SummaryPage.jsx";
import { CallPanel } from "./components/CallPanel.jsx";
import { ConversationPanel } from "./components/ConversationPanel.jsx";

const summaryKeys = [
  "customer_intent",
  "order_id",
  "resolution_status",
  "call_summary",
];

function App() {
  const [state, dispatch] = useReducer(callReducer, initialCallState);
  const [elapsed, setElapsed] = useState(0);
  const [route, setRoute] = useHashRoute();
  const [mockData, setMockData] = useState(null);
  const [copied, setCopied] = useState(false);
  const copyTimer = useRef(null);
  const transcriptRef = useRef(null);
  const voiceState = selectVoiceState(state);
  const {
    start: startCall,
    end: endCall,
    playTestTone,
    stats: micStats,
  } = useCallSocket(dispatch);
  const replayEvents = useMemo(() => mockData?.lookup || [], [mockData]);
  const { startMockReplay, stopMockReplay } = useMockReplay(
    dispatch,
    replayEvents,
    800,
  );
  const [scenario, setScenario] = useState("");
  const [ScenarioPicker, setScenarioPicker] = useState(null);
  const scenarioEvents = useMemo(
    () => (scenario && mockData ? mockData[scenario] : []),
    [scenario, mockData],
  );
  const {
    startMockReplay: startScenarioReplay,
    stopMockReplay: stopScenarioReplay,
  } = useMockReplay(dispatch, scenarioEvents, 800);
  const callActive = ["connecting", "live", "ending"].includes(
    state.status.state,
  );
  const debug =
    new URLSearchParams(window.location.search).get("debug") === "1";

  useEffect(() => {
    if (import.meta.env.DEV) {
      import("./mocks/call-events.json").then((module) =>
        setMockData(module.default),
      );
      import("./components/ScenarioPicker.jsx").then((module) =>
        setScenarioPicker(() => module.default),
      );
    }
  }, []);
  useEffect(() => () => window.clearTimeout(copyTimer.current), []);
  useEffect(() => {
    if (state.status.state !== "live") return undefined;
    const timer = setInterval(() => setElapsed((value) => value + 1), 1000);
    return () => clearInterval(timer);
  }, [state.status.state]);
  useEffect(() => {
    if (scenario) startScenarioReplay();
  }, [scenario, startScenarioReplay]);
  useEffect(() => {
    const viewport = transcriptRef.current?.querySelector(
      '[data-slot="scroll-area-viewport"]',
    );
    if (
      viewport &&
      viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight < 120
    )
      viewport.scrollTo({
        top: viewport.scrollHeight,
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "auto"
          : "smooth",
      });
  }, [state.turns, state.tools]);

  const runReplay = () => {
    if (callActive) return;
    stopMockReplay();
    stopScenarioReplay();
    dispatch({ type: "call_requested" });
    setElapsed(0);
    startMockReplay();
  };
  const runScenario = (key) => {
    if (callActive) return;
    setScenario(key);
    stopMockReplay();
    stopScenarioReplay();
    dispatch({ type: "reset" });
    dispatch({ type: "call_requested" });
    setElapsed(0);
  };
  const startAnother = () => {
    stopMockReplay();
    stopScenarioReplay();
    dispatch({ type: "reset" });
    setElapsed(0);
    window.location.hash = "#/";
    setRoute("call");
  };
  const navigateSummary = () => {
    window.location.hash = "#/summary";
    setRoute("summary");
  };
  const time = `${String(Math.floor(elapsed / 60)).padStart(2, "0")}:${String(elapsed % 60).padStart(2, "0")}`;
  const summary =
    state.summary &&
    Object.fromEntries(summaryKeys.map((key) => [key, state.summary[key]]));
  const { errorMessage, sessionLimit } = getVisibleNotice({
    error: state.error,
    status: state.status,
    turnCount: state.turns.length,
  });
  const copySummary = async () => {
    await navigator.clipboard.writeText(JSON.stringify(summary, null, 2));
    setCopied(true);
    window.clearTimeout(copyTimer.current);
    copyTimer.current = window.setTimeout(() => setCopied(false), 2000);
  };

  return (
    <main className="mx-auto w-full max-w-[1440px] px-[13px] sm:px-[22px] lg:px-[42px]">
      <header className="flex h-[66px] items-center justify-between border-b border-border sm:h-[82px]">
        <a
          href="#/"
          onClick={() => setRoute("call")}
          className="flex items-center gap-3 font-sans text-sm font-bold tracking-[.16em] text-primary"
        >
          <span className="grid size-[34px] place-items-center rounded-full bg-primary text-primary-foreground">
            <Sparkles size={17} />
          </span>
          <span className="leading-[1.05]">
            AURA
            <small className="mt-[2px] block text-[13px] leading-[1.05] tracking-[.24em]">
              SKINCARE
            </small>
          </span>
        </a>
      </header>
      {route === "summary" ? (
        <SummaryPage
          summary={summary}
          copied={copied}
          copySummary={copySummary}
          startAnother={startAnother}
          backToCall={() => {
            window.location.hash = "#/";
            setRoute("call");
          }}
        />
      ) : (
        <div className="grid items-stretch gap-4 py-4 lg:grid-cols-[minmax(360px,.82fr)_minmax(0,1.18fr)] lg:gap-7 lg:py-[30px]">
          <CallPanel
            state={state}
            voiceState={voiceState}
            time={time}
            callActive={callActive}
            runReplay={runReplay}
            runCall={() => {
              if (callActive) endCall();
              else {
                stopMockReplay();
                stopScenarioReplay();
                dispatch({ type: "call_requested" });
                setElapsed(0);
                startCall();
              }
            }}
            navigateSummary={navigateSummary}
            startAnother={startAnother}
            scenario={scenario}
            ScenarioPicker={ScenarioPicker}
            runScenario={runScenario}
            playTestTone={playTestTone}
          />
          <ConversationPanel
            state={state}
            voiceState={voiceState}
            errorMessage={errorMessage}
            sessionLimit={sessionLimit}
            transcriptRef={transcriptRef}
            debug={debug}
            micStats={micStats}
            audioForwarded={state.audioForwarded}
            providerActivity={state.providerActivity}
          />
        </div>
      )}
    </main>
  );
}
export default App;
