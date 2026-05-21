"""Manage analysis history by scanning existing log files."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from tradingagents.reporting.compact_html_report import get_stock_name


def _results_dir() -> Path:
    return Path.home() / ".tradingagents" / "logs"


def _format_elapsed(seconds: float | None) -> str:
    """Format elapsed seconds into human-readable string."""
    if seconds is None or seconds <= 0:
        return "—"
    m, s = divmod(int(seconds), 60)
    if m > 0:
        return f"{m}分{s:02d}秒"
    return f"{s}秒"


def get_history(limit: int = 200) -> list[dict[str, Any]]:
    """Scan saved analysis logs and return a sorted list (newest first).

    Each entry: {
        "ticker": "300750",
        "name": "宁德时代",
        "date": "2026-05-12",
        "elapsed_seconds": 125.3,
        "elapsed_str": "2分05秒",
        "path": "/abs/path/...json"
    }
    Only the most recent *limit* entries are returned; older files are pruned.
    """
    root = _results_dir()
    if not root.exists():
        return []

    entries: list[dict[str, Any]] = []
    for log_file in root.rglob("full_states_log_*.json"):
        match = re.search(r"full_states_log_(\d{4}-\d{2}-\d{2})\.json$", log_file.name)
        if not match:
            continue
        date_str = match.group(1)
        ticker = log_file.parent.parent.name

        # Try to load elapsed_seconds and analysis_mode from the JSON
        elapsed_seconds = None
        analysis_mode = None
        try:
            with open(log_file, encoding="utf-8") as f:
                data = json.load(f)
            elapsed_seconds = data.get("elapsed_seconds")
            analysis_mode = data.get("analysis_mode")
        except Exception:
            pass

        name = get_stock_name(ticker) or ""
        entries.append({
            "ticker": ticker,
            "name": name,
            "date": date_str,
            "elapsed_seconds": elapsed_seconds,
            "elapsed_str": _format_elapsed(elapsed_seconds),
            "analysis_mode": analysis_mode or "—",
            "path": str(log_file),
        })

    # Sort newest first
    entries.sort(key=lambda e: e["date"], reverse=True)

    # Prune old entries beyond limit
    if len(entries) > limit:
        _prune_entries(entries[limit:])
        entries = entries[:limit]

    return entries


def _prune_entries(old_entries: list[dict[str, Any]]) -> None:
    """Delete log files and their parent directories for pruned entries."""
    for entry in old_entries:
        try:
            path = Path(entry["path"])
            if path.exists():
                path.unlink()
            # Remove empty parent directories (ticker/TradingAgentsStrategy_logs)
            parent = path.parent  # TradingAgentsStrategy_logs
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
            grandparent = parent.parent  # ticker dir
            if grandparent.exists() and not any(grandparent.iterdir()):
                grandparent.rmdir()
        except Exception:
            pass


def load_analysis(path: str) -> dict[str, Any]:
    """Load a saved analysis JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def extract_signal(state: dict[str, Any]) -> str:
    """Extract the short signal (Buy/Sell/Hold) from a final state dict."""
    import re

    for field in (
        "investment_plan",
        "trader_investment_decision",
        "final_trade_decision",
    ):
        text = state.get(field, "")
        if not text:
            continue
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        for keyword in ("BUY", "SELL", "HOLD"):
            if keyword in cleaned.upper():
                return keyword.capitalize()
    return "N/A"
