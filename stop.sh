#!/usr/bin/env bash
# stop.sh — Gracefully stop a running BOTTestAutomation session
# Usage: ./stop.sh

ROOT="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$ROOT/.bottest.pid"
MOCK_PID_FILE="$ROOT/.mock_server.pid"
MOCK_PORT=8080

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[bottest]${NC} $*"; }
warn()  { echo -e "${YELLOW}[bottest]${NC} $*"; }
error() { echo -e "${RED}[bottest]${NC} $*" >&2; }

stopped=0

# ── Stop via PID file (started with start.sh) ─────────────────────────────────
if [ -f "$PID_FILE" ]; then
  PID=$(cat "$PID_FILE")
  if kill -0 "$PID" 2>/dev/null; then
    info "Stopping bottest process (PID $PID)..."
    kill -TERM "$PID" 2>/dev/null || true
    # Give it 5 s to exit cleanly, then force
    for i in $(seq 1 10); do
      sleep 0.5
      kill -0 "$PID" 2>/dev/null || { stopped=1; break; }
    done
    if [ $stopped -eq 0 ]; then
      warn "Process did not exit cleanly; sending SIGKILL..."
      kill -KILL "$PID" 2>/dev/null || true
      stopped=1
    fi
  else
    warn "PID $PID in .bottest.pid is not running."
    stopped=1
  fi
  rm -f "$PID_FILE"
fi

# ── Also kill any stray playwright/chromium children ─────────────────────────
STRAY=$(pgrep -f "run\.py|bottest|chromium.*playwright" 2>/dev/null || true)
if [ -n "$STRAY" ]; then
  warn "Cleaning up stray processes: $STRAY"
  echo "$STRAY" | xargs kill -TERM 2>/dev/null || true
  stopped=1
fi

# ── Stop mock http.server on port 8080 ───────────────────────────────────────
if [ -f "$MOCK_PID_FILE" ]; then
  MOCK_PID=$(cat "$MOCK_PID_FILE")
  if kill -0 "$MOCK_PID" 2>/dev/null; then
    info "Stopping mock chatbot server (PID $MOCK_PID)..."
    kill -TERM "$MOCK_PID" 2>/dev/null || true
  else
    warn "Mock server PID $MOCK_PID is not running."
  fi
  rm -f "$MOCK_PID_FILE"
  stopped=1
else
  # Kill any leftover http.server on the mock port by port lookup
  MOCK_STRAY=$(lsof -ti tcp:${MOCK_PORT} 2>/dev/null || true)
  if [ -n "$MOCK_STRAY" ]; then
    warn "Killing stray mock server on port ${MOCK_PORT} (PID $MOCK_STRAY)..."
    echo "$MOCK_STRAY" | xargs kill -TERM 2>/dev/null || true
    stopped=1
  fi
fi

if [ $stopped -eq 1 ]; then
  info "All bottest processes stopped."
else
  warn "No running bottest process found."
fi
