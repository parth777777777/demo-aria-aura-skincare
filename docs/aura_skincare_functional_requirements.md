# Aura Skincare AI Voice Agent — Functional Requirements

## 1. Project overview

Build a browser-based AI voice customer-support agent for Aura Skincare, a fictional premium organic Indian skincare brand. The agent, **Aria**, should converse naturally with customers, answer brand and policy questions, look up mock order information, enforce business rules, and produce a transcript and structured post-call summary.

### Chosen technology stack

- **Frontend:** React + Vite + JavaScript
- **Backend:** Python + FastAPI
- **Voice AI:** Gemini Live API
- **Communication:** Browser ↔ FastAPI over WebSocket ↔ Gemini Live
- **Database:** MongoDb for NoSQL mock order records (or in-memory Python dictionaries for simplicity) 
- **Data:** Mock order records in Python dictionaries or JSON
- **Testing:** `pytest` for backend tests, plus browser-based end-to-end testing
- **Deployment:** Vercel for frontend and Render (or equivalent) for backend

> The exact Gemini Live model, SDK, connection mechanism, quotas, and credential flow must be verified against the current documentation and the Google project being used before implementation.

## 2. P0 — Core functional requirements

These requirements must work for the application to be considered complete.

| ID | Requirement | Description |
|---|---|---|
| FR-01 | Start a voice call | The customer can start a browser-based voice session using a visible **Start Call** button. |
| FR-02 | Microphone and speaker | Request microphone permission, capture customer speech, and play the agent's spoken responses. |
| FR-03 | Real-time conversation | Maintain conversational context, respond naturally and concisely, and avoid unnecessary repetition. |
| FR-04 | Live agent state | Display Listening, Thinking, and Speaking states, with feedback when connecting or encountering an error. |
| FR-05 | Brand knowledge | Answer questions using Aura Skincare's supplied brand information and policies. |
| FR-06 | Order lookup tool | Gemini can request `get_order_details(order_id)`; Python executes the function and returns the actual record. |
| FR-07 | Policy enforcement | Check order status and policy conditions before explaining whether a requested action is eligible. |
| FR-08 | Graceful error handling | Handle unknown orders, missing IDs, unclear speech, API failures, and unsupported questions without inventing facts or crashing. |
| FR-09 | End call | Provide an **End Call** button that closes the session and finalizes available conversation data. |
| FR-10 | Post-call transcript | Display a chronological transcript of customer and agent turns after the call. |
| FR-11 | Structured call summary | Generate and display JSON containing `customer_intent`, `order_id`, `resolution_status`, and `call_summary`. |
| FR-12 | Test order helper | Show `ORD-101`, `ORD-102`, and `ORD-103`, with sample details, directly in the interface. |
| FR-13 | Public deployment | Provide an accessible application URL that evaluators can open and test without running the development environment. |

## 3. P1 — Business logic and brand policies

Implement policy rules in Python so the model cannot unilaterally override them.

| Rule | Requirement |
|---|---|
| Shipping fee | Free delivery only on orders strictly above ₹499; orders at or below ₹499 have a ₹50 shipping fee. Exactly ₹499 pays ₹50. |
| Standard delivery | Explain that standard delivery takes 3–5 business days. |
| Returns | Accept returns within 7 days of delivery only for unopened, unused products in original packaging. |
| Damaged products | The issue must be reported within 48 hours of delivery, with photos, for replacement. |
| Cancellation | Cancellation is allowed only while order status is `Processing`. |
| Shipped orders | Shipped or out-for-delivery orders cannot be cancelled; customers may refuse delivery at the doorstep. |
| Cash on delivery | COD is available for orders up to ₹2,500; payment may be made by cash or UPI at the doorstep. |
| Unknown information | Acknowledge uncertainty and ask for clarification rather than fabricating a policy or order status. |
| Out-of-scope requests | Politely decline unrelated tasks, such as booking flights. |

### Mock order database

The backend must include these sample records from the assessment.

| Order ID | Customer | Product | Value | Status | Notes |
|---|---|---|---:|---|---|
| `ORD-101` | Priya Sharma | Vitamin C Serum (30ml) | ₹699 | Out for Delivery | BlueDart — `BD-982103`; expected by 6 PM today |
| `ORD-102` | Rahul Verma | Hydrating Sunscreen SPF 50 | ₹499 | Delivered | Delhivery — `DL-441029`; delivered 14 days ago |
| `ORD-103` | Ananya Patel | Green Tea Face Wash + Toner | ₹850 | Processing | Ordered 3 hours ago; eligible for cancellation |

### Policy and edge-case requirements

- A delivered order is not automatically eligible for return.
- A customer asking to cancel an order does not mean the cancellation succeeded.
- If an order ID is missing, ask the customer for it before performing a lookup.
- If eligibility depends on information that is unavailable, explain what is missing rather than guessing.
- The app only needs to check eligibility; actual refund, cancellation, and replacement transactions are out of scope unless deliberately added later.

## 4. P1 — Voice session and tool-calling requirements

| ID | Requirement | Description |
|---|---|---|
| FR-14 | Session lifecycle | FastAPI establishes and maintains the Gemini Live session. The browser can start and end calls, and the application cleans up sessions when calls terminate. |
| FR-15 | Tool-call dispatch | Identify the requested function, validate its arguments, execute only registered tools, and return the result to Gemini using the correct function-call identifier. |
| FR-16 | Server-side policy validation | Eligibility decisions are made by deterministic Python functions. The model cannot override a denied result by generating a more agreeable response. |
| FR-17 | Transcript collection | Collect supported input and output transcription events, preserve speaker attribution and order, and handle partial or unfinished turns when a call ends. |
| FR-18 | Summary generation | Generate structured output from the completed transcript and available tool results. Validate the schema before displaying it. |

