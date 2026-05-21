"""Real-time progress display for the analysis pipeline."""

from __future__ import annotations

import streamlit as st

from web.progress import PIPELINE_STAGES, ProgressTracker


def _status_badge(status: str) -> str:
    if status == "done":
        return '<span style="color:#22c55e; font-size:1.3rem;">●</span>'
    if status == "active":
        return '<span style="color:#ff5a1f; font-size:1.3rem;">◉</span>'
    return '<span style="color:#333; font-size:1.3rem;">○</span>'


def _format_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def _msg_type_color(msg_type: str) -> str:
    """Return a CSS color for each message type."""
    return {
        "Data": "#0891b2",      # cyan-600
        "Agent": "#7c3aed",     # violet-600
        "User": "#2563eb",      # blue-600
        "System": "#6b7280",    # gray-500
        "Control": "#9ca3af",   # gray-400
        "Tool": "#ea580c",      # orange-600
    }.get(msg_type, "#6b7280")


def _truncate(text: str, max_len: int = 150) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


def render_progress(tracker: ProgressTracker) -> None:
    """Render the pipeline progress panel."""

    is_repair_mode = getattr(tracker, "run_mode", "analysis") == "repair"

    st.markdown(
        f"""
        <div style="text-align:center; margin:1rem 0 0.5rem;">
            <span style="font-size:1.6rem; font-weight:700; color:#1f2937;">
                {'补报告中' if is_repair_mode else '分析进行中'}
            </span>
            <span style="font-size:1.1rem; color:#6b7280; margin-left:0.8rem;">
                {tracker.ticker}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    completed = len(tracker.completed_stages)
    total = len(PIPELINE_STAGES)
    pct = completed / total if total else 0
    progress_text = f"{completed}/{total} 阶段完成  ·  {_format_time(tracker.elapsed)}"
    if is_repair_mode:
        progress_text = f"补报告中  ·  {_format_time(tracker.elapsed)}"
    st.progress(pct, text=progress_text)

    analyst_stages = PIPELINE_STAGES[:7]
    post_stages = PIPELINE_STAGES[7:]

    st.markdown(
        '<div style="margin:0.5rem 0 0.3rem; font-size:0.85rem; color:#6b7280; font-weight:600;">ANALYSTS</div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(len(analyst_stages))
    for col, stage in zip(cols, analyst_stages):
        status = tracker.stage_status(stage["id"])
        badge = _status_badge(status)
        label_color = "#ff5a1f" if status == "active" else "#9ca3af" if status == "pending" else "#16a34a"
        col.markdown(
            f"""
            <div style="text-align:center; padding:0.5rem 0;">
                {badge}<br>
                <span style="font-size:0.75rem; color:{label_color};">{stage['name']}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div style="margin:0.8rem 0 0.3rem; font-size:0.85rem; color:#6b7280; font-weight:600;">PIPELINE</div>',
        unsafe_allow_html=True,
    )

    cols2 = st.columns(len(post_stages))
    for col, stage in zip(cols2, post_stages):
        status = tracker.stage_status(stage["id"])
        badge = _status_badge(status)
        label_color = "#ff5a1f" if status == "active" else "#9ca3af" if status == "pending" else "#16a34a"
        col.markdown(
            f"""
            <div style="text-align:center; padding:0.5rem 0;">
                {badge}<br>
                <span style="font-size:0.75rem; color:{label_color};">{stage['name']}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("LLM 调用", tracker.llm_calls)
    c2.metric("工具调用", tracker.tool_calls)
    c3.metric("输入 Tokens", f"{tracker.tokens_in:,}")
    c4.metric("输出 Tokens", f"{tracker.tokens_out:,}")

    if tracker.error:
        st.error(f"错误: {tracker.error}")

    # ── Messages & Tools 实时日志 ──────────────────────────────────────────
    all_logs = []
    for ts, mtype, content in tracker.messages:
        all_logs.append((ts, mtype, content))
    for ts, tool_name, args_str in tracker.tool_calls_log:
        all_logs.append((ts, "Tool", f"{tool_name}({args_str})"))

    if all_logs:
        # Sort by time (they're HH:MM:SS strings, chronological append is fine)
        with st.expander(f"📜 Messages & Tools ({len(all_logs)})", expanded=False):
            for ts, mtype, content in all_logs:
                color = _msg_type_color(mtype)
                st.markdown(
                    f"""
                    <div style="font-family:monospace; font-size:0.78rem; line-height:1.4; margin-bottom:0.3rem;">
                        <span style="color:#9ca3af;">{ts}</span>
                        <span style="color:{color}; font-weight:600; margin-left:0.4rem;">{mtype}</span>
                        <span style="color:#374151; margin-left:0.4rem;">{_truncate(content, 200)}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    completed_reports = [
        (stage["name"], stage["icon"], tracker.stage_reports[stage["id"]])
        for stage in PIPELINE_STAGES
        if stage["id"] in tracker.stage_reports
    ]

    if completed_reports:
        st.markdown(
            '<div style="margin:0.5rem 0 0.3rem; font-size:0.85rem; color:#6b7280; font-weight:600;">'
            f"REPORTS ({len(completed_reports)})</div>",
            unsafe_allow_html=True,
        )
        for name, icon, report in reversed(completed_reports):
            is_latest = (name == completed_reports[-1][0])
            with st.expander(f"{icon} {name}", expanded=is_latest):
                st.markdown(report[:3000])
