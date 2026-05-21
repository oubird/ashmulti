"""Persistent task metadata for resumable web analyses."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from tradingagents.dataflows.utils import safe_ticker_component
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.checkpointer import clear_checkpoint
from tradingagents.reporting.compact_html_report import _report_dir, _safe_filename


_TASKS_SUBDIR = "web_tasks"


def now_iso() -> str:
    """Return a local ISO timestamp."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _jsonable(value: Any) -> Any:
    """Best-effort conversion to JSON-serializable data."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def tasks_root() -> Path:
    """Return the root directory for web task records."""
    return Path.home() / ".tradingagents" / _TASKS_SUBDIR


def task_key(ticker: str, trade_date: str) -> str:
    """Return a human-readable stable key for a task."""
    return f"{safe_ticker_component(ticker).upper()}__{trade_date}"


def task_dir(ticker: str) -> Path:
    """Return the directory that stores records for a ticker."""
    return tasks_root() / safe_ticker_component(ticker).upper()


def task_path(ticker: str, trade_date: str) -> Path:
    """Return the JSON file path for a task."""
    return task_dir(ticker) / f"{trade_date}.json"


def full_log_path(ticker: str, trade_date: str, config: dict[str, Any] | None = None) -> Path:
    """Return the canonical full-state log path for a task."""
    cfg = config or {}
    results_dir = Path(cfg.get("results_dir", DEFAULT_CONFIG["results_dir"]))
    return results_dir / safe_ticker_component(ticker) / "TradingAgentsStrategy_logs" / f"full_states_log_{trade_date}.json"


def _atomic_write(path: Path, data: str) -> None:
    """Write text atomically to avoid partial JSON records."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)


def save_task_record(record: dict[str, Any]) -> Path:
    """Persist a task record to disk and return its file path."""
    ticker = record["ticker"]
    trade_date = record["trade_date"]
    path = task_path(ticker, trade_date)
    payload = dict(record)
    payload["task_key"] = task_key(ticker, trade_date)
    payload["task_path"] = str(path)
    payload["updated_at"] = now_iso()
    _atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return path


