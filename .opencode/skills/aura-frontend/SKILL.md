---
name: aura-frontend
description: Build Aura's React/Vite JavaScript UI using React Bits, shadcn/ui, Tailwind CSS, and Lucide, while keeping voice behaviour modular, accessible, and testable.
---

# Aura Frontend

Use for frontend work across the Aura app. Read root `AGENTS.md` and relevant existing `docs/` first. Inspect the actual repository, installed dependencies, and Git status before changing files. Do not overwrite user work.

## Stack and boundaries

- Use React + Vite + plain JavaScript (`.js` / `.jsx`); do not introduce TypeScript.
- Use Tailwind CSS for layout, responsive styling, and shared design tokens.
- Use shadcn/ui for accessible standard UI primitives where appropriate.
- Use React Bits selectively for distinctive motion or interactive visuals.
- Use `lucide-react` for icons.
- Use Oxlint for linting. Do not add ESLint unless explicitly requested.
- Keep Gemini credentials out of browser code. Frontend communicates with the FastAPI backend, never with Gemini using a permanent secret key.
- Do not add another component library or state-management package without a concrete need.

## Choose and integrate components

- Before using a third-party component, check its current official docs, source, licence, peer dependencies, props, accessibility, and installation instructions.
- Prefer JavaScript + CSS variants of React Bits. Do not copy TypeScript-only examples without adapting them correctly to JavaScript.
- Install only the specific component and dependencies required. Avoid dumping many components into the repository or adding multiple libraries that solve the same problem.
- Treat installed/copied components as project code: keep their responsibilities clear and customize them to the design system.
- Do not assume a React Bits component is accessible, responsive, or performant without inspecting it.
- Avoid paid/pro-only components and assets unless explicitly approved.

## Visual system

- Create a cohesive premium skincare identity, not a generic dashboard or a component-demo collage.
- Use shared design tokens for colour, typography, spacing, radii, borders, and motion.
- Keep the voice interaction primary; transcript, order lookup, and call summary support it.
- Use animation sparingly and purposefully. Tie Listening, Thinking, Speaking, connecting, and disconnected visuals to actual app state; never fake a successful connection or tool action.
- Respect `prefers-reduced-motion`, provide fallbacks for heavy/WebGL effects, and avoid effects that harm readability, battery, or responsiveness.
- Keep responsive behaviour, contrast, keyboard operation, semantic labels, visible focus, and useful loading/error/empty states.

## Modularity

Keep these concerns separate:
- UI components: rendering and local presentation.
- Hooks: React lifecycle and feature state.
- Services: HTTP/WebSocket transport and message parsing.
- Domain data and action results: obtained from the backend, not duplicated as frontend business rules.

Prefer feature-based components with clear props over giant page components. Don't create empty abstractions pre-emptively; introduce modules when implementing real behaviour. Avoid components that both own network transport and render complex UI.

## Voice-specific behaviour

- Request microphone permission only after the user starts a call.
- Follow the actual documented backend WebSocket contract for audio encoding, sample rate, messages, transcription, audio responses, errors, and end-of-call events.
- Do not invent client-side event names or audio formats independently of the backend.
- Handle permission denial, failed connections, reconnect/disconnect, and user hang-up. Clean up streams, audio nodes, sockets, and listeners.
- Prevent duplicate call starts and overlapping audio playback.
- Reflect real events in call-state indicators; don't claim an action succeeded until the backend confirms it.

## Verification

- Run the available Oxlint script, tests, and production build after relevant changes.
- Do not claim checks passed unless they actually ran. Report missing scripts or blockers clearly.
- Do not consume Gemini quota to test purely visual or frontend changes.
- Finish with a concise summary of changed files, checks/results, and known limitations.

## Related skill

For backend behaviour, use `aura-backend`, `gemini-live`, `fastapi-backend`, or `tool-engineering` as relevant. This skill defines how the frontend should use the selected UI tools; it does not replace those tools' official component documentation.
