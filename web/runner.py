"""Background thread runner for TradingAgentsGraph pipeline."""

from __future__ import annotations

import logging
import re
import threading
from pathlib import Path
from typing import Any

from tradingagents.graph.checkpointer import checkpoint_step, clear_checkpoint, get_checkpointer, thread_id
from tradingagents.reporting.compact_html_report import (
    generate_compact_html_report,
    get_stock_name,
    save_compact_html_report,
)
from tradingagents.reporting.risk_html_report import (
    generate_risk_html_report,
    save_risk_html_report,
)
from web.progress import PIPELINE_STAGES, ProgressTracker
from web.task_store import (
    apply_task_snapshot,
    build_resume_config,
    create_task_record,
    delete_task_artifacts,
    full_log_path,
    load_legacy_cli_final_state,
    load_task_record_by_path,
    merge_task_record,
    save_task_record,
    snapshot_tracker,
)


logger = logging.getLogger(__name__)


_REPORT_KEY_TO_STAGE = {s["report_key"]: s["id"] for s in PIPELINE_STAGES}

_ANALYST_REPORT_KEYS = [
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
    "policy_report",
    "hot_money_report",
    "lockup_report",
]

# Per-task registry so multiple users can run concurrently.
# task_key -> {"tracker": ProgressTracker, "thread": Thread, "stop_event": Event, "user_id": str}
_RUN_REGISTRY: dict[str, dict] = {}
_REGISTRY_LOCK = threading.Lock()


def _task_key(ticker: str, trade_date: str) -> str:
    from web.task_store import task_key as _tk
    return _tk(ticker, trade_date)


def get_active_tracker(task_key: str | None = None, user_id: str = "") -> ProgressTracker | None:
    """Return a tracker by task_key, or the first running tracker for a user."""
    with _REGISTRY_LOCK:
        if task_key and task_key in _RUN_REGISTRY:
            return _RUN_REGISTRY[task_key]["tracker"]
        if user_id:
            for ctx in _RUN_REGISTRY.values():
                if ctx.get("user_id") == user_id:
                    return ctx["tracker"]
        return None


def request_stop(task_key: str | None = None) -> None:
    """Signal the background runner to stop at the next chunk boundary."""
    with _REGISTRY_LOCK:
        if task_key and task_key in _RUN_REGISTRY:
            _RUN_REGISTRY[task_key]["stop_event"].set()


