"""
Analytics Module - Sentiment Trend Analysis

Track quality metrics over time to detect regressions and trends.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from sqlmodel import Session, select, func
from models import ConversationLog, TestRun


@dataclass
class DailyMetrics:
    """Daily aggregated metrics."""
    date: str
    total_tests: int
    pass_count: int
    fail_count: int
    pass_rate: float
    avg_score: float
    avg_latency_ms: float
    categories_tested: List[str]


@dataclass
class TrendAnalysis:
    """Trend analysis results."""
    period_days: int
    current_pass_rate: float
    previous_pass_rate: float
    pass_rate_change: float  # Positive = improvement
    current_avg_score: float
    previous_avg_score: float
    score_change: float
    trend: str  # "improving", "declining", "stable"
    insights: List[str]


@dataclass
class CategoryBreakdown:
    """Performance breakdown by category."""
    category: str
    total_tests: int
    pass_count: int
    pass_rate: float
    avg_score: float
    avg_latency_ms: float
    common_issues: List[str]


def get_daily_metrics(session: Session, days: int = 7) -> List[DailyMetrics]:
    """
    Get daily aggregated metrics for the last N days.
    
    Args:
        session: Database session
        days: Number of days to retrieve
    
    Returns:
        List of DailyMetrics, one per day
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # Get all logs in date range
    statement = select(ConversationLog).where(
        ConversationLog.timestamp >= start_date
    ).order_by(ConversationLog.timestamp)
    
    logs = session.exec(statement).all()
    
    # Group by date
    daily_data: Dict[str, List[ConversationLog]] = {}
    for log in logs:
        date_str = log.timestamp.strftime("%Y-%m-%d") if log.timestamp else "unknown"
        if date_str not in daily_data:
            daily_data[date_str] = []
        daily_data[date_str].append(log)
    
    # Calculate metrics for each day
    metrics = []
    for date_str in sorted(daily_data.keys()):
        day_logs = daily_data[date_str]
        
        total = len(day_logs)
        passed = sum(1 for l in day_logs if l.status == "pass")
        failed = sum(1 for l in day_logs if l.status == "fail")
        pass_rate = (passed / total * 100) if total > 0 else 0
        
        scores = [l.overall_score for l in day_logs if l.overall_score]
        avg_score = sum(scores) / len(scores) if scores else 0
        
        latencies = [l.latency_ms for l in day_logs if l.latency_ms]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        
        categories = list(set(l.category for l in day_logs if l.category))
        
        metrics.append(DailyMetrics(
            date=date_str,
            total_tests=total,
            pass_count=passed,
            fail_count=failed,
            pass_rate=round(pass_rate, 1),
            avg_score=round(avg_score, 2),
            avg_latency_ms=round(avg_latency, 0),
            categories_tested=categories
        ))
    
    return metrics


def analyze_trends(session: Session, period_days: int = 7) -> TrendAnalysis:
    """
    Analyze trends comparing current period to previous period.
    
    Args:
        session: Database session
        period_days: Days in each comparison period
    
    Returns:
        TrendAnalysis with insights
    """
    now = datetime.now()
    current_start = now - timedelta(days=period_days)
    previous_start = current_start - timedelta(days=period_days)
    
    # Get current period logs
    current_logs = session.exec(
        select(ConversationLog).where(
            ConversationLog.timestamp >= current_start
        )
    ).all()
    
    # Get previous period logs
    previous_logs = session.exec(
        select(ConversationLog).where(
            ConversationLog.timestamp >= previous_start,
            ConversationLog.timestamp < current_start
        )
    ).all()
    
    # Calculate current metrics
    current_total = len(current_logs)
    current_passed = sum(1 for l in current_logs if l.status == "pass")
    current_pass_rate = (current_passed / current_total * 100) if current_total > 0 else 0
    current_scores = [l.overall_score for l in current_logs if l.overall_score]
    current_avg_score = sum(current_scores) / len(current_scores) if current_scores else 0
    
    # Calculate previous metrics
    previous_total = len(previous_logs)
    previous_passed = sum(1 for l in previous_logs if l.status == "pass")
    previous_pass_rate = (previous_passed / previous_total * 100) if previous_total > 0 else 0
    previous_scores = [l.overall_score for l in previous_logs if l.overall_score]
    previous_avg_score = sum(previous_scores) / len(previous_scores) if previous_scores else 0
    
    # Calculate changes
    pass_rate_change = current_pass_rate - previous_pass_rate
    score_change = current_avg_score - previous_avg_score
    
    # Determine trend
    if pass_rate_change > 5 or score_change > 0.5:
        trend = "improving"
    elif pass_rate_change < -5 or score_change < -0.5:
        trend = "declining"
    else:
        trend = "stable"
    
    # Generate insights
    insights = []
    if trend == "improving":
        insights.append(f"Pass rate improved by {pass_rate_change:.1f}% this period")
    elif trend == "declining":
        insights.append(f"Pass rate declined by {abs(pass_rate_change):.1f}% - investigate recent failures")
    
    if current_total < previous_total * 0.5:
        insights.append("Warning: Significantly fewer tests run this period")
    
    # Find problematic categories
    category_failures = {}
    for log in current_logs:
        if log.status == "fail" and log.category:
            category_failures[log.category] = category_failures.get(log.category, 0) + 1
    
    if category_failures:
        worst_category = max(category_failures, key=category_failures.get)
        insights.append(f"Most failures in '{worst_category}' category ({category_failures[worst_category]} failures)")
    
    return TrendAnalysis(
        period_days=period_days,
        current_pass_rate=round(current_pass_rate, 1),
        previous_pass_rate=round(previous_pass_rate, 1),
        pass_rate_change=round(pass_rate_change, 1),
        current_avg_score=round(current_avg_score, 2),
        previous_avg_score=round(previous_avg_score, 2),
        score_change=round(score_change, 2),
        trend=trend,
        insights=insights
    )


