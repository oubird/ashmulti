"""Manage analysis history by scanning existing log files."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tradingagents.reporting.compact_html_report import _get_code_to_name_map, _report_dir, _safe_filename

from web.task_store import (
    can_continue,
    continue_mode,
    legacy_cli_message_log_path,
    legacy_cli_report_dir,
    legacy_logs_root,
    display_status,
    list_task_records,
    load_legacy_cli_final_state,
    task_key,
    view_mode,
)


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


def _report_files_exist(ticker: str, trade_date: str, stock_name: str = "") -> tuple[bool, bool, str, str]:
    """Return whether the compact/risk reports exist, plus their file paths."""
    report_dir = _report_dir()
    safe_ticker = _safe_filename(ticker)

    compact_candidates: list[Path] = []
    risk_candidates: list[Path] = []
    if stock_name:
        safe_name = _safe_filename(stock_name)
        compact_candidates.append(report_dir / f"{safe_ticker}_{safe_name}_{trade_date}.html")
        risk_candidates.append(report_dir / f"{safe_ticker}_{safe_name}_risk_{trade_date}.html")

    compact_candidates.extend(
        p for p in report_dir.glob(f"{safe_ticker}_*_{trade_date}.html") if "_risk_" not in p.stem
    )
    risk_candidates.extend(report_dir.glob(f"{safe_ticker}_*_risk_{trade_date}.html"))

    compact = next((p for p in compact_candidates if p.exists()), None)
    risk = next((p for p in risk_candidates if p.exists()), None)
    return bool(compact), bool(risk), str(compact) if compact else "", str(risk) if risk else ""


def _legacy_cli_report_paths(ticker: str, trade_date: str) -> tuple[Path, Path]:
    """Return the legacy CLI complete report and report directory paths."""
    report_dir = legacy_cli_report_dir(ticker, trade_date)
    return report_dir / "complete_report.md", report_dir


def _legacy_cli_artifacts_exist(ticker: str, trade_date: str) -> bool:
    """Return whether legacy CLI markdown artifacts exist for a task."""
    report_dir = legacy_cli_report_dir(ticker, trade_date)
    return report_dir.exists() and any(report_dir.glob("*.md"))


def _parse_log_entry(log_file: Path, c2n: dict[str, str] | None) -> dict[str, Any] | None:
    """Convert one full-state log file into a normalized history entry."""
    match = re.search(r"full_states_log_(\d{4}-\d{2}-\d{2})\.json$", log_file.name)
    if not match:
        return None

    trade_date = match.group(1)
    ticker = log_file.parent.parent.name
    try:
        with log_file.open(encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None

    stock_name = data.get("stock_name") or ""
    name = stock_name or ""
    if not name and c2n is not None:
        name = c2n.get(ticker, "")

    compact_ok, risk_ok, compact_path, risk_path = _report_files_exist(ticker, trade_date, stock_name)
    report_complete = compact_ok and risk_ok
    base = {
        "ticker": ticker,
        "name": name,
        "date": trade_date,
        "trade_date": trade_date,
        "elapsed_seconds": data.get("elapsed_seconds"),
        "elapsed_str": _format_elapsed(data.get("elapsed_seconds")),
        "analysis_mode": data.get("analysis_mode") or "—",
        "stock_name": stock_name or name,
        "analysis_complete": True,
        "report_complete": report_complete,
        "status": "completed" if report_complete else "recoverable",
        "error": "",
        "report_error": "",
        "current_stage": "",
        "completed_stages": [],
        "view_mode": "report" if report_complete else "task",
        "view_path": str(log_file),
        "path": str(log_file),
        "log_path": str(log_file),
        "task_path": str(
            Path.home()
            / ".tradingagents"
            / "web_tasks"
            / safe_ticker_component_for_path(ticker).upper()
            / f"{trade_date}.json"
        ),
        "report_path": compact_path,
        "risk_report_path": risk_path,
        "continue_mode": "repair" if not report_complete else "none",
        "can_continue": not report_complete,
        "source": "log",
        "task_record_present": False,
        "sort_ts": log_file.stat().st_mtime,
    }
    base["status_label"] = display_status(base)
    return base


def _parse_legacy_cli_entry(ticker: str, trade_date: str, c2n: dict[str, str] | None) -> dict[str, Any] | None:
    """Convert legacy CLI markdown artifacts into a normalized history entry."""
    if not _legacy_cli_artifacts_exist(ticker, trade_date):
        return None

    final_state = load_legacy_cli_final_state(ticker, trade_date)
    if not final_state:
        return None

    stock_name = final_state.get("stock_name") or ""
    if not stock_name and c2n is not None:
        stock_name = c2n.get(ticker, "")

    compact_ok, risk_ok, compact_path, risk_path = _report_files_exist(ticker, trade_date, stock_name)
    complete_report, report_dir = _legacy_cli_report_paths(ticker, trade_date)
    if not compact_ok and complete_report.exists():
        compact_path = str(complete_report)
        compact_ok = True

    report_complete = bool(compact_ok and risk_ok)
    sort_ts = max((p.stat().st_mtime for p in report_dir.glob("*.md")), default=report_dir.stat().st_mtime if report_dir.exists() else 0.0)
    html_report = _report_dir() / f"{_safe_filename(ticker)}_{_safe_filename(stock_name or 'unknown')}_{trade_date}.html"
    risk_report = _report_dir() / f"{_safe_filename(ticker)}_{_safe_filename(stock_name or 'unknown')}_risk_{trade_date}.html"

    entry = {
        "ticker": ticker,
        "name": stock_name or "",
        "date": trade_date,
        "trade_date": trade_date,
        "elapsed_seconds": final_state.get("elapsed_seconds"),
        "elapsed_str": _format_elapsed(final_state.get("elapsed_seconds")),
        "analysis_mode": final_state.get("analysis_mode") or "—",
        "stock_name": stock_name or "",
        "analysis_complete": True,
        "report_complete": report_complete,
        "status": "completed" if report_complete else "recoverable",
        "error": "",
        "report_error": "",
        "current_stage": "",
        "completed_stages": [],
        "view_mode": "report" if report_complete else "task",
        "view_path": str(html_report if html_report.exists() else complete_report if complete_report.exists() else report_dir),
        "path": str(html_report if html_report.exists() else complete_report if complete_report.exists() else report_dir),
        "log_path": str(legacy_cli_message_log_path(ticker, trade_date)),
        "task_path": "",
        "report_path": str(html_report if html_report.exists() else complete_report if complete_report.exists() else compact_path),
        "risk_report_path": str(risk_report if risk_report.exists() else risk_path),
        "continue_mode": "repair" if not report_complete else "none",
        "can_continue": not report_complete,
        "source": "legacy_cli",
        "task_record_present": False,
        "legacy_cli": True,
        "sort_ts": sort_ts,
    }
    entry["status_label"] = display_status(entry)
    return entry


def safe_ticker_component_for_path(ticker: str) -> str:
    """Import-safe wrapper used to avoid a cyclic import in module globals."""
    from tradingagents.dataflows.utils import safe_ticker_component

    return safe_ticker_component(ticker)


def _merge_record_and_log(
    record: dict[str, Any],
    log_entry: dict[str, Any] | None,
    c2n: dict[str, str] | None,
) -> dict[str, Any]:
    """Merge task record metadata and log metadata into one row."""
    ticker = record["ticker"]
    trade_date = record["trade_date"]
    stock_name = record.get("stock_name") or ""
    log_path = str(_results_dir() / safe_ticker_component_for_path(ticker) / "TradingAgentsStrategy_logs" / f"full_states_log_{trade_date}.json")
    compact_ok, risk_ok, compact_path, risk_path = _report_files_exist(ticker, trade_date, stock_name)

    merged = dict(record)
    merged["date"] = merged.get("trade_date") or merged.get("date") or trade_date
    merged["trade_date"] = merged.get("trade_date") or trade_date
    if log_entry:
        if merged.get("elapsed_seconds") in (None, "", 0, 0.0):
            merged["elapsed_seconds"] = log_entry.get("elapsed_seconds")
        if merged.get("analysis_mode") in (None, "", "—"):
            merged["analysis_mode"] = log_entry.get("analysis_mode")
        merged["analysis_complete"] = True
        merged["log_path"] = log_entry.get("log_path", log_path)
        merged["path"] = log_entry.get("path", log_path)
        merged["view_path"] = log_entry.get("path", log_path)
        if not merged.get("stock_name"):
            merged["stock_name"] = log_entry.get("stock_name", "")
        if not merged.get("name"):
            merged["name"] = log_entry.get("name", "")

    name = merged.get("stock_name") or merged.get("name") or ""
    if not name and c2n is not None:
        name = c2n.get(ticker, "")
    merged["name"] = name

    merged["analysis_complete"] = bool(merged.get("analysis_complete")) or bool(log_entry)
    merged["report_complete"] = bool(compact_ok and risk_ok)
    if merged["analysis_complete"] and merged["report_complete"]:
        merged["status"] = "completed"
    elif merged["analysis_complete"]:
        merged["status"] = "recoverable"
    elif merged.get("status") not in {"running", "interrupted", "recoverable"}:
        merged["status"] = "interrupted"

    merged["elapsed_seconds"] = merged.get("elapsed_seconds")
    merged["elapsed_str"] = _format_elapsed(merged.get("elapsed_seconds"))
    merged["analysis_mode"] = merged.get("analysis_mode") or "—"
    merged["report_path"] = compact_path
    merged["risk_report_path"] = risk_path
    merged["view_mode"] = view_mode(merged)
    merged["continue_mode"] = continue_mode(merged)
    merged["can_continue"] = can_continue(merged)
    merged["status_label"] = display_status(merged)
    if merged["view_mode"] == "report":
        merged["view_path"] = merged.get("log_path") or merged.get("path") or log_path
    else:
        task_file = Path(str(merged.get("task_path") or ""))
        if task_file.exists():
            merged["view_path"] = str(task_file)
        else:
            merged["view_path"] = merged.get("log_path") or merged.get("path") or log_path

    sort_candidates = []
    if merged.get("task_path"):
        p = Path(merged["task_path"])
        if p.exists():
            sort_candidates.append(p.stat().st_mtime)
    if merged.get("log_path"):
        p = Path(merged["log_path"])
        if p.exists():
            sort_candidates.append(p.stat().st_mtime)
    if log_entry:
        sort_candidates.append(log_entry.get("sort_ts", 0.0))
    merged["sort_ts"] = max(sort_candidates) if sort_candidates else 0.0
    return merged


def _load_task_rows(c2n: dict[str, str] | None) -> dict[str, dict[str, Any]]:
    """Load task records and merge them with any log entries."""
    rows: dict[str, dict[str, Any]] = {}
    deleted_keys: set[str] = set()
    for record in list_task_records():
        if record.get("status") == "deleted" or record.get("delete_requested"):
            ticker = record.get("ticker", "")
            trade_date = record.get("trade_date", "")
            if ticker and trade_date:
                deleted_keys.add(task_key(ticker, trade_date))
            continue
        ticker = record.get("ticker", "")
        trade_date = record.get("trade_date", "")
        if not ticker or not trade_date:
            continue
        key = task_key(ticker, trade_date)
        rows[key] = _merge_record_and_log(record, None, c2n)

    root = _results_dir()
    if root.exists():
        for log_file in root.rglob("full_states_log_*.json"):
            log_entry = _parse_log_entry(log_file, c2n)
            if not log_entry:
                continue
            key = task_key(log_entry["ticker"], log_entry["date"])
            if key in deleted_keys:
                continue
            existing = rows.get(key)
            if existing:
                rows[key] = _merge_record_and_log(existing, log_entry, c2n)
            else:
                rows[key] = log_entry

    legacy_root = legacy_logs_root()
    if legacy_root.exists():
        for ticker_dir in legacy_root.iterdir():
            if not ticker_dir.is_dir():
                continue
            ticker = ticker_dir.name
            legacy_message = ticker_dir / "message_tool.log"
            if legacy_message.exists():
                # Legacy CLI root can also contain the flat message log; keep it for view-only fallbacks.
                pass
            for report_dir in ticker_dir.iterdir():
                if not report_dir.is_dir():
                    continue
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", report_dir.name):
                    continue
                trade_date = report_dir.name
                key = task_key(ticker, trade_date)
                if key in deleted_keys:
                    continue
                if key in rows and rows[key].get("source") != "legacy_cli":
                    continue
                legacy_entry = _parse_legacy_cli_entry(ticker, trade_date, c2n)
                if legacy_entry:
                    rows[key] = legacy_entry

    return rows


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
    c2n: dict[str, str] | None = None  # lazy-loaded name map

    if c2n is None:
        c2n = _get_code_to_name_map()

    entries = list(_load_task_rows(c2n).values())
    entries.sort(key=lambda e: (e.get("sort_ts", 0.0), e.get("date", "")), reverse=True)

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
            if path.name and not path.name.startswith("full_states_log_"):
                continue
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


def load_task_detail(path: str) -> dict[str, Any]:
    """Load either a task record or a full-state log for the detail page."""
    return load_analysis(path)


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