def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks from LLM output."""
    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()


def _extract_content_string(content: Any) -> str | None:
    """Extract string content from various message formats."""
    if content is None or content == "":
        return None
    if isinstance(content, str):
        s = content.strip()
        return s if s else None
    if isinstance(content, dict):
        text = content.get("text", "")
        return text.strip() if text else None
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                t = item.get("text", "").strip()
                if t:
                    parts.append(t)
            elif isinstance(item, str):
                t = item.strip()
                if t:
                    parts.append(t)
        result = " ".join(parts)
        return result if result else None
    s = str(content).strip()
    return s if s else None


def _classify_message(message: Any) -> tuple[str, str | None]:
    """Classify a LangChain message into (type, content)."""
    try:
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    except ImportError:
        return ("System", _extract_content_string(getattr(message, "content", None)))

    content = _extract_content_string(getattr(message, "content", None))

    if isinstance(message, HumanMessage):
        if content and content.strip() == "Continue":
            return ("Control", content)
        return ("User", content)

    if isinstance(message, ToolMessage):
        return ("Data", content)

    if isinstance(message, AIMessage):
        return ("Agent", content)

    return ("System", content)


def _detect_completed_stages(
    chunk: dict[str, Any],
    tracker: ProgressTracker,
) -> None:
    """Check the streamed chunk for newly completed stages."""
    for report_key in _ANALYST_REPORT_KEYS:
        stage_id = _REPORT_KEY_TO_STAGE[report_key]
        content = chunk.get(report_key, "")
        if content and tracker.stage_status(stage_id) != "done":
            tracker.mark_stage_done(stage_id, _strip_think_tags(str(content)))

    dqs = chunk.get("data_quality_summary", "")
    if dqs and tracker.stage_status("quality_gate") != "done":
        tracker.mark_stage_done("quality_gate", str(dqs))

    debate = chunk.get("investment_debate_state")
    if debate and isinstance(debate, dict):
        judge = debate.get("judge_decision", "")
        if judge and tracker.stage_status("debate") != "done":
            tracker.mark_stage_done("debate", str(judge))

    trader_plan = chunk.get("trader_investment_plan", "")
    if trader_plan and tracker.stage_status("trader") != "done":
        tracker.mark_stage_done("trader", _strip_think_tags(str(trader_plan)))

    risk = chunk.get("risk_debate_state")
    if risk and isinstance(risk, dict):
        risk_judge = risk.get("judge_decision", "")
        if risk_judge and tracker.stage_status("risk") != "done":
            tracker.mark_stage_done("risk", str(risk_judge))

    final = chunk.get("final_trade_decision", "")
    if final and tracker.stage_status("pm") != "done":
        tracker.mark_stage_done("pm", _strip_think_tags(str(final)))


def _infer_active_stage(tracker: ProgressTracker) -> None:
    """Set the current_stage to the first non-completed stage."""
    from web.progress import STAGE_IDS

    for sid in STAGE_IDS:
        if tracker.stage_status(sid) == "pending":
            tracker.mark_stage_active(sid)
            return


def _capture_messages(chunk: dict[str, Any], tracker: ProgressTracker) -> None:
    """Extract messages and tool calls from a streamed chunk."""
    messages = chunk.get("messages", [])
    if not messages:
        return

    for message in messages:
        msg_type, content = _classify_message(message)
        if content and content.strip():
            tracker.add_message(msg_type, content.strip())

        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            for tc in tool_calls:
                if isinstance(tc, dict):
                    tracker.add_tool_call(tc.get("name", "unknown"), tc.get("args", {}))
                else:
                    tracker.add_tool_call(getattr(tc, "name", "unknown"), getattr(tc, "args", {}))


def _persist_task_record(
    record: dict[str, Any],
    tracker: ProgressTracker,
    **updates: Any,
) -> dict[str, Any]:
    """Merge tracker state into the record and persist it."""
    merged_updates = snapshot_tracker(tracker)
    merged_updates.update(updates)
    merged = merge_task_record(record, **merged_updates)
    save_task_record(merged)
    return merged


def _refresh_task_record(record: dict[str, Any] | None) -> dict[str, Any] | None:
    """Reload a task record from disk so delete flags are seen quickly."""
    if not record:
        return None
    task_path = record.get("task_path")
    if not task_path:
        return record
    disk_record = load_task_record_by_path(task_path)
    if isinstance(disk_record, dict):
        return disk_record
    return record


def _build_runtime_config(
    config: dict[str, Any],
    existing_record: dict[str, Any] | None,
    repair_only: bool,
) -> dict[str, Any]:
    """Return the config used for the current run."""
    if existing_record and not repair_only:
        runtime_config = build_resume_config(existing_record)
    else:
        runtime_config = dict(config)
        runtime_config["checkpoint_enabled"] = True
    runtime_config["checkpoint_enabled"] = True
    return runtime_config


def _initial_selected_analysts(
    selected_analysts: list[str],
    existing_record: dict[str, Any] | None,
) -> list[str]:
    """Use the saved analyst selection when resuming an existing task."""
    if existing_record and isinstance(existing_record.get("selected_analysts"), list):
        return [str(x) for x in existing_record["selected_analysts"]]
    return list(selected_analysts)


def _load_final_state_for_repair(
    ticker: str,
    trade_date: str,
    existing_record: dict[str, Any] | None,
    runtime_config: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    """Load the saved full-state log for report repair."""
    if existing_record and existing_record.get("legacy_cli"):
        legacy_final_state = load_legacy_cli_final_state(ticker, trade_date)
        if legacy_final_state is not None:
            legacy_log_path = Path.home() / ".tradingagents" / "logs" / ticker / trade_date / "message_tool.log"
            return legacy_final_state, legacy_log_path

    log_path = Path(
        (existing_record or {}).get("final_state_path")
        or full_log_path(ticker, trade_date, runtime_config)
    )
    if log_path.exists() and log_path.suffix.lower() == ".json":
        import json

        with log_path.open(encoding="utf-8") as f:
            final_state = json.load(f)
        return final_state, log_path

    legacy_final_state = load_legacy_cli_final_state(ticker, trade_date)
    if legacy_final_state is not None:
        legacy_log_path = Path.home() / ".tradingagents" / "logs" / ticker / trade_date / "message_tool.log"
        return legacy_final_state, legacy_log_path

    raise FileNotFoundError(f"找不到可用于补报告的日志文件: {log_path}")


def _generate_reports(
    graph: Any,
    final_state: dict[str, Any],
    ticker: str,
    trade_date: str,
    stop_event: threading.Event | None = None,
) -> tuple[str, str, str | None]:
    """Generate the compact and risk HTML reports."""
    stock_name = get_stock_name(ticker)
    compact_path = ""
    risk_path = ""
    postprocess_error: str | None = None

    try:
        if stop_event and stop_event.is_set():
            raise InterruptedError("用户已取消")
        html = generate_compact_html_report(
            llm=graph.quick_thinking_llm,
            final_state=final_state,
            ticker=ticker,
            trade_date=trade_date,
        )
        compact_path = str(save_compact_html_report(html, ticker, stock_name, trade_date))
        if stop_event and stop_event.is_set():
            raise InterruptedError("用户已取消")
    except Exception as exc:
        if isinstance(exc, InterruptedError):
            raise
        postprocess_error = str(exc)
        import logging

        logging.getLogger(__name__).warning("Compact HTML report generation failed: %s", exc)

    try:
        if stop_event and stop_event.is_set():
            raise InterruptedError("用户已取消")
        risk_html = generate_risk_html_report(
            llm=graph.quick_thinking_llm,
            risk_debate_state=final_state.get("risk_debate_state", {}),
        )
        risk_path = str(save_risk_html_report(risk_html, ticker, stock_name, trade_date))
        if stop_event and stop_event.is_set():
            raise InterruptedError("用户已取消")
    except Exception as exc:
        if isinstance(exc, InterruptedError):
            raise
        postprocess_error = postprocess_error or str(exc)
        if postprocess_error and str(exc) not in postprocess_error:
            postprocess_error = f"{postprocess_error}; {exc}"
        import logging

        logging.getLogger(__name__).warning("Risk HTML report generation failed: %s", exc)

    return compact_path, risk_path, postprocess_error


def _clear_task_checkpoint(runtime_config: dict[str, Any], ticker: str, trade_date: str) -> None:
    """Best-effort removal of a finished task's checkpoint rows."""
    try:
        clear_checkpoint(runtime_config["data_cache_dir"], ticker, trade_date)
    except Exception as exc:
        logger.warning("Failed to clear checkpoint for %s %s: %s", ticker, trade_date, exc)


