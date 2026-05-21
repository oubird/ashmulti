"""Render the completed analysis report with summary panel and export buttons."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path as _Path
from typing import Any

import streamlit as st

from tradingagents.reporting.compact_html_report import get_stock_name, _safe_filename, _report_dir
from tradingagents.reporting.risk_html_report import _resolve_risk_html_report


def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()


def _signal_style(signal: str) -> tuple[str, str]:
    s = signal.upper()
    if "BUY" in s:
        return "#22c55e", "买入"
    if "SELL" in s:
        return "#ef4444", "卖出"
    return "#fbbf24", "持有"


def _report_table_css() -> str:
    """Compact table styling shared by embedded HTML and Markdown report content."""
    return """
    <style>
    .report-embed {
        max-width: 100%;
        overflow-x: auto;
    }
    .report-embed table,
    div[data-testid="stMarkdownContainer"] table {
        width: auto !important;
        max-width: 100% !important;
        table-layout: auto !important;
        display: inline-table !important;
        border-collapse: collapse !important;
        margin: 0.35rem 0 0.9rem 0 !important;
        font-size: 0.9rem !important;
    }
    .report-embed th,
    .report-embed td,
    div[data-testid="stMarkdownContainer"] th,
    div[data-testid="stMarkdownContainer"] td {
        padding: 0.3rem 0.55rem !important;
        line-height: 1.45 !important;
        white-space: normal !important;
        overflow-wrap: anywhere !important;
        word-break: break-word !important;
        vertical-align: top !important;
    }
    .report-embed th,
    div[data-testid="stMarkdownContainer"] th {
        white-space: nowrap !important;
    }
    </style>
    """


def _inject_report_table_css() -> None:
    """Inject compact table CSS for Markdown-rendered report sections."""
    st.markdown(_report_table_css(), unsafe_allow_html=True)


def _copy_guard_html() -> str:
    """Return hidden HTML/JS that blocks Streamlit's clear-cache hotkey on report pages."""
    return """
    <div data-testid="ta-report-copy-guard-root" hidden aria-hidden="true"></div>
    <script>
    (function () {
      const flagName = "__taCopyGuardInstalled";
      if (window[flagName]) {
        return;
      }
      window[flagName] = true;

      const reportMarkerSelector = '[data-testid="ta-report-copy-guard-root"]';
      const editableSelector = [
        "input",
        "textarea",
        "select",
        '[contenteditable=""]',
        '[contenteditable="true"]',
        '[contenteditable="plaintext-only"]',
      ].join(", ");

      const isEditableTarget = (target) => {
        if (!(target instanceof Element)) {
          return false;
        }
        return Boolean(target.closest(editableSelector));
      };

      const isReportPageActive = () => Boolean(document.querySelector(reportMarkerSelector));
      const getSelectionText = () => {
        const selection = window.getSelection ? window.getSelection() : null;
        return selection ? String(selection).trim() : "";
      };
      const isCopyKey = (event) => {
        const key = (event.key || "").toLowerCase();
        return key === "c" || event.code === "KeyC";
      };
      const hasCopyIntent = (event) => {
        const hasModifier = event.ctrlKey || event.metaKey;
        const hasSelection = getSelectionText().length > 0;
        return hasModifier || hasSelection;
      };

      const shouldBlockClearCacheShortcut = (event) => {
        if (!isReportPageActive()) {
          return false;
        }
        if (!isCopyKey(event) || isEditableTarget(event.target)) {
          return false;
        }
        return hasCopyIntent(event);
      };

      const handleKeyEvent = (event) => {
        if (!shouldBlockClearCacheShortcut(event)) {
          return;
        }
        event.stopPropagation();
        if (event.stopImmediatePropagation) {
          event.stopImmediatePropagation();
        }
        event.cancelBubble = true;
      };

      window.addEventListener("keydown", handleKeyEvent, true);
      window.addEventListener("keyup", handleKeyEvent, true);
      document.addEventListener("keydown", handleKeyEvent, true);
      document.addEventListener("keyup", handleKeyEvent, true);
    })();
    </script>
    """


def _inject_copy_guard() -> None:
    """Install the copy guard script for report pages."""
    st.html(_copy_guard_html(), unsafe_allow_javascript=True, width="content")


