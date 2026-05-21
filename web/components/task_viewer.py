"""Task detail view for incomplete or resumable analyses."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from web.history import load_task_detail


def _render_field(label: str, value: Any) -> None:
    st.markdown(
        f"<div style='font-size:0.82rem; color:#6b7280; margin-bottom:0.2rem;'>{label}</div>"
        f"<div style='font-size:0.95rem; color:#1f2937; font-weight:600;'>{value or '—'}</div>",
        unsafe_allow_html=True,
    )


def _join_stages(stages: Any) -> str:
    if not stages:
        return "—"
    if isinstance(stages, list):
        return "、".join(str(x) for x in stages if str(x).strip()) or "—"
    return str(stages)


def render_task_detail(entry: dict[str, Any]) -> None:
    """Render the task detail page for an incomplete or recoverable run."""
    source_path = entry.get("view_path") or entry.get("path") or entry.get("task_path") or ""
    payload: dict[str, Any] = {}
    if source_path and Path(source_path).exists():
        try:
            loaded = load_task_detail(source_path)
            if isinstance(loaded, dict):
                payload = loaded
        except Exception:
            payload = {}

    data = dict(payload)
    data.update(entry)

    st.markdown("### 🔎 任务详情")
    st.markdown(
        f"""
        <div style="background:#ffffff; border:1px solid #e5e7eb; border-radius:12px; padding:1rem 1.1rem; margin-bottom:1rem;">
            <div style="font-size:1.15rem; font-weight:800; color:#1f2937; margin-bottom:0.25rem;">
                {data.get("ticker", "—")} {data.get("name", "")}
            </div>
            <div style="color:#6b7280; font-size:0.92rem;">
                分析日期：{data.get("date", "—")} · 状态：{data.get("status_label", "—")} · 模式：{data.get("analysis_mode", "—")}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        _render_field("当前阶段", data.get("current_stage") or "—")
    with col2:
        _render_field("已完成阶段", len(data.get("completed_stages", [])) if isinstance(data.get("completed_stages"), list) else data.get("completed_stages") or "—")
    with col3:
        _render_field("LLM / 工具", f"{data.get('llm_calls', 0)} / {data.get('tool_calls', 0)}")
    with col4:
        elapsed = data.get("elapsed_str") or data.get("elapsed_seconds") or "—"
        _render_field("耗时", elapsed)

    error = data.get("error") or ""
    if error:
        st.error(f"错误信息: {error}")

    report_error = data.get("report_error") or ""
    if report_error and report_error != error:
        st.warning(f"后处理问题: {report_error}")

    if data.get("status_label") in {"中断", "可恢复"}:
        st.info("这条任务还没有完整结束，可以回到历史列表点击“继续”来接着跑。")
    elif data.get("legacy_cli"):
        st.info("这是一条从历史运行日志恢复出来的旧任务，没有 Web 任务清单和 checkpoint；点击“继续”会走补报告 / 补产物流程。")

    stage_reports = data.get("stage_reports") or {}
    if isinstance(stage_reports, dict) and stage_reports:
        st.markdown("#### 阶段快照")
        for stage_name, report in stage_reports.items():
            with st.expander(str(stage_name), expanded=False):
                st.markdown(str(report))

    if data.get("legacy_cli"):
        legacy_dir = Path(data.get("path") or data.get("view_path") or "")
        if legacy_dir.is_dir():
            st.markdown("#### 旧任务产物")
            report_files = sorted(p for p in legacy_dir.glob("*.md"))
            for report_file in report_files:
                if report_file.name == "complete_report.md":
                    continue
                with st.expander(report_file.name, expanded=False):
                    try:
                        st.markdown(report_file.read_text(encoding="utf-8"))
                    except Exception as exc:
                        st.warning(f"读取失败: {exc}")

    if data.get("final_trade_decision") or data.get("investment_plan") or data.get("trader_investment_plan"):
        st.markdown("#### 当前结果摘要")
        if data.get("final_trade_decision"):
            st.markdown(f"**最终决策**：{data.get('final_trade_decision')}")
        if data.get("investment_plan"):
            st.markdown(f"**投资计划**：{data.get('investment_plan')}")
        if data.get("trader_investment_plan"):
            st.markdown(f"**交易员计划**：{data.get('trader_investment_plan')}")

    with st.expander("原始任务数据", expanded=False):
        st.json(data)

    st.markdown("---")
    if st.button("返回历史", type="secondary", use_container_width=True):
        st.session_state.pop("viewing_task", None)
        st.session_state["current_page"] = "history"
        st.rerun()
