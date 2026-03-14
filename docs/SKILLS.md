# SKILLS.md — Reusable Skills Registry

## Skill: Browser Navigation

- **File:** `backend/mcp_browser.py`
- **Functions:** `navigate_to_url`, `click_element`, `type_text`, `wait_for_selector`
- **Dependencies:** `playwright`, `playwright-stealth`
- **Error handling:** `_retry()` with exponential backoff (1s → 2s → 4s, 3 attempts)

---

## Skill: Chat Widget Interaction

- **File:** `backend/mcp_browser.py`
- **Functions:** `detect_chat_widget`, `send_chat_message`, `wait_for_bot_response`, `extract_chat_messages`
- **Dependencies:** Browser Navigation skill
- **Key behavior:**
  - **Guardrail 3:** `detect_chat_widget` returns a `WidgetContext` with the Playwright `Frame` reference. All subsequent calls execute within that frame (handles cross-origin iframes for LivePerson, Genesys, Salesforce, etc.)
  - **Guardrail 2:** `wait_for_bot_response` uses a 7-step composite wait: typing indicator → stabilization loop. Does NOT use `networkidle`.
  - Multiple submit methods: Enter-key and button-click, auto-detected

---

## Skill: Conversational Reasoning

- **File:** `backend/reasoning.py`
- **Functions:** `call_reason`, `lookup_mock_data`
- **Dependencies:** `anthropic` SDK
- **Key behavior:**
  - **Guardrail 1:** Forces Anthropic tool calling with `tool_choice: {type: tool, name: make_decision}` — no markdown fences in output
  - `AgentDecision` Pydantic model validates all output before ACT step
  - Crashes fast on invalid decisions rather than silently proceeding

---

## Skill: OBSERVE-REASON-ACT Engine

- **File:** `backend/engine.py`
- **Functions:** `run_scenario`, `reasoning_loop`, `observe`, `act`
- **Dependencies:** Conversational Reasoning, Chat Widget Interaction
- **Key behavior:**
  - FSM with 8 states (INIT → ... → COMPLETE/FAILED/ESCALATED/ERROR)
  - Circuit breaker: 5 consecutive ERROR scenarios halt the entire run (exit code 2)
  - Bot unresponsive detection: 3 consecutive empty OBSERVE results → FAILED
  - Human escalation detection via keyword matching

---

## Skill: Report Generation

- **File:** `backend/reporter.py`
- **Functions:** `generate_report_json`, `generate_transcript`, `generate_security_log`, `print_console_summary`, `write_report_json`, `write_transcript`
- **Dependencies:** `rich` (optional, falls back gracefully)
- **Key behavior:**
  - `report.json` — structured JSON with latency percentiles (avg, max, p95)
  - `transcript.txt` — ISO-8601 timestamped, SYSTEM/USER/BOT/AGENT_REASONING senders
  - `security.log` — OBSERVE/PROBE/RESULT/SCORE entries (only when red-team enabled)
  - ERROR vs FAIL status distinction (tool failure vs bot test failure)

---

## Skill: Security Probing

- **File:** `backend/security.py`
- **Functions:** `check_allowlist`, `can_activate_red_team`, `confirm_red_team`, `run_observe_only`, `run_active_probes`
- **Dependencies:** Chat Widget Interaction
- **Key behavior:**
  - Triple gate: `--red-team` flag AND allowlist match AND user confirmation
  - Observe-only mode: passive DOM analysis, no injected payloads
  - Active probe library: system prompt extraction, instruction override, context boundary, role confusion
  - All probes logged with full request/response pairs
  - **DISABLED by default**

---

## Skill: Persistence

- **File:** `backend/models.py`
- **Functions:** `create_tables`, `get_engine`, `get_session`
- **Schema:** `TestRun → ConversationThread → MessageExchange`
- **Dependencies:** `sqlmodel`, SQLite
