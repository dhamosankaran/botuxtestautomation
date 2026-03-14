#!/usr/bin/env python3
"""CLI entry point for BOTTestAutomation.

Usage:
    python run.py --scenario scenarios/example_basic.yaml
    python run.py --scenario scenarios/citi.yaml --red-team
    python run.py --scenario-dir scenarios/banking/
    python run.py --scenario scenarios/example.yaml --headless false --max-turns 10
"""
import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

# Load .env — check backend/.env first, then root .env
try:
    from dotenv import load_dotenv
    for _env_path in ("backend/.env", ".env"):
        if Path(_env_path).exists():
            load_dotenv(_env_path, override=False)
            break
except ImportError:
    pass  # dotenv optional; user can export vars manually

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("bottest")


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


def load_settings(path: str = "config/settings.yaml") -> dict:
    """Load and return settings.yaml as a dict.

    Args:
        path: Path to the settings YAML file.

    Returns:
        Settings dict. Falls back to defaults on file not found.
    """
    try:
        return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        logger.warning("settings.yaml not found at %s; using defaults", path)
        return {}


def load_scenario(path: str) -> dict:
    """Load and return a scenario YAML file as a dict.

    Args:
        path: Path to the scenario YAML file.

    Returns:
        Scenario dict (the value under the 'scenario' key).

    Raises:
        SystemExit: If the file is not found or invalid.
    """
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return raw.get("scenario", raw)
    except FileNotFoundError:
        logger.error("Scenario file not found: %s", path)
        sys.exit(1)
    except yaml.YAMLError as exc:
        logger.error("Invalid YAML in %s: %s", path, exc)
        sys.exit(1)


def load_mock_data(path: str = "config/mock_data.json") -> dict:
    """Load synthetic test data from mock_data.json.

    Args:
        path: Path to mock_data.json.

    Returns:
        Dict of mock data values. Empty dict on failure.
    """
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not load mock_data.json: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Settings overrides from CLI args
# ---------------------------------------------------------------------------


def apply_overrides(settings: dict, args: argparse.Namespace) -> dict:
    """Apply CLI argument overrides to the settings dict.

    Args:
        settings: Base settings loaded from settings.yaml.
        args: Parsed CLI arguments.

    Returns:
        Settings dict with overrides applied (mutated in place).
    """
    browser = settings.setdefault("browser", {})
    agent = settings.setdefault("agent", {})
    security = settings.setdefault("security", {})

    if args.headless is not None:
        browser["headless"] = args.headless.lower() == "true"
        logger.info("Override: headless=%s", browser["headless"])

    if args.max_turns is not None:
        agent["max_turns_default"] = args.max_turns
        logger.info("Override: max_turns=%d", args.max_turns)

    if args.red_team:
        security["red_team_enabled"] = True
        logger.info("Override: red_team_enabled=True")

    return settings


# ---------------------------------------------------------------------------
# Single scenario execution
# ---------------------------------------------------------------------------


