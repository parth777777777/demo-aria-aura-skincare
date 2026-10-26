import { useState } from "react";
import { ArrowLeft, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";

function apiBaseUrl() {
  if (import.meta.env.VITE_API_BASE_URL)
    return import.meta.env.VITE_API_BASE_URL.replace(/\/$/, "");
  const socketUrl = import.meta.env.VITE_WS_URL;
  if (socketUrl)
    return socketUrl
      .replace(/^ws:/, "http:")
      .replace(/^wss:/, "https:")
      .replace(/\/ws\/call\/?$/, "");
  return window.location.origin;
}

export function DemoAccountPage({ onCreated, onBack }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    const displayName = name.trim();
    if (!displayName || displayName.length > 80) {
      setError("Enter a name between 1 and 80 characters.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`${apiBaseUrl()}/api/demo-sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: displayName }),
      });
      if (!response.ok) {
        setError(
          response.status === 422
            ? "Please enter a valid display name."
            : "We couldn't create your demo account. Please try again.",
        );
        return;
      }
      const identity = await response.json();
      if (
        typeof identity.credential !== "string" ||
        typeof identity.display_name !== "string"
      ) {
        setError("We couldn't create your demo account. Please try again.");
        return;
      }
      try {
        sessionStorage.setItem(
          "aura.demoIdentity.credential",
          identity.credential,
        );
        sessionStorage.setItem(
          "aura.demoIdentity.displayName",
          identity.display_name,
        );
      } catch {
        setError(
          "This browser can't securely keep a demo identity for this tab.",
        );
        return;
      }
      onCreated(identity.display_name);
    } catch {
      setError("We couldn't reach Aura. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      className="mx-auto grid min-h-[70vh] max-w-2xl content-center gap-8 py-12"
      aria-labelledby="demo-title"
    >
      <Button variant="ghost" className="w-fit rounded-full" onClick={onBack}>
        <ArrowLeft /> Back to Mock DB
      </Button>
      <div className="rounded-3xl border border-border bg-card p-7 shadow-sm sm:p-10">
        <span className="mb-6 grid size-12 place-items-center rounded-full bg-primary text-primary-foreground">
          <Sparkles />
        </span>
        <p className="text-sm font-medium uppercase tracking-[.18em] text-muted-foreground">
          AURA SKINCARE · DEMO
        </p>
        <h1
          id="demo-title"
          className="mt-3 font-heading text-4xl tracking-tight sm:text-5xl"
        >
          Create a demo account
        </h1>
        <p className="mt-4 leading-7 text-muted-foreground">
          Choose a display name to try the temporary demo identity experience.
          No password or real account is needed.
        </p>
        <form onSubmit={submit} className="mt-8 grid gap-4">
          <label htmlFor="demo-name" className="text-sm font-medium">
            Display name
          </label>
          <input
            id="demo-name"
            name="name"
            autoComplete="name"
            maxLength={80}
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="h-12 rounded-xl border border-input bg-background px-4 outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-describedby={error ? "demo-error" : undefined}
          />
          {error && (
            <p
              id="demo-error"
              role="alert"
              className="text-sm text-destructive"
            >
              {error}
            </p>
          )}
          <Button
            type="submit"
            disabled={busy}
            className="mt-2 h-12 rounded-full"
          >
            {busy ? "Creating…" : "Create demo account"}
          </Button>
        </form>
        <p className="mt-5 text-xs leading-5 text-muted-foreground">
          This is a temporary demo identity, not a real account. It remains
          available in this browser tab until you reset it or close the tab.
        </p>
      </div>
    </section>
  );
}