def _run(
    ticker: str,
    trade_date: str,
    config: dict,
    tracker: ProgressTracker,
    selected_analysts: list[str],
    task_record: dict[str, Any] | None = None,
    repair_only: bool = False,
    stop_event: threading.Event | None = None,
    user_id: str = "",
) -> None:
    """Execute the full pipeline in the current thread."""
    from cli.stats_handler import StatsCallbackHandler
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    stats = StatsCallbackHandler()
    existing_record = dict(task_record) if task_record else None
    runtime_config = _build_runtime_config(config, existing_record, repair_only)
    effective_analysts = _initial_selected_analysts(selected_analysts, existing_record)

    graph = TradingAgentsGraph(
        effective_analysts,
        debug=True,
        config=runtime_config,
        callbacks=[stats],
    )

    task_record_state = existing_record
    if task_record_state is not None and not repair_only:
        task_record_state = _persist_task_record(
            task_record_state,
            tracker,
            status="running",
            analysis_complete=False,
            report_complete=False,
            delete_requested=False,
            error="",
            report_error="",
            is_running=True,
            is_complete=False,
            stock_name=task_record_state.get("stock_name") or get_stock_name(ticker),
            config=runtime_config,
            selected_analysts=effective_analysts,
        )
    elif task_record_state is None and not repair_only:
        owner_id = 0
        try:
            owner_id = int(user_id) if user_id else 0
        except Exception:
            pass
        task_record_state = create_task_record(
            ticker,
            trade_date,
            runtime_config,
            effective_analysts,
            stock_name=get_stock_name(ticker),
            owner_user_id=owner_id,
        )
        task_record_state = _persist_task_record(
            task_record_state,
            tracker,
            status="running",
            analysis_complete=False,
            report_complete=False,
            delete_requested=False,
            error="",
            report_error="",
            is_running=True,
            is_complete=False,
        )
    elif task_record_state is not None and repair_only:
        # Keep the saved record visible while a repair-only run is in flight.
        task_record_state = _persist_task_record(
            task_record_state,
            tracker,
            status=task_record_state.get("status", "recoverable"),
            analysis_complete=bool(task_record_state.get("analysis_complete")),
            report_complete=bool(task_record_state.get("report_complete")),
            report_error="",
            error="",
            is_running=True,
            is_complete=False,
            config=runtime_config,
            selected_analysts=effective_analysts,
            stock_name=task_record_state.get("stock_name") or get_stock_name(ticker),
        )
        task_record_state = _refresh_task_record(task_record_state)
        if task_record_state and task_record_state.get("delete_requested"):
            delete_task_artifacts(task_record_state)
            tracker.mark_error("任务已删除")
            return

    checkpoint_ctx = None
    last_chunk: dict[str, Any] = {}
    final_state: dict[str, Any] = {}
    analysis_complete = bool(task_record_state and task_record_state.get("analysis_complete"))
    report_complete = bool(task_record_state and task_record_state.get("report_complete"))
    signal = task_record_state.get("signal", "") if task_record_state else ""
    postprocess_error: str | None = None
    log_path = Path(
        (task_record_state or {}).get("final_state_path")
        or full_log_path(ticker, trade_date, runtime_config)
    )
    stock_name = (task_record_state or {}).get("stock_name") or get_stock_name(ticker)

    _stop_ev = stop_event if stop_event is not None else threading.Event()
    try:
        if repair_only:
            final_state, log_path = _load_final_state_for_repair(
                ticker,
                trade_date,
                task_record_state,
                runtime_config,
            )
            if _stop_ev.is_set():
                raise InterruptedError("用户已取消")
            signal = graph.process_signal(final_state.get("final_trade_decision", ""))
            compact_path, risk_path, postprocess_error = _generate_reports(
                graph,
                final_state,
                ticker,
                trade_date,
                stop_event=_stop_ev,
            )
            report_complete = bool(compact_path and risk_path)
            if task_record_state is not None:
                task_record_state = _persist_task_record(
                    task_record_state,
                    tracker,
                    status="completed" if report_complete else "recoverable",
                    analysis_complete=True,
                    report_complete=report_complete,
                    report_error=postprocess_error or "",
                    error="",
                    final_state_path=str(log_path),
                    report_path=compact_path,
                    risk_report_path=risk_path,
                    signal=signal,
                    is_running=False,
                    is_complete=True,
                    stock_name=stock_name,
                    config=runtime_config,
                    selected_analysts=effective_analysts,
                )
            _clear_task_checkpoint(runtime_config, ticker, trade_date)
            tracker.postprocess_error = postprocess_error
            tracker.mark_complete(final_state, signal)
            tracker.postprocess_error = postprocess_error
            return

        init_state = graph.propagator.create_initial_state(ticker, trade_date)
        args = graph.propagator.get_graph_args(callbacks=[stats])

        if runtime_config.get("checkpoint_enabled"):
            checkpoint_ctx = get_checkpointer(runtime_config["data_cache_dir"], ticker)
            saver = checkpoint_ctx.__enter__()
            graph.graph = graph.workflow.compile(checkpointer=saver)

            args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = thread_id(
                ticker, trade_date
            )
            if (
                task_record_state is not None
                and not task_record_state.get("analysis_complete")
                and checkpoint_step(runtime_config["data_cache_dir"], ticker, trade_date) is not None
            ):
                init_state = None

        for chunk in graph.graph.stream(init_state, **args):
            task_record_state = _refresh_task_record(task_record_state)
            if _stop_ev.is_set():
                if task_record_state and task_record_state.get("delete_requested"):
                    delete_task_artifacts(task_record_state)
                    tracker.mark_error("任务已删除")
                    return
                if task_record_state:
                    task_record_state = _persist_task_record(
                        task_record_state,
                        tracker,
                        status="interrupted",
                        analysis_complete=False,
                        report_complete=False,
                        error="用户已取消",
                        report_error="",
                        is_running=False,
                        is_complete=False,
                    )
                tracker.mark_error("用户已取消")
                return

            last_chunk = chunk
            _detect_completed_stages(chunk, tracker)
            _infer_active_stage(tracker)
            _capture_messages(chunk, tracker)

            s = stats.get_stats()
            tracker.update_stats(s["llm_calls"], s["tool_calls"], s["tokens_in"], s["tokens_out"])

            if task_record_state:
                task_record_state = _persist_task_record(
                    task_record_state,
                    tracker,
                    status="running",
                    analysis_complete=False,
                    report_complete=False,
                    error="",
                    report_error="",
                    is_running=True,
                    is_complete=False,
                    stock_name=stock_name,
                    config=runtime_config,
                    selected_analysts=effective_analysts,
                )

        task_record_state = _refresh_task_record(task_record_state)
        if task_record_state and task_record_state.get("delete_requested"):
            delete_task_artifacts(task_record_state)
            tracker.mark_error("任务已删除")
            return

        if not last_chunk:
            raise RuntimeError("分析没有返回任何结果")

        signal = graph.process_signal(last_chunk.get("final_trade_decision", ""))
        graph.ticker = ticker
        depth = runtime_config.get("max_debate_rounds", 5)
        mode_map = {1: "快速", 3: "中等", 5: "深度"}
        analysis_mode = mode_map.get(depth, "深度")
        stock_name = get_stock_name(ticker)
        graph._log_state(
            trade_date,
            last_chunk,
            elapsed_seconds=tracker.elapsed,
            analysis_mode=analysis_mode,
            stock_name=stock_name,
        )

        final_state = dict(last_chunk)
        log_path = full_log_path(ticker, trade_date, runtime_config)
        analysis_complete = True
        if task_record_state:
            task_record_state = _persist_task_record(
                task_record_state,
                tracker,
                status="running",
                analysis_complete=True,
                report_complete=False,
                error="",
                report_error="",
                final_state_path=str(log_path),
                signal=signal,
                stock_name=stock_name,
                config=runtime_config,
                selected_analysts=effective_analysts,
                is_running=True,
                is_complete=False,
            )

        task_record_state = _refresh_task_record(task_record_state)
        if task_record_state and task_record_state.get("delete_requested"):
            delete_task_artifacts(task_record_state)
            tracker.mark_error("任务已删除")
            return

        compact_path, risk_path, postprocess_error = _generate_reports(
            graph,
            final_state,
            ticker,
            trade_date,
            stop_event=_stop_ev,
        )
        report_complete = bool(compact_path and risk_path)

        if task_record_state:
            task_record_state = _persist_task_record(
                task_record_state,
                tracker,
                status="completed" if report_complete else "recoverable",
                analysis_complete=True,
                report_complete=report_complete,
                report_error=postprocess_error or "",
                error="",
                final_state_path=str(log_path),
                report_path=compact_path,
                risk_report_path=risk_path,
                signal=signal,
                stock_name=stock_name,
                config=runtime_config,
                selected_analysts=effective_analysts,
                is_running=False,
                is_complete=True,
            )

        _clear_task_checkpoint(runtime_config, ticker, trade_date)
        tracker.postprocess_error = postprocess_error
        tracker.mark_complete(last_chunk, signal)
        tracker.postprocess_error = postprocess_error
    except Exception as exc:
        if task_record_state:
            status = "recoverable" if analysis_complete else "interrupted"
            task_record_state = _persist_task_record(
                task_record_state,
                tracker,
                status=status,
                analysis_complete=analysis_complete,
                report_complete=report_complete,
                error=str(exc) if not analysis_complete else "",
                report_error=postprocess_error or "",
                final_state_path=str(log_path) if analysis_complete else "",
                signal=signal if analysis_complete else task_record_state.get("signal", ""),
                stock_name=stock_name,
                config=runtime_config,
                selected_analysts=effective_analysts,
                is_running=False,
                is_complete=False,
            )
        raise
    finally:
        if checkpoint_ctx is not None:
            checkpoint_ctx.__exit__(None, None, None)
        with _REGISTRY_LOCK:
            _RUN_REGISTRY.pop(_task_key(ticker, trade_date), None)