### Example tool flow

1. Customer asks: “Where is my order ORD-101?”
2. Gemini identifies the need for order information and requests `get_order_details(order_id="ORD-101")`.
3. The application validates the tool call and executes the Python function.
4. The backend returns the actual order details or a not-found result.
5. The tool response is sent back to the Live session.
6. Gemini speaks a concise answer based on the returned data.

**Important:** Gemini requests a tool call; the application executes the code. The model does not directly access the Python runtime or database.

## 5. P2 — Quality improvements

Implement after the core workflow is reliable.

- Natural Hinglish and Indian English support.
- Interruptible agent speech, where supported.
- Clear messages for connection failures, denied microphone permissions, and API quota errors.
- A visible indicator while the post-call summary is being generated.
- Recovery or a clear failure state when the network disconnects.
- A responsive interface suitable for a laptop browser.
- A repeatable manual test script covering success and failure scenarios.

These are quality improvements; Hinglish, interruption handling, ambiguity handling, and very low latency are optional enhancements in the assessment.

## 6. Non-functional requirements

| Area | Requirement |
|---|---|
| Security | Never expose a permanent Gemini API key in browser code. |
| Validation | Validate order IDs, tool arguments, and summary structure. |
| Reliability | Handle provider failures, invalid tool responses, and session termination without crashing. |
| Maintainability | Separate API routes, services, policy rules, and mock data. |
| Testing | Unit-test policy decisions and order lookup; manually test the end-to-end voice flow. |
| Configuration | Provide `.env.example` without real credentials. |
| Documentation | Include setup instructions, architecture, trade-offs, and answers to all four assessment questions. |
| Submission | Provide public application URL, GitHub repository, demo video, LinkedIn profile, and a short approach note. |

## 7. Acceptance criteria

Before submission, verify each scenario.

- [ ] **Voice:** Start a call, ask a question aloud, hear a relevant spoken answer, and end the call.
- [ ] **Order tracking:** Ask for `ORD-101` and hear the correct courier, tracking ID, and expected delivery.
- [ ] **Invalid order:** Ask for an unknown order and receive a clarification or not-found response, not fabricated details.
- [ ] **Cancellation allowed:** Ask to cancel `ORD-103` and receive an eligibility-consistent response.
- [ ] **Cancellation denied:** Ask to cancel `ORD-101` and be told that the order is already out for delivery.
- [ ] **Return policy:** Ask about returning `ORD-102` after 14 days and receive a response consistent with the seven-day policy.
- [ ] **Out of scope:** Ask the agent to book a flight and receive a polite refusal.
- [ ] **Transcript:** End a conversation and see the chronological transcript.
- [ ] **Summary:** See valid structured JSON with the required fields and a sensible resolution status.
- [ ] **Deployment:** Open the deployed URL in a fresh browser session and successfully test the application.

## 8. Deliberately out of scope

To protect the four-day deadline, the initial version will not include:

- A real order-management system or payment gateway.
- Actual refunds, cancellations, or replacement transactions.
- Customer accounts, login, or order ownership verification.
- A production database.
- Telephony or phone-number integration.
- Multi-brand support.
- An analytics dashboard or production-scale call-management platform.

The assessment requires a browser-based experience and mock order database, so these features are not necessary for the initial submission.

## 9. Delivery plan

### Day 1 — Foundation
- Scaffold frontend and backend.
- Verify the selected Gemini Live model, SDK, credentials, quota, and connection pattern.
- Establish a working audio session and confirm spoken conversation.

### Day 2 — Agent intelligence
- Implement order lookup and function calling.
- Add deterministic policy checks.
- Handle invalid IDs, missing information, and out-of-scope questions.

### Day 3 — Interface and summaries
- Add call controls and live states.
- Display the sample order helper and transcript.
- Generate and validate the structured post-call summary.
- Run acceptance tests.

### Day 4 — Submission
- Deploy the frontend and backend.
- Test the public URL and production configuration.
- Fix critical issues.
- Complete the README and architecture explanation.
- Record the 3–5 minute demo video and prepare the submission email.

## 10. Submission deliverables

- Public application URL.
- GitHub repository with source code, README, architecture/approach, setup instructions, and `.env.example`.
- 3–5 minute demo video showing a voice conversation, an order lookup, a policy-related conversation, the transcript and summary, and a brief architecture walkthrough.
- Short approach note of 2–3 sentences.
- Accessible LinkedIn profile link.

### README questions to answer

1. Why did you choose this architecture and technology stack?
2. What was the most difficult part of the assignment, and how did you solve it?
3. If you had one more week, what would you improve first and why?
4. What would need to change if the agent handled 1,000 customer conversations per day?

## 11. Implementation principle

**The model handles conversation; Python handles facts and policy decisions.**

Cancellation in this milestone is deliberately implemented as an in-memory,
per-session mock state change only. It does not contact a real order system or
perform a real cancellation transaction.

Prioritize a complete, reliable core workflow over extra features. Verify the selected Gemini Live API capabilities and account limits before committing to implementation details, and test the public deployment rather than assuming local success guarantees production success.