def get_category_breakdown(session: Session, days: int = 30) -> List[CategoryBreakdown]:
    """
    Get performance breakdown by category.
    
    Args:
        session: Database session
        days: Number of days to analyze
    
    Returns:
        List of CategoryBreakdown, one per category
    """
    start_date = datetime.now() - timedelta(days=days)
    
    logs = session.exec(
        select(ConversationLog).where(
            ConversationLog.timestamp >= start_date
        )
    ).all()
    
    # Group by category
    by_category: Dict[str, List[ConversationLog]] = {}
    for log in logs:
        cat = log.category or "unknown"
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(log)
    
    # Calculate metrics per category
    breakdowns = []
    for category, cat_logs in by_category.items():
        total = len(cat_logs)
        passed = sum(1 for l in cat_logs if l.status == "pass")
        pass_rate = (passed / total * 100) if total > 0 else 0
        
        scores = [l.overall_score for l in cat_logs if l.overall_score]
        avg_score = sum(scores) / len(scores) if scores else 0
        
        latencies = [l.latency_ms for l in cat_logs if l.latency_ms]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        
        # Find common issues (from LLM feedback)
        issues = []
        for log in cat_logs:
            if log.status == "fail" and log.llm_feedback:
                if len(issues) < 3 and log.llm_feedback not in issues:
                    issues.append(log.llm_feedback[:100])
        
        breakdowns.append(CategoryBreakdown(
            category=category,
            total_tests=total,
            pass_count=passed,
            pass_rate=round(pass_rate, 1),
            avg_score=round(avg_score, 2),
            avg_latency_ms=round(avg_latency, 0),
            common_issues=issues
        ))
    
    # Sort by total tests descending
    breakdowns.sort(key=lambda x: x.total_tests, reverse=True)
    
    return breakdowns


def get_quality_stats(session: Session) -> Dict:
    """
    Get overall quality statistics.
    
    Returns:
        Dictionary with comprehensive quality stats
    """
    # All-time stats
    all_logs = session.exec(select(ConversationLog)).all()
    all_runs = session.exec(select(TestRun)).all()
    
    total_tests = len(all_logs)
    total_runs = len(all_runs)
    
    passed = sum(1 for l in all_logs if l.status == "pass")
    failed = sum(1 for l in all_logs if l.status == "fail")
    
    scores = [l.overall_score for l in all_logs if l.overall_score]
    avg_score = sum(scores) / len(scores) if scores else 0
    
    latencies = [l.latency_ms for l in all_logs if l.latency_ms and l.latency_ms > 0]
    
    return {
        "all_time": {
            "total_tests": total_tests,
            "total_runs": total_runs,
            "pass_rate": round((passed / total_tests * 100) if total_tests > 0 else 0, 1),
            "avg_score": round(avg_score, 2),
            "avg_latency_ms": round(sum(latencies) / len(latencies) if latencies else 0, 0),
            "min_latency_ms": min(latencies) if latencies else 0,
            "max_latency_ms": max(latencies) if latencies else 0,
        },
        "last_7_days": analyze_trends(session, 7).__dict__,
        "categories": len(set(l.category for l in all_logs if l.category)),
    }
