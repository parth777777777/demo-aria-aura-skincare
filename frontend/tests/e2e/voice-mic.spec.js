import { test } from "@playwright/test";
import { chromium } from "playwright";

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

test("streams fake microphone audio and records call diagnostics", async () => {
  const wav = process.env.AURA_FAKE_MIC_WAV;
  if (!wav) throw new Error("Set AURA_FAKE_MIC_WAV to an absolute WAV path");

  const browser = await chromium.launch({
    headless: true,
    args: [
      "--use-fake-ui-for-media-stream",
      "--use-fake-device-for-media-stream",
      `--use-file-for-fake-audio-capture=${wav}%noloop`,
    ],
  });
  const context = await browser.newContext();
  const page = await context.newPage();
  const consoleMessages = [];
  const pageErrors = [];
  const socketDiagnostics = [];
  page.on("console", (message) =>
    consoleMessages.push(`${message.type()}: ${message.text()}`),
  );
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("websocket", (socket) => {
    const record = {
      url: socket.url(),
      sentBinary: 0,
      receivedBinary: 0,
      receivedTypes: [],
    };
    socket.on("framesent", ({ payload }) => {
      if (typeof payload !== "string") record.sentBinary += 1;
    });
    socket.on("framereceived", ({ payload }) => {
      if (typeof payload !== "string") {
        record.receivedBinary += 1;
        return;
      }
      try {
        record.receivedTypes.push(JSON.parse(payload).type ?? "<no type>");
      } catch {
        record.receivedTypes.push("<non-json text>");
      }
    });
    socketDiagnostics.push(record);
  });

  const series = [];
  let finalPanel = "";
  let summaryAppeared = false;
  try {
    await page.goto("http://127.0.0.1:5173/?debug=1");
    await page.getByRole("button", { name: /start a call/i }).click();
    await page
      .getByRole("region", { name: "Your conversation" })
      .getByText("Listening", { exact: true })
      .waitFor({ timeout: 30_000 });

    for (let second = 1; second <= 25; second += 1) {
      await wait(1000);
      const body = await page.locator("body").innerText();
      const mic = body.match(/Mic sent:\s*(\d+) frames/);
      const forwarded = body.match(/Backend forwarded:\s*(\d+) frames/);
      const provider = body.match(/Gemini activity:\s*(observed|waiting)/);
      const inputTranscripts = body.match(/Input transcripts=(\d+)/);
      const outputTranscripts = body.match(/output transcripts=(\d+)/);
      const audioBytes = body.match(/audio bytes received=(\d+)/);
      const status =
        body.match(
          /(?:Ready when you are|Connecting|Listening|Aria is thinking|Aria is speaking|Call ended|Call error)/g,
        ) ?? [];
      const errorNotice = body.match(
        /(?:GEMINI_[A-Z_]+|BAD_MESSAGE|SESSION_LIMIT|INTERNAL|microphone[^\n]*|Audio[^\n]*)/gi,
      );
      series.push({
        second,
        micFramesSent: Number(mic?.[1] ?? 0),
        backendForwarded: Number(forwarded?.[1] ?? 0),
        providerActivity: provider?.[1] ?? "not sampled",
        transcriptCount:
          Number(inputTranscripts?.[1] ?? 0) +
          Number(outputTranscripts?.[1] ?? 0),
        inputTranscripts: Number(inputTranscripts?.[1] ?? 0),
        audioBytesReceived: Number(audioBytes?.[1] ?? 0),
        errorOrNotice: errorNotice?.[0] ?? null,
        statusText: status.at(-1) ?? "not found",
      });
    }

    await page.getByRole("button", { name: /end call/i }).click();
    await page
      .getByText("Call ended", { exact: true })
      .waitFor({ timeout: 15_000 });
    finalPanel = await page.locator("body").innerText();
    summaryAppeared =
      (await page.getByRole("button", { name: /view call summary/i }).count()) >
      0;
  } finally {
    console.log(`TIME_SERIES ${JSON.stringify(series)}`);
    console.log(`WEBSOCKET_DIAGNOSTICS ${JSON.stringify(socketDiagnostics)}`);
    console.log(`CONSOLE_MESSAGES ${JSON.stringify(consoleMessages)}`);
    console.log(`PAGE_ERRORS ${JSON.stringify(pageErrors)}`);
    console.log(`FINAL_PANEL ${JSON.stringify(finalPanel)}`);
    console.log(`SUMMARY_PAGE_APPEARED ${summaryAppeared}`);

    const sent = series.map((sample) => sample.micFramesSent);
    const increasingForDuration =
      sent.length === 25 &&
      sent.every((value, index) => index === 0 || value > sent[index - 1]);
    const userTranscript = series.some((sample) => sample.inputTranscripts > 0);
    const ariaAudio = socketDiagnostics.some(
      (record) => record.receivedBinary > 0,
    );
    const noErrorNotice = series.every(
      (sample) => sample.errorOrNotice == null,
    );
    console.log(
      `CRITERIA mic_increases_for_all_25s=${increasingForDuration} user_transcript=${userTranscript} aria_audio_bytes=${ariaAudio} no_error_notice=${noErrorNotice}`,
    );
    console.log(
      `FAILED_CRITERIA ${JSON.stringify([
        ...(!increasingForDuration
          ? ["mic counter did not increase for the full 25 seconds"]
          : []),
        ...(!userTranscript ? ["no user transcript appeared"] : []),
        ...(!ariaAudio ? ["no Aria audio bytes arrived"] : []),
        ...(!noErrorNotice ? ["an error notice appeared"] : []),
      ])}`,
    );
    await context.close();
    await browser.close();
  }
});
