import { Button } from "@/components/ui/button";

export default function ScenarioPicker({ scenario, runReplay, runScenario }) {
  return (
    <div className="mt-4 flex flex-col items-center gap-2">
      <Button size="sm" variant="outline" onClick={runReplay}>
        Run mock replay
      </Button>
      <label className="flex items-center gap-2 text-sm text-muted-foreground">
        Scenario
        <select
          className="h-9 rounded-md border border-border bg-background px-2 text-foreground"
          value={scenario}
          onChange={(event) => runScenario(event.target.value)}
          aria-label="Run mock scenario"
        >
          <option value="" disabled>
            Choose a scenario
          </option>
          <option value="cancel">Cancel flow (ORD-103)</option>
          <option value="lookup">Lookup flow (ORD-101)</option>
          <option value="session_limit">Session limit with summary</option>
          <option value="session_limit_without_summary">
            Session limit without summary
          </option>
          <option value="fatal_error">Fatal error</option>
          <option value="recoverable_error">Recoverable error mid-call</option>
          <option value="user_ended_no_summary">User ended, no summary</option>
        </select>
      </label>
    </div>
  );
}
