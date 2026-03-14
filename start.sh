#!/usr/bin/env bash
# start.sh — Set up and run BOTTestAutomation
# Usage:
#   ./start.sh                                                  → demo run against built-in mock chatbot
#   ./start.sh --scenario scenarios/citi_credit_card_inquiry.yaml
#   ./start.sh --scenario-dir scenarios/
#   ./start.sh --scenario scenarios/example_basic.yaml --headless false
#   ./start.sh --red-team --scenario scenarios/citi_credit_card_inquiry.yaml

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/.venv"
PID_FILE="$ROOT/.bottest.pid"
MOCK_PID_FILE="$ROOT/.mock_server.pid"
MOCK_PORT=8080

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[bottest]${NC} $*"; }
warn()  { echo -e "${YELLOW}[bottest]${NC} $*"; }
error() { echo -e "${RED}[bottest]${NC} $*" >&2; }

# ── Cleanup on exit ───────────────────────────────────────────────────────────
cleanup() {
  if [ -f "$MOCK_PID_FILE" ]; then
    MOCK_PID=$(cat "$MOCK_PID_FILE")
    # Graceful SIGTERM first, then SIGKILL after 3s if still running
    kill "$MOCK_PID" 2>/dev/null || true
    sleep 0.3
    kill -9 "$MOCK_PID" 2>/dev/null || true
    rm -f "$MOCK_PID_FILE"
    info "Mock chatbot server stopped."
  fi
  rm -f "$PID_FILE"
}
trap cleanup EXIT INT TERM

# ── 1. Python version guard ───────────────────────────────────────────────────
PYTHON_VERSION=$(python3 -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo "0")
PYTHON_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)" 2>/dev/null || echo "0")
if [ "$PYTHON_MAJOR" -lt 3 ] || [ "$PYTHON_VERSION" -lt 10 ]; then
  error "Python 3.10+ is required (found: $(python3 --version 2>&1 || echo 'not found'))"
  exit 1
fi

# ── 2. Virtual environment ────────────────────────────────────────────────────
if [ ! -d "$VENV" ]; then
  info "Creating virtual environment..."
  python3 -m venv "$VENV"
fi

source "$VENV/bin/activate"

# ── 3. Dependencies ───────────────────────────────────────────────────────────
info "Checking dependencies..."

# Only install as editable package if a package definition exists
if [ -f "$ROOT/pyproject.toml" ] || [ -f "$ROOT/setup.py" ] || [ -f "$ROOT/setup.cfg" ]; then
  pip install -e "$ROOT" --quiet --disable-pip-version-check
fi

pip install -r "$ROOT/requirements.txt" --quiet --disable-pip-version-check

# ── 4. Playwright browsers ────────────────────────────────────────────────────
# playwright install is idempotent — suppress output if already installed
info "Ensuring Playwright Chromium browser is installed..."
if ! playwright install chromium --dry-run 2>/dev/null | grep -q "chromium"; then
  playwright install chromium 2>/dev/null || playwright install chromium
else
  playwright install chromium --quiet >/dev/null 2>&1 || playwright install chromium >/dev/null 2>&1
fi

# ── 5. Environment ────────────────────────────────────────────────────────────
ENV_FILE="$ROOT/backend/.env"
if [ ! -f "$ENV_FILE" ]; then
  error "No backend/.env found. Create it with at least one API key:"
  error "  OPENAI_API_KEY=sk-..."
  error "  GEMINI_API_KEY=AIza..."
  exit 1
fi

# Check at least one LLM key is present (allow optional spaces around '=')
if ! grep -qE "^(OPENAI_API_KEY|GEMINI_API_KEY|GOOGLE_API_KEY|ANTHROPIC_API_KEY)\s*=\s*.+" "$ENV_FILE"; then
  error "No LLM API key found in backend/.env"
  error "Add at least one of: OPENAI_API_KEY, GEMINI_API_KEY, ANTHROPIC_API_KEY"
  exit 1
fi

# ── 6. Parse args / defaults ───────────────────────────────────────────────────
ARGS=("$@")
START_MOCK=false

if [ ${#ARGS[@]} -eq 0 ]; then
  # No arguments → use built-in mock chatbot for a quick demo
  ARGS=(--scenario "$ROOT/scenarios/example_basic.yaml")
  START_MOCK=true
  warn "No arguments given — running demo against built-in mock chatbot."
else
  # Check if any scenario argument targets localhost:8080
  for arg in "${ARGS[@]}"; do
    if [[ "$arg" == *"localhost:${MOCK_PORT}"* ]] || [[ "$arg" == *"127.0.0.1:${MOCK_PORT}"* ]]; then
      START_MOCK=true
      break
    fi
  done

  # Also check inside scenario files referenced by --scenario
  NUM_ARGS=${#ARGS[@]}
  for i in "${!ARGS[@]}"; do
    if [[ "${ARGS[$i]}" == "--scenario" ]]; then
      NEXT_IDX=$((i + 1))
      if [ "$NEXT_IDX" -lt "$NUM_ARGS" ]; then
        SCENARIO_FILE="${ARGS[$NEXT_IDX]}"
        if [ -f "$SCENARIO_FILE" ] && grep -q "localhost:${MOCK_PORT}" "$SCENARIO_FILE" 2>/dev/null; then
          START_MOCK=true
        fi
      fi
    fi
  done
fi

# ── 7. Start mock chatbot server if needed ─────────────────────────────────────
if [ "$START_MOCK" = true ]; then
  # Gracefully stop any leftover server on the port (SIGTERM first, then SIGKILL)
  LEFTOVER_PIDS=$(lsof -ti tcp:${MOCK_PORT} 2>/dev/null || true)
  if [ -n "$LEFTOVER_PIDS" ]; then
    echo "$LEFTOVER_PIDS" | xargs kill 2>/dev/null || true
    sleep 0.3
    echo "$LEFTOVER_PIDS" | xargs kill -9 2>/dev/null || true
  fi

  info "Starting mock chatbot server on http://localhost:${MOCK_PORT} ..."
  python3 -m http.server ${MOCK_PORT} \
    --directory "$ROOT/tests/fixtures" \
    --bind 127.0.0.1 \
    >/dev/null 2>&1 &
  echo $! > "$MOCK_PID_FILE"

  # Wait until the port is open (max 5s), then fail clearly if it never starts
  READY=false
  for i in $(seq 1 10); do
    if curl -sf "http://localhost:${MOCK_PORT}/" >/dev/null 2>&1; then
      READY=true
      break
    fi
    sleep 0.5
  done

  if [ "$READY" = false ]; then
    error "Mock chatbot server failed to start on port ${MOCK_PORT} after 5s"
    error "Check that nothing else is bound to port ${MOCK_PORT} and that tests/fixtures/ exists"
    exit 1
  fi

  info "Mock chatbot ready at http://localhost:${MOCK_PORT}/mock_chatbot.html"
fi

# ── 8. Run ─────────────────────────────────────────────────────────────────────
info "Starting BOTTestAutomation..."
echo ""

# Run directly (not backgrounded) so signal handling and exit codes are clean
set +e
python3 "$ROOT/run.py" "${ARGS[@]}"
EXIT_CODE=$?
set -e

rm -f "$PID_FILE"
echo ""

case $EXIT_CODE in
  0) info  "Run finished: ALL PASS" ;;
  1) warn  "Run finished: one or more scenarios FAILED" ;;
  2) error "Run aborted: circuit breaker / critical error" ;;
  *) error "Run exited with unexpected code $EXIT_CODE" ;;
esac

exit $EXIT_CODE
