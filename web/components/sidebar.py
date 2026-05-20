"""Sidebar: stock input and history list."""

from __future__ import annotations

import streamlit as st

from web.history import get_history


def _resolve_user_input(raw: str) -> tuple[str, str | None]:
    """Resolve raw user input to (ticker_code, error_msg).

    Accepts 6-digit codes or Chinese stock names (e.g. '宝光股份').
    Returns (code, None) on success or ("", error_msg) on failure.
    """
    from tradingagents.dataflows.a_stock import resolve_ticker

    try:
        code = resolve_ticker(raw)
        return code, None
    except ValueError as e:
        return "", str(e)


def render_sidebar() -> None:
    """Render the sidebar with input controls and history."""

    st.markdown(
        """
        <div style="text-align:center; margin-bottom:1.5rem;">
            <span style="font-size:2rem; font-weight:800; color:#ff5a1f;">Trading</span><span style="font-size:2rem; font-weight:800; color:#1f2937;">Agents</span><span style="font-size:2rem; font-weight:800; color:#1f2937;">-</span><span style="font-size:2rem; font-weight:800; color:#ff5a1f;">Astock</span>
            <div style="font-size:0.85rem; color:#6b7280; margin-top:0.2rem;">
                A股多Agent投研系统
            </div>
            <div style="font-size:0.7rem; color:#9ca3af; margin-top:0.3rem;">
                by <a href="https://github.com/simonlin1212" style="color:#ff5a1f; text-decoration:none;">simonlin1212</a>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.markdown("#### 新建分析")

    ticker = st.text_input(
        "股票代码",
        placeholder="例: 300750 或 宁德时代",
        key="input_ticker",
        help="输入6位A股代码或中文股票全称",
    )

    tracker = st.session_state.get("tracker")
    is_busy = tracker is not None and tracker.is_running

    if st.button(
        "开始分析" if not is_busy else "分析进行中...",
        use_container_width=True,
        disabled=is_busy,
        type="primary",
    ):
        if not ticker or not ticker.strip():
            st.error("❌ 请输入股票代码")
        else:
            resolved_code, err = _resolve_user_input(ticker)
            if err:
                st.error(f"❌ {err}")
            else:
                if resolved_code != ticker.strip():
                    st.success(f"✅ {ticker.strip()} → {resolved_code}")
                st.session_state["start_analysis"] = {
                    "ticker": resolved_code,
                }
                st.session_state["viewing_history"] = None

    if is_busy:
        if st.button(
            "⏹ 停止分析",
            use_container_width=True,
            type="secondary",
        ):
            from web.runner import request_stop
            request_stop()
            st.session_state.pop("tracker", None)
            st.session_state.pop("start_analysis", None)
            st.rerun()

    st.markdown("---")
    st.markdown("#### 历史记录")

    history = get_history()
    if not history:
        st.caption("暂无历史记录")
        return

    for entry in history[:20]:
        t, d = entry["ticker"], entry["date"]
        label = f"{t}  ·  {d}"
        if st.button(label, key=f"hist_{t}_{d}", use_container_width=True):
            st.session_state["viewing_history"] = entry["path"]
            st.session_state["start_analysis"] = None

    st.markdown("---")
    st.caption("⚠️ 仅供学习研究，不构成投资建议")
