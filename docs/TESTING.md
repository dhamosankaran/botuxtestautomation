# TESTING.md — Testing Strategy

## Test Pyramid

- **70%** Unit tests — individual functions, all dependencies mocked
- **25%** Integration tests — component interactions, local mock chatbot
- **5%** Manual tests — against live targets, Phase 6 only

## Running Tests

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# All tests
PYTHONPATH=. pytest tests/ -v

# Unit tests only (fast, no Playwright)
PYTHONPATH=. pytest tests/ -v -k "not integration"

# Integration tests (requires Playwright)
PYTHONPATH=. pytest tests/ -v -k "integration"

# With coverage
PYTHONPATH=. pytest tests/ --cov=backend --cov-report=html
```

## Test Files

| File | Type | What It Tests |
|---|---|---|
| `tests/test_models.py` | Unit | SQLModel schema creation, CRUD, FK relationships |
| `tests/test_reasoning.py` | Unit | AgentDecision validation, tool schema, mock LLM calls |
| `tests/test_engine.py` | Unit | FSM transitions, escalation detection, mocked loop |
| `tests/test_security.py` | Unit | Allowlist matching, triple-gate, probe leak detection |
| `tests/test_mcp_browser.py` | Integration | Full Playwright against `tests/fixtures/mock_chatbot.html` |

## Local Mock Chatbot (`tests/fixtures/mock_chatbot.html`)

The HTML fixture supports four modes (toggled via checkboxes):

| Mode | Behavior |
|---|---|
| Normal | Typing indicator (1 s) then canned response |
| Break Mode | Widget disappears on send (tests widget-not-found recovery) |
| No Response | Typing indicator appears but bot never replies (tests timeout) |
| Slow Response | 3 s delay instead of 1 s (tests stabilization timing) |

Canned responses are keyword-triggered:
- `credit card / apr / rewards` → product + APR information
- `balance / checking / savings` → account balances
- `pin / account number / ssn` → identity verification request
- `human / agent / transfer` → escalation to human agent

## Key Test Scenarios

### MCP Browser Tests
1. `test_navigate_and_extract` — navigate to mock page, extract text
2. `test_detect_widget_main_frame` — find widget in main frame
3. `test_detect_widget_returns_none_on_empty_page` — no widget → None
4. `test_send_message_via_button` — submit via button click
5. `test_send_message_enter_key` — submit via Enter key
6. `test_wait_for_bot_response_with_typing` — composite wait through typing indicator
7. `test_wait_for_bot_response_timeout` — returns False on timeout
8. `test_capture_screenshot_creates_file` — screenshot saved to disk
9. `test_retry_on_timeout_raises` — 3x retry then exception

### Engine Tests
1. `test_happy_path_goal_reached` — high confidence → COMPLETE + PASS
2. `test_max_turns_exceeded` — turn limit → FAILED + PARTIAL
3. `test_bot_unresponsive_terminates` — 3 empty → FAILED
4. `test_human_escalation_detected` — escalation phrase → ESCALATED

### Security Tests
1. `test_red_team_disabled_by_default` — flag=False → no probes
2. `test_red_team_blocked_without_allowlist` — flag=True but not allowlisted → blocked
3. `test_red_team_requires_all_three_gates` — all three pass → True
4. `test_red_team_blocked_by_user_decline` — user says N → blocked
5. `test_check_for_leak_detects_system_prompt` — leak heuristic fires
6. `test_observe_only_returns_observations` — passive mode returns results

### Reasoning Tests
1. `test_valid_respond_decision` — well-formed AgentDecision
2. `test_confidence_too_high_raises` — confidence > 1.0 → ValidationError
3. `test_invalid_action_raises` — unknown action → ValueError
4. `test_call_reason_returns_agent_decision` — mocked LLM → valid decision
5. `test_call_reason_raises_without_api_key` — missing key → RuntimeError
