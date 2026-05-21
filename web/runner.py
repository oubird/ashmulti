"""Background thread runner for TradingAgentsGraph pipeline."""

from __future__ import annotations

import re
import threading
from typing import Any

from web.progress import PIPELINE_STAGES, ProgressTracker


_REPORT_KEY_TO_STAGE = {s["report_key"]: s["id"] for s in PIPELINE_STAGES}

_ANALYST_REPORT_KEYS = [
    "market_report", "sentiment_report", "news_report",
    "fundamentals_report", "policy_report", "hot_money_report", "lockup_report",
]

# Global references so the UI can reconnect after a page refresh
_GLOBAL_TRACKER: ProgressTracker | None = None
_GLOBAL_THREAD: threading.Thread | None = None
_STOP_EVENT = threading.Event()


def get_active_tracker() -> ProgressTracker | None:
    """Return the globally stored tracker if a run is still active."""
    return _GLOBAL_TRACKER


def request_stop() -> None:
    """Signal the background runner to stop at the next chunk boundary."""
    _STOP_EVENT.set()


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
    msg_id = getattr(message, "id", None)

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

        # Capture tool calls from AIMessage
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            for tc in tool_calls:
                if isinstance(tc, dict):
                    tracker.add_tool_call(tc.get("name", "unknown"), tc.get("args", {}))
                else:
                    tracker.add_tool_call(getattr(tc, "name", "unknown"), getattr(tc, "args", {}))


def _run(
    ticker: str,
    trade_date: str,
    config: dict,
    tracker: ProgressTracker,
    selected_analysts: list[str],
) -> None:
    """Execute the full pipeline in the current thread."""
    from cli.stats_handler import StatsCallbackHandler
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    stats = StatsCallbackHandler()

    graph = TradingAgentsGraph(
        selected_analysts,
        debug=True,
        config=config,
        callbacks=[stats],
    )

    init_state = graph.propagator.create_initial_state(ticker, trade_date)
    args = graph.propagator.get_graph_args(callbacks=[stats])

    last_chunk: dict[str, Any] = {}

    for chunk in graph.graph.stream(init_state, **args):
        if _STOP_EVENT.is_set():
            tracker.mark_error("用户已取消")
            break
        last_chunk = chunk
        _detect_completed_stages(chunk, tracker)
        _infer_active_stage(tracker)
        _capture_messages(chunk, tracker)

        s = stats.get_stats()
        tracker.update_stats(s["llm_calls"], s["tool_calls"], s["tokens_in"], s["tokens_out"])

    signal = graph.process_signal(last_chunk.get("final_trade_decision", ""))

    graph.ticker = ticker
    depth = config.get("max_debate_rounds", 5)
    mode_map = {1: "快速", 3: "中等", 5: "深度"}
    analysis_mode = mode_map.get(depth, "深度")
    graph._log_state(trade_date, last_chunk, elapsed_seconds=tracker.elapsed, analysis_mode=analysis_mode)

    # Generate compact HTML report (post-processing, failures are non-fatal)
    try:
        from tradingagents.reporting.compact_html_report import (
            generate_compact_html_report,
            get_stock_name,
            save_compact_html_report,
        )

        html = generate_compact_html_report(
            llm=graph.quick_thinking_llm,
            final_state=last_chunk,
            ticker=ticker,
            trade_date=trade_date,
        )
        stock_name = get_stock_name(ticker)
        save_compact_html_report(html, ticker, stock_name, trade_date)
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning("Compact HTML report generation failed: %s", exc)

    tracker.mark_complete(last_chunk, signal)


def run_analysis_in_thread(
    ticker: str,
    trade_date: str,
    config: dict,
    tracker: ProgressTracker,
    selected_analysts: list[str],
) -> threading.Thread:
    """Launch the pipeline in a daemon thread. Returns the thread handle."""
    global _GLOBAL_TRACKER, _GLOBAL_THREAD

    _STOP_EVENT.clear()
    tracker.ticker = ticker
    tracker.trade_date = trade_date
    tracker.is_running = True
    tracker.mark_stage_active("market")

    _GLOBAL_TRACKER = tracker

    def _target() -> None:
        global _GLOBAL_TRACKER, _GLOBAL_THREAD
        try:
            _run(ticker, trade_date, config, tracker, selected_analysts)
        except Exception as exc:
            tracker.mark_error(str(exc))
        finally:
            _GLOBAL_TRACKER = None
            _GLOBAL_THREAD = None

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    _GLOBAL_THREAD = t
    return t
