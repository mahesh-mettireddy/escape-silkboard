# escape-silkboard 🛺✈️

An AI-narrated Bengaluru commuter survival text adventure built for the **Futurelab Studios Engineering Challenge**.

It's **7:00 PM** at **Silk Board Junction** (`0.0 km`). Flight `FL 2047` departs Kempegowda International Airport (`38.0 km`) at **9:40 PM**, and **check-in closes strictly at 8:55 PM** (`115 minutes`). You have **32% phone battery**, **₹500 in cash** (*UPI works while the phone lives*), and **1 cold samosa**.

---

## Architecture: *"Code Owns the Facts. The LLM Owns the Story."*

```text
Player Natural Input (English / Hinglish / Kannada / Telugu / Tamil)
   │
   ▼
[1. InputGuardrail (Python)] ──► 0-Token block for prompt injections & god-mode cheats
   │
   ▼
[2. NarratorEngine (LangChain + Gemini 2.5 Flash / Flash-Lite)]
   ├─ Pre-detects player language/script so speaker replies in the exact same language
   ├─ Uses "Yes, and..." human persona with multi-turn conversational memory
   └─ Returns Pydantic v2 Structured Output (`TurnProposal`) + live `usage_metadata`
   │
   ▼
[3. OutputGuardrail (Python Deterministic Clamp)]
   ├─ Separates Stationary Haggling/Questions (0.0 km, ₹0) from Travel Moves
   ├─ Enforces 8–12 Turn Pacing (caps travel at 6.0 km/turn in city, 7.5 km/turn past Hebbal)
   ├─ Enforces Monotonic Clock (+2..+20 mins per turn; time never runs backward)
   ├─ Enforces Wallet Solvency (intercepts moves costing more than remaining cash)
   ├─ Enforces 0% Battery Lock (disables UPI, Uber/Ola/Rapido, Maps, and Calls)
   ├─ Enforces Single-Use Inventory (1 cold samosa removed permanently once used)
   └─ Signs verified GameState with HMAC-SHA256 (stateless & DevTools tamper-proof)
```

---

## Signature Feature & UI Highlights

* **Live Route Map (`0.0 km` → `38.0 km`):** Continuous SVG road tracker across Bengaluru checkpoints (*Silk Board → Sony World / ORR → Indiranagar Metro → Mekhri Circle → Hebbal Flyover → Sadahalli Toll → KIA Terminal 1*) that fills smoothly turn-by-turn.
* **True Chat + Two-Part AI Response:** Player messages stay pinned on the right; AI responses on the left spotlight **bold spoken driver dialogue** on top and a **compact scene explanation + delta pills** below.
* **Zero-Scroll `100dvh` Layout:** Clock, Battery, Cash, Bag, and the Live Route Map stay visible at all times across both Desktop (split-screen) and Mobile (sticky top deck) with Dark/Light mode support.
* **Live Token Telemetry (`⚡`) & 2-Way API Key Support:** Displays real `input_tokens`, `output_tokens`, and USD cost from Gemini's `usage_metadata`, and automatically falls back from server `.env` key to browser-supplied key (`🔑 API Key`) with top status alerts on missing key or `429` quota exhaustion.

---

## Model & Token Cost per Playthrough

* **Models:** `gemini-2.5-flash` and `gemini-2.5-flash-lite` via `langchain-google-genai` (`with_structured_output(TurnProposal, include_raw=True)`, `thinking_budget=0`) with automatic failover across models on free-tier rate limits.
* **Actual Token Usage per Turn:** `~310–650 input tokens` + `~75–180 output tokens` = **`~385–800 tokens/turn`**.
* **Total Cost per Full Playthrough (8–12 turns):**
  * Input (`~4,500 tokens` × `$0.15 / 1M`) + Output (`~1,200 tokens` × `$0.60 / 1M`) = **`~$0.0014` (`< ₹0.12 INR`)** per complete game (`$0.00` on Gemini Free Tier).

---

## Project Structure

```text
escape-silkboard/
├── api/
│   └── index.py           # FastAPI entry point (/api/start, /api/turn, /api/health + static UI)
├── engine/
│   ├── state.py           # Deterministic GameState, landmarks (0–38 km), HMAC-SHA256 signing
│   ├── guardrails.py      # TurnProposal schema, 0-token InputGuardrail & deterministic OutputGuardrail
│   ├── narrator.py        # Gemini 2.5 Flash structured narrator, usage_metadata & 2-way key handler
│   └── harness.py         # Orchestrates InputGuardrail -> NarratorEngine -> OutputGuardrail
├── public/
│   ├── index.html         # 100dvh responsive cockpit UI
│   ├── styles.css         # Dark/Light theme & responsive styling
│   └── app.js             # Chat controller, SVG route animation & live token telemetry
├── tests/
│   └── test_harness.py    # 9 unit & full 8–12 turn playthrough tests
├── DESIGN.md              # Concise (<60 words each) answers for The moment, The cut, and The miss
├── .env.example           # Environment variable template
├── requirements.txt       # Python dependencies
└── vercel.json            # One-click Vercel Python serverless deployment config
```

---

## Local Setup & Testing

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure API key (or enter it directly in the UI via the '🔑 API Key' button)
cp .env.example .env

# 3. Start the server
uvicorn api.index:app --reload --port 8000
```
Open **http://127.0.0.1:8000** in your browser.

### Run the Guardrail & Full Playthrough Test Suite
```bash
pytest -v
```

---

## Deploy to Vercel

1. Push this repository to GitHub.
2. Import the repository into **Vercel** (`vercel.json` is pre-configured for `@vercel/python`).
3. Add `GEMINI_API_KEY` in Vercel **Project Settings → Environment Variables** (or leave it blank to let players enter their own key in the top bar).
