# FEATURES.md — Feature Status Tracker

## Phase 1: Foundation

| Feature | Status | Priority | File |
|---|---|---|---|
| SQLModel schema (TestRun, Thread, Message) | ✅ DONE | P0 | `backend/models.py` |
| Config loading (settings.yaml) | ✅ DONE | P0 | `config/settings.yaml` + `run.py` |
| MCP Browser: Core functions | ✅ DONE | P0 | `backend/mcp_browser.py` |
| MCP Browser: Chat widget detection | ✅ DONE | P0 | `backend/mcp_browser.py` |
| MCP Browser: Composite wait strategy | ✅ DONE | P0 | `backend/mcp_browser.py` |
| MCP Browser: Iframe traversal | ✅ DONE | P0 | `backend/mcp_browser.py` |
| OBSERVE-REASON-ACT engine | ✅ DONE | P0 | `backend/engine.py` |
| Structured output enforcement | ✅ DONE | P0 | `backend/reasoning.py` |
| Report generation (JSON + transcript) | ✅ DONE | P0 | `backend/reporter.py` |
| CLI entry point (run.py) | ✅ DONE | P0 | `run.py` |

## Phase 2: Security & Polish

| Feature | Status | Priority | File |
|---|---|---|---|
| Allowlist management | ✅ DONE | P1 | `backend/security.py` |
| Observe-only security mode | ✅ DONE | P1 | `backend/security.py` |
| Active red-team probes | ✅ DONE | P1 | `backend/security.py` |
| Circuit breaker | ✅ DONE | P1 | `backend/engine.py` + `run.py` |
| Console output formatting (Rich) | ✅ DONE | P2 | `backend/reporter.py` |
| Sentiment scoring (post-processing) | NOT STARTED | P1 | After Phase 1 |

## Phase 3: Extensibility

| Feature | Status | Priority | Notes |
|---|---|---|---|
| Multi-provider LLM support (OpenAI, Google) | NOT STARTED | P2 | After Phase 1 |
| Parallel scenario execution | NOT STARTED | P2 | After Phase 2 |
| HTML report dashboard | NOT STARTED | P3 | Nice to have |
| CI/CD integration (GitHub Actions) | NOT STARTED | P3 | Nice to have |
| PostgreSQL migration | NOT STARTED | P3 | Only when needed |

## Status Legend

| Symbol | Meaning |
|---|---|
| `NOT STARTED` | In backlog |
| `IN PROGRESS` | Currently being implemented |
| `REVIEW` | Code written, needs review |
| `✅ DONE` | Implemented, tested, merged |
| `BLOCKED` | Waiting on dependency |
