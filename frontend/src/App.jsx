import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { callReducer, initialCallState } from "./state/callReducer.js";
import { selectVoiceState } from "./state/selectors.js";
import { useMockReplay } from "./hooks/useMockReplay.js";
import { useCallSocket } from "./hooks/useCallSocket.js";
import { useHashRoute } from "./hooks/useHashRoute.js";
import { getVisibleNotice } from "./lib/display.js";
import { SummaryPage } from "./components/SummaryPage.jsx";
import { CallPanel } from "./components/CallPanel.jsx";
import { ConversationPanel } from "./components/ConversationPanel.jsx";
import { DemoAccountPage } from "./components/DemoAccountPage.jsx";
import { Button } from "@/components/ui/button";

const summaryKeys = [
  "customer_intent",
  "order_id",
  "resolution_status",
  "call_summary",
];

function getStoredDemoIdentity() {
  try {
    const credential = sessionStorage.getItem("aura.demoIdentity.credential");
    const displayName = sessionStorage.getItem("aura.demoIdentity.displayName");
    return credential && displayName ? { credential, displayName } : null;
  } catch {
    return null;
  }
}

function App() {
  const [state, dispatch] = useReducer(callReducer, initialCallState);
  const [elapsed, setElapsed] = useState(0);
  const [route, setRoute] = useHashRoute();
  const [demoName, setDemoName] = useState(() => {
    return getStoredDemoIdentity()?.displayName || "";
  });
  const [mockData, setMockData] = useState(null);
  const [copied, setCopied] = useState(false);
  const copyTimer = useRef(null);
  const voiceState = selectVoiceState(state);
  const {
    start: startCall,
    end: endCall,
    playTestTone,
    stats: micStats,
  } = useCallSocket(
    (event) => {
      if (event?.type === "error" && event.code === "ACCOUNT_SESSION_INVALID") {
        try {
          sessionStorage.removeItem("aura.demoIdentity.credential");
          sessionStorage.removeItem("aura.demoIdentity.displayName");
        } catch {
          // Storage may be unavailable; the current UI still offers re-creation.
        }
        setDemoName("");
      }
      dispatch(event);
    },
    () => {
      const identity = getStoredDemoIdentity();
      return identity
        ? {
            type: "start_call",
            mode: "account",
            credential: identity.credential,
          }
        : { type: "start_call" };
    },
  );
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
    <main className="min-h-screen bg-[#f7f6f0] px-3 py-3 sm:px-6 sm:py-6 2xl:px-16 2xl:py-[30px]">
      <div className="mx-auto flex min-h-[calc(100svh-24px)] w-full max-w-[1792px] flex-col overflow-hidden rounded-[28px] border border-border bg-[#fffefa] shadow-[0_12px_50px_rgba(32,45,39,0.06)] sm:min-h-[calc(100svh-48px)] sm:rounded-[36px] lg:h-[calc(100svh-48px)] lg:min-h-[730px] 2xl:h-[calc(100svh-60px)] 2xl:min-h-[730px]">
        <header className="flex min-h-[72px] items-center justify-between gap-4 border-b border-border px-5 sm:min-h-[82px] sm:px-9">
          <a
            href="#/"
            onClick={() => setRoute("call")}
            className="flex min-w-0 items-center gap-3 text-foreground"
          >
            <span className="font-heading text-[30px] font-semibold tracking-[-.04em]">
              aura
            </span>
            <span className="hidden text-sm text-muted-foreground sm:block">
              Personal care, personally.
            </span>
          </a>
          <Button
            variant="ghost"
            className="shrink-0 rounded-full text-sm font-medium"
            onClick={() => {
              if (route !== "call") {
                window.location.hash = "#/";
                setRoute("call");
              } else if (demoName) {
                try {
                  sessionStorage.removeItem("aura.demoIdentity.credential");
                  sessionStorage.removeItem("aura.demoIdentity.displayName");
                } catch {
                  /* unavailable storage */
                }
                setDemoName("");
              } else {
                window.location.hash = "#/demo-account";
                setRoute("demo-account");
              }
            }}
          >
            {route === "call" ? (
              demoName ? (
                <>Demo identity: {demoName} · Reset</>
              ) : (
                "Create demo account"
              )
            ) : (
              <>
                <ArrowLeft data-icon="inline-start" /> Back to conversation
              </>
            )}
          </Button>
        </header>
        {route === "demo-account" ? (
          <div className="flex-1 p-4 sm:p-8">
            <DemoAccountPage
              onCreated={(name) => {
                setDemoName(name);
                window.location.hash = "#/";
                setRoute("call");
              }}
              onBack={() => {
                window.location.hash = "#/";
                setRoute("call");
              }}
            />
          </div>
        ) : route === "summary" ? (
          <div className="flex-1 p-4 sm:p-8">
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
          </div>
        ) : (
          <div className="grid min-h-0 flex-1 items-stretch lg:grid-cols-[minmax(350px,.95fr)_minmax(0,1.8fr)] lg:grid-rows-[minmax(0,1fr)]">
            <CallPanel
              state={state}
              voiceState={voiceState}
              time={time}
              callActive={callActive}
              debug={debug}
              runReplay={runReplay}
              runCall={() => {
                if (callActive) endCall();
                else {
                  if (demoName && !getStoredDemoIdentity()) {
                    window.location.hash = "#/demo-account";
                    setRoute("demo-account");
                    return;
                  }
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
              debug={debug}
              micStats={micStats}
              audioForwarded={state.audioForwarded}
              providerActivity={state.providerActivity}
              isAccountMode={Boolean(demoName)}
            />
          </div>
        )}
      </div>
    </main>
  );
}
export default App;
