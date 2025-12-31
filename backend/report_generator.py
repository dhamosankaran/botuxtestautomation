"""
Report Generator Module

Generate PDF and CSV reports for test results.
"""

import os
import csv
import io
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass

from sqlmodel import Session, select
from models import ConversationLog, TestRun


@dataclass
class ReportData:
    """Data structure for report generation."""
    test_run: TestRun
    conversations: List[ConversationLog]
    summary: dict
    generated_at: datetime


def generate_csv_report(session: Session, test_run_id: int) -> str:
    """
    Generate a CSV report for a test run.
    
    Args:
        session: Database session
        test_run_id: ID of the test run
    
    Returns:
        CSV content as string
    """
    # Get test run
    test_run = session.get(TestRun, test_run_id)
    if not test_run:
        raise ValueError(f"Test run {test_run_id} not found")
    
    # Get conversation logs
    logs = session.exec(
        select(ConversationLog).where(
            ConversationLog.test_run_id == test_run_id
        ).order_by(ConversationLog.id)
    ).all()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        "ID", "Utterance", "Bot Response", "Status", "Category",
        "Score", "Latency (ms)", "Turns", "LLM Feedback", "Timestamp"
    ])
    
    # Data rows
    for log in logs:
        writer.writerow([
            log.id,
            log.utterance,
            (log.bot_response or "")[:200],  # Truncate long responses
            log.status,
            log.category or "",
            log.overall_score or "",
            log.latency_ms or "",
            log.turns or 1,
            (log.llm_feedback or "")[:100],  # Truncate feedback
            log.timestamp.isoformat() if log.timestamp else ""
        ])
    
    # Summary section
    writer.writerow([])
    writer.writerow(["=== SUMMARY ==="])
    writer.writerow(["Test Run ID", test_run_id])
    writer.writerow(["Status", test_run.status])
    writer.writerow(["Started", test_run.started_at])
    writer.writerow(["Completed", test_run.completed_at])
    writer.writerow(["Total Tests", len(logs)])
    
    passed = sum(1 for l in logs if l.status == "pass")
    writer.writerow(["Passed", passed])
    writer.writerow(["Failed", len(logs) - passed])
    writer.writerow(["Pass Rate", f"{(passed / len(logs) * 100):.1f}%" if logs else "N/A"])
    
    scores = [l.overall_score for l in logs if l.overall_score]
    if scores:
        writer.writerow(["Avg Score", f"{sum(scores) / len(scores):.2f}"])
    
    return output.getvalue()


def generate_markdown_report(session: Session, test_run_id: int) -> str:
    """
    Generate a Markdown report for a test run.
    
    Args:
        session: Database session
        test_run_id: ID of the test run
    
    Returns:
        Markdown content as string
    """
    # Get test run
    test_run = session.get(TestRun, test_run_id)
    if not test_run:
        raise ValueError(f"Test run {test_run_id} not found")
    
    # Get conversation logs
    logs = session.exec(
        select(ConversationLog).where(
            ConversationLog.test_run_id == test_run_id
        ).order_by(ConversationLog.id)
    ).all()
    
    # Calculate metrics
    total = len(logs)
    passed = sum(1 for l in logs if l.status == "pass")
    failed = total - passed
    pass_rate = (passed / total * 100) if total > 0 else 0
    
    scores = [l.overall_score for l in logs if l.overall_score]
    avg_score = sum(scores) / len(scores) if scores else 0
    
    latencies = [l.latency_ms for l in logs if l.latency_ms]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    
    # Build report
    report = f"""# Bot Test Report

**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Test Run ID:** {test_run_id}

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Status** | {test_run.status} |
| **Total Tests** | {total} |
| **Passed** | {passed} ✅ |
| **Failed** | {failed} ❌ |
| **Pass Rate** | {pass_rate:.1f}% |
| **Avg Score** | {avg_score:.2f}/10 |
| **Avg Latency** | {avg_latency:.0f}ms |

---

## Test Results

| # | Utterance | Status | Score | Category |
|---|-----------|--------|-------|----------|
"""
    
    for i, log in enumerate(logs, 1):
        status_icon = "✅" if log.status == "pass" else "❌"
        utterance = (log.utterance or "")[:40] + ("..." if len(log.utterance or "") > 40 else "")
        score = f"{log.overall_score:.1f}" if log.overall_score else "N/A"
        report += f"| {i} | {utterance} | {status_icon} | {score} | {log.category or 'N/A'} |\n"
    
    # Failed tests detail
    failed_logs = [l for l in logs if l.status == "fail"]
    if failed_logs:
        report += f"""
---

## Failed Tests Detail

"""
        for log in failed_logs:
            report += f"""### ❌ {log.utterance[:50]}...

- **Category:** {log.category or 'N/A'}
- **Bot Response:** {(log.bot_response or 'No response')[:200]}...
- **LLM Feedback:** {log.llm_feedback or 'No feedback'}

"""
    
    # Category breakdown
    categories = {}
    for log in logs:
        cat = log.category or "unknown"
        if cat not in categories:
            categories[cat] = {"total": 0, "passed": 0}
        categories[cat]["total"] += 1
        if log.status == "pass":
            categories[cat]["passed"] += 1
    
    if categories:
        report += """---

## Category Breakdown

| Category | Total | Passed | Pass Rate |
|----------|-------|--------|-----------|
"""
        for cat, stats in sorted(categories.items()):
            cat_rate = (stats["passed"] / stats["total"] * 100) if stats["total"] > 0 else 0
            report += f"| {cat} | {stats['total']} | {stats['passed']} | {cat_rate:.1f}% |\n"
    
    report += f"""
---

*Report generated by Bot UX Test Automation Platform*
"""
    
    return report


def save_report_to_file(content: str, filename: str, reports_dir: str = "reports") -> str:
    """
    Save report content to a file.
    
    Args:
        content: Report content
        filename: Output filename
        reports_dir: Directory to save reports
    
    Returns:
        Full path to saved file
    """
    # Create reports directory if needed
    os.makedirs(reports_dir, exist_ok=True)
    
    filepath = os.path.join(reports_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    
    return filepath


def get_report_summary(session: Session, test_run_id: int) -> dict:
    """
    Get a quick summary for report generation.
    
    Returns:
        Dictionary with summary stats
    """
    test_run = session.get(TestRun, test_run_id)
    if not test_run:
        return {"error": "Test run not found"}
    
    logs = session.exec(
        select(ConversationLog).where(
            ConversationLog.test_run_id == test_run_id
        )
    ).all()
    
    total = len(logs)
    passed = sum(1 for l in logs if l.status == "pass")
    
    return {
        "test_run_id": test_run_id,
        "status": test_run.status,
        "total_tests": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round((passed / total * 100) if total > 0 else 0, 1),
        "started_at": test_run.started_at.isoformat() if test_run.started_at else None,
        "completed_at": test_run.completed_at.isoformat() if test_run.completed_at else None,
    }
