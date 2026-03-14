# CODE_REVIEW.md — Code Review Checklist

## Before Submitting Code for Review

### Correctness
- [ ] Does the code implement the exact behavior described in `BOTTestAutomation_COMPLETE_SPEC.md`?
- [ ] Are all three guardrails implemented?
  - [ ] Guardrail 1: Structured outputs via Anthropic tool calling (`make_decision`)
  - [ ] Guardrail 2: Composite wait strategy (`typing → stabilization`, no `networkidle`)
  - [ ] Guardrail 3: Iframe traversal with `WidgetContext` frame scoping
- [ ] Does error handling follow the retry → circuit breaker → graceful skip pattern?
- [ ] Are all foreign key relationships correct in the SQLModel schema?
- [ ] Does the security module enforce all three activation gates?

### Code Quality
- [ ] All functions have type hints (parameters AND return types)
- [ ] All public functions have Google-style docstrings
- [ ] No function exceeds 50 lines
- [ ] No hardcoded selectors, URLs, or credentials
- [ ] Uses `logging` module, **never** `print()`
- [ ] Uses `asyncio.sleep()`, **never** `time.sleep()`
- [ ] No bare `except Exception` without logging and re-raise or explicit suppression

### Testing
- [ ] Every new file has a corresponding test file
- [ ] Tests cover the happy path AND at least 2 failure modes
- [ ] Async tests use `@pytest.mark.asyncio`
- [ ] Tests do not depend on network access (mock external services)
- [ ] Integration tests are marked with `@pytest.mark.integration`
- [ ] Flaky tests have retry decorators with a comment explaining why

### Security
- [ ] Red-team features are disabled by default (`red_team_enabled: false` in settings)
- [ ] No secrets or API keys in code (from environment variables only)
- [ ] Mock data uses obviously fake values (account numbers start with `4111-0000`)
- [ ] Allowlist is checked before any active probing
- [ ] All security probes logged with full request/response pairs
- [ ] `.env` files are in `.gitignore`

### Report Accuracy
- [ ] JSON report matches the schema defined in section 2.5 of the spec
- [ ] Transcript timestamps are in ISO-8601 format (`%Y-%m-%dT%H:%M:%SZ`)
- [ ] `ERROR` status used for tool failures; `FAIL` for bot test failures
- [ ] Latency metrics are calculated correctly (avg, max, p95)