async def execute_scenario(
    scenario_path: str,
    settings: dict,
    mock_data: dict,
    red_team: bool,
) -> dict:
    """Run one scenario file end-to-end and return the report dict.

    Args:
        scenario_path: Path to the scenario YAML file.
        settings: Settings dict (with overrides applied).
        mock_data: Synthetic data from mock_data.json.
        red_team: Whether --red-team flag was passed.

    Returns:
        Report dict from generate_report_json().
    """
    from backend.engine import run_scenario
    from backend.models import create_tables, persist_session_to_db
    from backend.reporter import (
        generate_report_json,
        generate_transcript,
        print_console_summary,
        score_sentiments,
        write_report_json,
        write_transcript,
    )
    from backend.security import can_activate_red_team

    scenario = load_scenario(scenario_path)
    # Merge per-scenario mock_data into global mock_data (scenario wins)
    combined_mock = {**mock_data, **scenario.get("mock_data", {})}
    scenario["mock_data"] = combined_mock

    # Propagate --max-turns CLI override to the scenario dict so the engine sees it
    max_turns_override = settings.get("agent", {}).get("max_turns_default")
    if max_turns_override is not None:
        scenario["max_turns"] = int(max_turns_override)
        logger.info("Scenario max_turns set to %d from CLI override", max_turns_override)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_dir = Path(
        settings.get("reporting", {}).get("output_dir", "./reports")
    ) / run_id
    report_dir.mkdir(parents=True, exist_ok=True)

    # Security gate check
    security_cfg = settings.get("security", {})
    active_red_team = False
    if red_team:
        active_red_team = can_activate_red_team(
            target_url=scenario.get("target_url", ""),
            red_team_flag=True,
            allowlist_path=security_cfg.get("allowlist_path", "config/allowlist.json"),
            require_confirmation=security_cfg.get("require_confirmation", True),
        )

    logger.info("Starting run %s: %s", run_id, scenario.get("name", "?"))
    create_tables()
    started_at = datetime.now(timezone.utc)

    session = await run_scenario(
        scenario=scenario,
        settings=settings,
        run_id=run_id,
        red_team=active_red_team,
    )

    completed_at = datetime.now(timezone.utc)
    transcript = generate_transcript(session, run_id)
    write_transcript(report_dir, transcript)

    # Sentiment scoring — post-processing LLM call on all bot turns
    bot_entries = [(e.turn, e.content) for e in session.history if e.sender == "bot"]
    sentiment_by_turn: dict = {}
    if bot_entries:
        bot_texts = [content for _, content in bot_entries]
        scores = await score_sentiments(bot_texts)
        sentiment_by_turn = {turn: score for (turn, _), score in zip(bot_entries, scores)}

    report = generate_report_json(
        run_id=run_id,
        scenario=scenario,
        session=session,
        started_at=started_at,
        completed_at=completed_at,
        transcript_text=transcript,
        sentiment_by_turn=sentiment_by_turn,
    )
    write_report_json(report_dir, report)
    print_console_summary(report, report_dir)

    # Security log
    if active_red_team and session.probe_results:
        from backend.reporter import write_security_log, generate_security_log
        log = generate_security_log(session.probe_results, run_id)
        write_security_log(report_dir, log)

    # DB persistence — non-blocking; errors are logged but do not fail the run
    persist_session_to_db(
        session=session,
        run_id=run_id,
        started_at=started_at,
        completed_at=completed_at,
        report_path=str(report_dir),
        sentiment_by_turn=sentiment_by_turn,
    )

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse and return command-line arguments.

    Returns:
        Parsed argparse Namespace.
    """
    parser = argparse.ArgumentParser(
        prog="bottest",
        description="BOTTestAutomation — Autonomous chatbot QA and security testing",
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--scenario",
        metavar="FILE",
        help="Path to a single scenario YAML file",
    )
    group.add_argument(
        "--scenario-dir",
        metavar="DIR",
        help="Path to a directory of scenario YAML files (runs all *.yaml)",
    )

    parser.add_argument(
        "--red-team",
        action="store_true",
        default=False,
        help="Enable red-team security probing (requires allowlist match + confirmation)",
    )
    parser.add_argument(
        "--headless",
        metavar="true|false",
        default=None,
        help="Override headless browser setting (default: from settings.yaml)",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=None,
        metavar="N",
        help="Override maximum conversation turns",
    )
    parser.add_argument(
        "--settings",
        default="config/settings.yaml",
        metavar="FILE",
        help="Path to settings.yaml (default: config/settings.yaml)",
    )

    return parser.parse_args()


async def main() -> int:
    """Main async entry point.

    Returns:
        Exit code: 0=success, 1=test failure, 2=circuit breaker / critical error.
    """
    args = parse_args()
    settings = load_settings(args.settings)
    apply_overrides(settings, args)
    mock_data = load_mock_data()

    # Collect scenario paths
    if args.scenario:
        scenario_paths = [args.scenario]
    else:
        scenario_dir = Path(args.scenario_dir)
        if not scenario_dir.is_dir():
            logger.error("--scenario-dir is not a directory: %s", args.scenario_dir)
            return 2
        scenario_paths = sorted(scenario_dir.glob("*.yaml"))
        if not scenario_paths:
            logger.error("No *.yaml files found in %s", args.scenario_dir)
            return 2
        scenario_paths = [str(p) for p in scenario_paths]

    # Circuit breaker state
    circuit_threshold = settings.get("agent", {}).get("circuit_breaker_threshold", 5)
    consecutive_errors = 0
    any_failure = False

    for scenario_path in scenario_paths:
        logger.info("Running scenario: %s", scenario_path)
        try:
            report = await execute_scenario(
                scenario_path=scenario_path,
                settings=settings,
                mock_data=mock_data,
                red_team=args.red_team,
            )
            if report["status"] == "ERROR":
                consecutive_errors += 1
            else:
                consecutive_errors = 0

            if report["status"] in ("FAIL", "ERROR", "PARTIAL"):
                any_failure = True

        except Exception as exc:
            logger.error("Unhandled error in scenario %s: %s", scenario_path, exc,
                         exc_info=True)
            consecutive_errors += 1
            any_failure = True

        # Circuit breaker — write diagnostic.json then halt
        if consecutive_errors >= circuit_threshold:
            logger.critical(
                "Circuit breaker triggered: %d consecutive critical errors. Halting.",
                consecutive_errors,
            )
            diag_dir = Path(settings.get("reporting", {}).get("output_dir", "./reports"))
            diag_dir.mkdir(parents=True, exist_ok=True)
            diag_path = diag_dir / "diagnostic.json"
            diag_path.write_text(
                json.dumps(
                    {
                        "circuit_breaker_triggered": True,
                        "consecutive_errors": consecutive_errors,
                        "threshold": circuit_threshold,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "last_scenario": str(scenario_path),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            logger.critical("Diagnostic written: %s", diag_path)
            return 2

    return 0 if not any_failure else 1


def main_sync() -> None:
    """Synchronous wrapper used by the 'bottest' console script entry point."""
    sys.exit(asyncio.run(main()))


if __name__ == "__main__":
    main_sync()
