#!/usr/bin/env bash
# test.sh — Run the unit test suite for BOTTestAutomation
# Usage:
#   ./test.sh              → run all unit tests
#   ./test.sh -v           → verbose output
#   ./test.sh -k reasoning → run only tests matching "reasoning"
#   ./test.sh --cov        → run with coverage report

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/.venv"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[bottest]${NC} $*"; }
warn()  { echo -e "${YELLOW}[bottest]${NC} $*"; }

# ── Activate venv ─────────────────────────────────────────────────────────────
if [ ! -d "$VENV" ]; then
  info "No venv found. Run ./start.sh first to set up the environment."
  exit 1
fi
source "$VENV/bin/activate"

# ── Parse args ────────────────────────────────────────────────────────────────
PYTEST_ARGS=()
COV=0

for arg in "$@"; do
  case "$arg" in
    --cov) COV=1 ;;
    *)     PYTEST_ARGS+=("$arg") ;;
  esac
done

# Always ignore browser integration tests (require a live URL)
PYTEST_ARGS+=(--ignore=tests/test_mcp_browser.py)

if [ $COV -eq 1 ]; then
  PYTEST_ARGS+=(--cov=backend --cov-report=term-missing --cov-report=html:reports/coverage)
  info "Coverage report will be written to reports/coverage/index.html"
fi

# ── Run ───────────────────────────────────────────────────────────────────────
info "Running unit tests..."
echo ""
python3 -m pytest "$ROOT/tests/" "${PYTEST_ARGS[@]}"