def run_analysis_in_thread(
    ticker: str,
    trade_date: str,
    config: dict,
    tracker: ProgressTracker,
    selected_analysts: list[str],
    task_record: dict[str, Any] | None = None,
    repair_only: bool = False,
    user_id: str = "",
) -> threading.Thread:
    """Launch the pipeline in a daemon thread. Returns the thread handle."""
    tk = _task_key(ticker, trade_date)
    stop_event = threading.Event()
    tracker.ticker = ticker
    tracker.trade_date = trade_date
    tracker.is_running = True

    if task_record:
        apply_task_snapshot(tracker, task_record)
        tracker.error = None
        tracker.postprocess_error = None
    else:
        tracker.mark_stage_active("market")

    with _REGISTRY_LOCK:
        _RUN_REGISTRY[tk] = {
            "tracker": tracker,
            "thread": None,
            "stop_event": stop_event,
            "user_id": user_id,
        }

    def _target() -> None:
        try:
            _run(
                ticker,
                trade_date,
                config,
                tracker,
                selected_analysts,
                task_record=task_record,
                repair_only=repair_only,
                stop_event=stop_event,
                user_id=user_id,
            )
        except Exception as exc:
            tracker.mark_error(str(exc))
        finally:
            with _REGISTRY_LOCK:
                _RUN_REGISTRY.pop(tk, None)

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    with _REGISTRY_LOCK:
        if tk in _RUN_REGISTRY:
            _RUN_REGISTRY[tk]["thread"] = t
    return t