def load_task_record_by_path(path: str | Path) -> dict[str, Any] | None:
    """Load a task record from an explicit JSON file path."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        with p.open(encoding="utf-8") as f:
            record = json.load(f)
        if isinstance(record, dict):
            record.setdefault("task_path", str(p))
            record.setdefault("task_key", task_key(record.get("ticker", p.parent.name), record.get("trade_date", p.stem)))
            return record
    except Exception:
        return None
    return None


def load_task_record(ticker: str, trade_date: str) -> dict[str, Any] | None:
    """Load the task record for a ticker+date pair."""
    return load_task_record_by_path(task_path(ticker, trade_date))


def list_task_records() -> list[dict[str, Any]]:
    """Return all persisted task records."""
    root = tasks_root()
    if not root.exists():
        return []

    records: list[dict[str, Any]] = []
    for path in root.rglob("*.json"):
        record = load_task_record_by_path(path)
        if record:
            records.append(record)
    return records


def _prune_empty_parents(path: Path, stop_at: Path) -> None:
    """Remove empty parent folders up to but not including stop_at."""
    current = path.parent
    while current != stop_at and current.exists():
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _candidate_report_paths(record: dict[str, Any]) -> Iterable[Path]:
    """Yield possible compact/risk report files for a task."""
    ticker = _safe_filename(record["ticker"])
    trade_date = record["trade_date"]
    stock_name = record.get("stock_name") or ""
    report_dir = _report_dir()

    if stock_name:
        safe_name = _safe_filename(stock_name)
        yield report_dir / f"{ticker}_{safe_name}_{trade_date}.html"
        yield report_dir / f"{ticker}_{safe_name}_risk_{trade_date}.html"

    # Fallback to broad globbing so older records without stock_name still delete cleanly.
    yield from report_dir.glob(f"{ticker}_*_{trade_date}.html")
    yield from report_dir.glob(f"{ticker}_*_risk_{trade_date}.html")


def delete_task_artifacts(record: dict[str, Any]) -> None:
    """Delete the task record and all generated artifacts for one task."""
    ticker = record["ticker"]
    trade_date = record["trade_date"]
    config = record.get("config") if isinstance(record.get("config"), dict) else {}

    # Remove resumable checkpoint data first so a deleted row cannot be resumed.
    try:
        clear_checkpoint(config.get("data_cache_dir", DEFAULT_CONFIG["data_cache_dir"]), ticker, trade_date)
    except Exception:
        pass

    # Remove the full-state log.
    log_path = record.get("final_state_path")
    candidates = [Path(log_path)] if log_path else []
    candidates.append(full_log_path(ticker, trade_date, config))
    for path in candidates:
        try:
            p = Path(path)
            if p.exists():
                p.unlink()
                _prune_empty_parents(p, Path(config.get("results_dir", DEFAULT_CONFIG["results_dir"])))
        except Exception:
            pass

    # Remove generated HTML artifacts.
    for path in _candidate_report_paths(record):
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass

    # Remove the task record itself.
    path = Path(record.get("task_path") or task_path(ticker, trade_date))
    try:
        if path.exists():
            path.unlink()
            _prune_empty_parents(path, tasks_root())
    except Exception:
        pass


def build_resume_config(record: dict[str, Any]) -> dict[str, Any]:
    """Rebuild a runnable config snapshot from a task record."""
    config = dict(DEFAULT_CONFIG)
    saved = record.get("config")
    if isinstance(saved, dict):
        config.update(_jsonable(saved))
    config["checkpoint_enabled"] = True
    return config


def analysis_mode_label(config: dict[str, Any]) -> str:
    """Map debate depth to a readable label."""
    depth = config.get("max_debate_rounds", 5)
    return {1: "快速", 3: "中等", 5: "深度"}.get(depth, "深度")


def snapshot_tracker(tracker: Any) -> dict[str, Any]:
    """Serialize the current tracker state for persistence."""
    return {
        "current_stage": getattr(tracker, "current_stage", ""),
        "completed_stages": list(getattr(tracker, "completed_stages", [])),
        "stage_reports": dict(getattr(tracker, "stage_reports", {})),
        "is_running": bool(getattr(tracker, "is_running", False)),
        "is_complete": bool(getattr(tracker, "is_complete", False)),
        "error": getattr(tracker, "error", None),
        "signal": getattr(tracker, "signal", ""),
        "llm_calls": int(getattr(tracker, "llm_calls", 0)),
        "tool_calls": int(getattr(tracker, "tool_calls", 0)),
        "tokens_in": int(getattr(tracker, "tokens_in", 0)),
        "tokens_out": int(getattr(tracker, "tokens_out", 0)),
        "elapsed_seconds": float(getattr(tracker, "elapsed", 0.0)),
    }


def apply_task_snapshot(tracker: Any, record: dict[str, Any]) -> Any:
    """Restore progress fields from a saved task record into a live tracker."""
    tracker.current_stage = record.get("current_stage", "")
    tracker.completed_stages = list(record.get("completed_stages", []))
    tracker.stage_reports = dict(record.get("stage_reports", {}))
    tracker.error = record.get("error") or None
    tracker.postprocess_error = record.get("report_error") or None
    tracker.signal = record.get("signal", "")
    tracker.llm_calls = int(record.get("llm_calls", 0))
    tracker.tool_calls = int(record.get("tool_calls", 0))
    tracker.tokens_in = int(record.get("tokens_in", 0))
    tracker.tokens_out = int(record.get("tokens_out", 0))
    return tracker


def create_task_record(
    ticker: str,
    trade_date: str,
    config: dict[str, Any],
    selected_analysts: list[str],
    *,
    stock_name: str = "",
) -> dict[str, Any]:
    """Build a fresh task record ready to persist."""
    cfg = _jsonable(config)
    return {
        "ticker": ticker,
        "trade_date": trade_date,
        "task_key": task_key(ticker, trade_date),
        "task_path": str(task_path(ticker, trade_date)),
        "stock_name": stock_name or "",
        "analysis_mode": analysis_mode_label(cfg),
        "selected_analysts": list(selected_analysts),
        "config": cfg,
        "status": "running",
        "analysis_complete": False,
        "report_complete": False,
        "delete_requested": False,
        "error": "",
        "report_error": "",
        "current_stage": "",
        "completed_stages": [],
        "stage_reports": {},
        "is_running": True,
        "is_complete": False,
        "signal": "",
        "llm_calls": 0,
        "tool_calls": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "elapsed_seconds": 0.0,
        "started_at": now_iso(),
        "updated_at": now_iso(),
    }


def merge_task_record(record: dict[str, Any], **updates: Any) -> dict[str, Any]:
    """Return a copy of record with updates applied."""
    merged = dict(record)
    merged.update(updates)
    merged["updated_at"] = now_iso()
    return merged


def display_status(record: dict[str, Any]) -> str:
    """Return the Chinese status label shown in history."""
    status = record.get("status", "interrupted")
    analysis_complete = bool(record.get("analysis_complete"))
    report_complete = bool(record.get("report_complete"))
    if status == "deleted":
        return "已删除"
    if analysis_complete and report_complete:
        return "完成"
    if analysis_complete or status == "recoverable" or record.get("report_error"):
        return "可恢复"
    if status == "running":
        return "进行中"
    return "中断"


def can_continue(record: dict[str, Any]) -> bool:
    """Return whether the task should expose a Continue button."""
    return continue_mode(record) != "none"


def continue_mode(record: dict[str, Any]) -> str:
    """Return how Continue should behave: resume, repair, or none."""
    status = record.get("status", "interrupted")
    if status == "deleted":
        return "none"
    if bool(record.get("analysis_complete")):
        return "repair" if not bool(record.get("report_complete")) else "none"
    if status == "running":
        return "none"
    if status == "interrupted":
        return "resume"
    if status == "recoverable":
        return "repair"
    if status == "completed":
        return "repair" if not bool(record.get("report_complete")) else "none"
    return "none"


def view_mode(record: dict[str, Any]) -> str:
    """Return 'report' for completed reports or 'task' for a task detail page."""
    if bool(record.get("analysis_complete")) and bool(record.get("report_complete")):
        return "report"
    return "task"
