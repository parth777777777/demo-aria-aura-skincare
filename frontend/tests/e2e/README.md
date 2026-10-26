# Real voice browser smoke test

This deliberately opens one real Gemini Live session and consumes API quota.
Use only when a short real integration check is approved; stop after the first
failed run rather than retrying or changing app code to chase the result.

From `frontend/`, start the backend on port 8001 with
`ALLOWED_WS_ORIGINS=http://127.0.0.1:5173`, then start Vite with
`VITE_WS_URL=ws://127.0.0.1:8001/ws/call npm run dev -- --host 127.0.0.1 --port 5173 --strictPort`.
In another terminal run:

```sh
AURA_FAKE_MIC_WAV=/absolute/path/to/backend/tests/fixtures/order_check_ord101.wav npm run test:e2e:voice
```

Playwright launches its installed Chromium with the fake-media flags and a
`%noloop` WAV source. The test prints a 25-second debug-panel time series,
independent WebSocket frame/event counts, browser console/page errors, final
call panel, and each pass/fail criterion. This is not part of `npm test` or the
production build.