def _clean_html_for_embed(html: str) -> str:
    """Remove full-document tags so the HTML can be embedded inline."""
    html = re.sub(r"<!DOCTYPE[^>]*>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"</?html[^>]*>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"</?head[^>]*>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"</?body[^>]*>", "", html, flags=re.IGNORECASE)
    return f'<div class="report-embed">{html.strip()}</div>{_report_table_css()}'


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
    html_file = _report_dir() / f"{_safe_filename(ticker)}_{safe_name}_{trade_date}.html"
    if html_file.exists():
        return True, html_file.read_bytes(), f"{ticker}_{safe_name}_{trade_date}.html"
    return False, b"", ""


def _build_analyst_reports_zip(final_state: dict[str, Any]) -> bytes:
    """Pack the 7 analyst raw reports into a single zip file."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for key, title in _ANALYST_SECTIONS:
            content = final_state.get(key, "")
            if content:
                zf.writestr(f"{title}.md", str(content))
    return buf.getvalue()


def render_report(
    final_state: dict[str, Any],
    ticker: str,
    trade_date: str,
    signal: str,
    elapsed: float | None = None,
) -> None:
    """Render the full analysis report."""

    color, cn_signal = _signal_style(signal)
    stock_name = get_stock_name(ticker) or ""

    # ── Sticky header bar: title + download buttons ────────────────────────
    elapsed_str = ""
    if elapsed is not None:
        m, s = divmod(int(elapsed), 60)
        elapsed_str = f"共耗时{m}分{s:02d}秒" if m > 0 else f"共耗时{s}秒"

    header_line = f"{ticker} {stock_name}  投资评级：{cn_signal}（{signal.upper()}）  评测时间{trade_date}"
    if elapsed_str:
        header_line += f"  {elapsed_str}"

    html_exists, html_bytes, html_filename = _resolve_html_report(ticker, trade_date)
    zip_bytes = _build_analyst_reports_zip(final_state)

    _inject_copy_guard()
    _inject_report_table_css()

    header_cols = st.columns([3, 1, 1])
    with header_cols[0]:
        st.markdown(
            f'<span class="sticky-header-marker"></span><span style="font-size:1.05rem; font-weight:700; color:#1f2937;">{header_line}</span>',
            unsafe_allow_html=True,
        )
    with header_cols[1]:
        if html_exists:
            st.download_button(
                "📄 下载总结报告",
                data=html_bytes,
                file_name=html_filename,
                mime="text/html",
                use_container_width=True,
            )
        else:
            st.button("📄 总结报告未生成", disabled=True, use_container_width=True)
    with header_cols[2]:
        st.download_button(
            "📊 下载分析师报告",
            data=zip_bytes,
            file_name=f"{ticker}_分析师报告_{trade_date}.zip",
            mime="application/zip",
            use_container_width=True,
        )

    # ── Centered content area ──────────────────────────────────────────────
    _l_spacer, content_col, _r_spacer = st.columns([1, 6, 1])
    with content_col:
        # ── Compact HTML summary report (embedded, no iframe) ──────────────
        if html_exists:
            st.html(_clean_html_for_embed(html_bytes.decode("utf-8")))
        else:
            st.info("总结报告尚未生成")

        # ── Raw multi-agent reports ────────────────────────────────────────
        _render_raw_markdown(final_state, ticker, trade_date)

        # ── Disclaimer at bottom ───────────────────────────────────────────
        st.markdown("---")
        st.caption("⚠️ 本报告由 AI 自动生成，仅供学习研究，不构成投资建议。", help="")


def _render_raw_markdown(final_state: dict[str, Any], ticker: str, trade_date: str) -> None:
    """Render the raw multi-agent markdown report sections."""
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

    # ── Risk assessment: prefer translated Chinese HTML if available ────────
    risk = final_state.get("risk_debate_state")
    if risk and isinstance(risk, dict):
        st.markdown("### 🛡️ 风控评估")
        risk_html_exists, risk_html_bytes = _resolve_risk_html_report(ticker, trade_date)
        if risk_html_exists:
            st.html(_clean_html_for_embed(risk_html_bytes.decode("utf-8")))
        else:
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
