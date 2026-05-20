"""Render the completed analysis report with HTML preview and export."""

from __future__ import annotations

import re
from pathlib import Path as _Path
from typing import Any

import streamlit as st

from tradingagents.reporting.compact_html_report import get_stock_name, _safe_filename
from web.pdf_export import generate_pdf


def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()


def _signal_style(signal: str) -> tuple[str, str]:
    s = signal.upper()
    if "BUY" in s:
        return "#22c55e", "买入"
    if "SELL" in s:
        return "#ef4444", "卖出"
    return "#fbbf24", "持有"


_ANALYST_SECTIONS = [
    ("market_report", "📊 技术分析"),
    ("sentiment_report", "💬 市场情绪"),
    ("news_report", "📰 新闻舆情"),
    ("fundamentals_report", "📋 基本面"),
    ("policy_report", "🏛️ 政策分析"),
    ("hot_money_report", "🔥 游资追踪"),
    ("lockup_report", "🔒 解禁/减持"),
]


def _resolve_html_report(ticker: str, trade_date: str) -> tuple[bool, bytes, str]:
    """Return (exists, bytes, suggested_filename) for the compact HTML report."""
    stock_name = get_stock_name(ticker)
    safe_name = _safe_filename(stock_name) if stock_name else "unknown"
    html_file = _Path("report") / f"{_safe_filename(ticker)}_{safe_name}_{trade_date}.html"
    if html_file.exists():
        return True, html_file.read_bytes(), f"{ticker}_{safe_name}_{trade_date}.html"
    return False, b"", ""


def render_report(
    final_state: dict[str, Any],
    ticker: str,
    trade_date: str,
    signal: str,
    elapsed: float | None = None,
) -> None:
    """Render the full analysis report."""

    color, cn_signal = _signal_style(signal)

    stats_html = ""
    if elapsed is not None:
        m, s = divmod(int(elapsed), 60)
        stats_html = f'<div style="font-size:0.9rem; color:#888; margin-top:0.3rem;">耗时 {m}:{s:02d}</div>'

    st.markdown(
        f"""
        <div style="
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 16px;
            padding: 2rem;
            text-align: center;
            margin: 1rem 0 2rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        ">
            <div style="font-size:0.9rem; color:#9ca3af; letter-spacing:2px;">TRADING SIGNAL</div>
            <div style="font-size:3.5rem; font-weight:900; color:{color}; margin:0.3rem 0;">
                {signal.upper()}
            </div>
            <div style="font-size:1.2rem; color:#1f2937;">
                {ticker} · {trade_date}
            </div>
            {stats_html}
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.caption("⚠️ 本报告由 AI 自动生成，仅供学习研究，不构成投资建议。", help="")

    # ── Try compact HTML report first ───────────────────────────────────────
    html_exists, html_bytes, html_filename = _resolve_html_report(ticker, trade_date)

    if html_exists:
        # Render HTML directly in an iframe
        st.components.v1.html(html_bytes.decode("utf-8"), height=900, scrolling=True)

        # Export button row
        col_pdf, col_html = st.columns([1, 1])
        with col_pdf:
            try:
                pdf_bytes = generate_pdf(final_state, ticker, trade_date, signal)
                st.download_button(
                    "📥 下载 PDF 报告",
                    data=pdf_bytes,
                    file_name=f"TradingAgents-Astock_{ticker}_{trade_date}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            except Exception:
                st.button("📥 PDF 生成失败", disabled=True, use_container_width=True)
        with col_html:
            st.download_button(
                "📄 导出 HTML 报告",
                data=html_bytes,
                file_name=html_filename,
                mime="text/html",
                use_container_width=True,
            )

        # Optional: keep raw markdown in a collapsed expander for reference
        with st.expander("🔍 查看原始分析报告", expanded=False):
            _render_raw_markdown(final_state)
        return

    # ── Fallback: raw markdown report ───────────────────────────────────────
    col_pdf, col_spacer = st.columns([1, 3])
    with col_pdf:
        try:
            pdf_bytes = generate_pdf(final_state, ticker, trade_date, signal)
            st.download_button(
                "📥 下载 PDF 报告",
                data=pdf_bytes,
                file_name=f"TradingAgents-Astock_{ticker}_{trade_date}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception:
            st.button("📥 PDF 生成失败", disabled=True, use_container_width=True)

    _render_raw_markdown(final_state)


def _render_raw_markdown(final_state: dict[str, Any]) -> None:
    """Render the raw multi-agent markdown report (fallback)."""
    inv_plan = final_state.get("investment_plan", "")
    if inv_plan:
        st.markdown("### 👔 最终投资建议")
        st.markdown(_strip_think(str(inv_plan)))
        st.markdown("---")

    st.markdown("### 📊 分析师报告")

    for key, title in _ANALYST_SECTIONS:
        content = final_state.get(key, "")
        if not content:
            continue
        with st.expander(title, expanded=False):
            st.markdown(_strip_think(str(content)))

    debate = final_state.get("investment_debate_state")
    if debate and isinstance(debate, dict):
        st.markdown("### ⚔️ 多空辩论")
        tab_bull, tab_bear, tab_judge = st.tabs(["多方", "空方", "研究经理"])
        with tab_bull:
            st.markdown(_strip_think(debate.get("bull_history", "") or "无数据"))
        with tab_bear:
            st.markdown(_strip_think(debate.get("bear_history", "") or "无数据"))
        with tab_judge:
            st.markdown(_strip_think(debate.get("judge_decision", "") or "无数据"))

    trader_decision = final_state.get("trader_investment_decision", "")
    if trader_decision:
        with st.expander("💹 交易员决策", expanded=False):
            st.markdown(_strip_think(str(trader_decision)))

    risk = final_state.get("risk_debate_state")
    if risk and isinstance(risk, dict):
        st.markdown("### 🛡️ 风控评估")
        tab_agg, tab_con, tab_neu, tab_rj = st.tabs(["激进", "保守", "中性", "风控决策"])
        with tab_agg:
            st.markdown(_strip_think(risk.get("aggressive_history", "") or "无数据"))
        with tab_con:
            st.markdown(_strip_think(risk.get("conservative_history", "") or "无数据"))
        with tab_neu:
            st.markdown(_strip_think(risk.get("neutral_history", "") or "无数据"))
        with tab_rj:
            st.markdown(_strip_think(risk.get("judge_decision", "") or "无数据"))

    dqs = final_state.get("data_quality_summary", "")
    if dqs:
        with st.expander("✅ 数据质量", expanded=False):
            st.markdown(str(dqs))
