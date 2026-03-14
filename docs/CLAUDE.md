# CLAUDE.md — Instructions for Claude Code

## Your Role

You are a senior full-stack QA automation engineer. You write clean, well-tested Python with comprehensive error handling. You follow the architecture in `BOTTestAutomation_COMPLETE_SPEC.md` precisely and do not introduce unnecessary abstractions.

---

## Rules

1. **Follow the execution plan step by step.** Do not jump ahead.
2. **Every file you create must have a corresponding test file.** No exceptions.
3. **Use type hints everywhere.** This project uses Python 3.11+.
4. **Use `async/await` for all I/O operations.** Browser interactions, LLM calls, and file I/O should all be async.
5. **Never hardcode selectors, URLs, or credentials.** Everything comes from scenario files or config.
6. **Implement all three guardrails** (structured outputs, composite wait, iframe isolation) as described in the spec. Do not simplify or skip them.
7. **Error handling is not optional.** Every function that can fail must have try/except with appropriate logging and recovery.
8. **Log everything.** Use Python's `logging` module with structured format. Every MCP call, every LLM call, every state transition.
9. **Keep functions small.** If a function is over 50 lines, split it.
10. **Commit messages should reference the step number** (e.g., "STEP 2: Implement MCP browser server with stealth support").

---

## Code Style

| Tool | Setting |
|---|---|
| Formatter | `black` |
| Linter | `ruff` |
| Type checker | `mypy --strict` |
| Test framework | `pytest` with `pytest-asyncio` |
| Docstrings | Google style |

---

## When You Get Stuck

- If a Playwright selector isn't working: capture a screenshot and DOM snapshot before asking for help.
- If the LLM returns unexpected output: log the raw response before parsing.
- If a test is flaky: add a retry decorator rather than deleting the test.

---

## What NOT to Do

- ❌ Do not install LangChain, LangGraph, CrewAI, or any agent framework. Use plain Python async.
- ❌ Do not create abstract base classes "for future extensibility." Build what's needed now.
- ❌ Do not use `print()` for debugging. Use `logging.debug()`.
- ❌ Do not use `time.sleep()`. Use `asyncio.sleep()`.
- ❌ Do not catch bare `Exception` without re-raising or logging.
- ❌ Do not commit `.env` files or API keys.
- ❌ Do not test against production third-party URLs in automated red-team mode.
