"""TradingAgents A股分析 — Streamlit Web UI."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

load_dotenv(_PROJECT_ROOT / ".env")

from tradingagents.default_config import DEFAULT_CONFIG  # noqa: E402

from web.components.progress_panel import render_progress  # noqa: E402
from web.components.report_viewer import render_report  # noqa: E402
from web.components.sidebar import _resolve_user_input  # noqa: E402
from web.history import extract_signal, get_history, load_analysis  # noqa: E402
from web.progress import ProgressTracker  # noqa: E402
from web.runner import get_active_tracker, request_stop, run_analysis_in_thread  # noqa: E402

# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="A股多专家投研系统",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ───────────────────────────────────────────────────────────────

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&display=swap');

    /* Hide Streamlit chrome */
    #MainMenu, header[data-testid="stHeader"],
    footer, div[data-testid="stDecoration"],
    div[data-testid="stToolbar"] { display: none !important; }
    /* Hide sidebar completely */
    section[data-testid="stSidebar"] { display: none !important; }
    button[data-testid="collapsedControl"] { display: none !important; }

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, sans-serif;
    }
    .stApp {
        background: #f8f9fa;
    }
    .stMetric label { color: #6b7280 !important; font-size: 0.8rem !important; }
    .stMetric [data-testid="stMetricValue"] {
        color: #ff5a1f !important;
        font-weight: 700 !important;
    }
    .stProgress > div > div > div {
        background: linear-gradient(90deg, #ff5a1f, #ff8c42) !important;
    }
    button[kind="primary"] {
        background: linear-gradient(135deg, #ff5a1f, #ff8c42) !important;
        border: none !important;
        font-weight: 700 !important;
        letter-spacing: 0.05em !important;
        box-shadow: 0 4px 15px rgba(255,90,31,0.25) !important;
        transition: all 0.2s ease !important;
    }
    button[kind="primary"]:hover {
        background: linear-gradient(135deg, #e04d15, #ff5a1f) !important;
        box-shadow: 0 6px 20px rgba(255,90,31,0.35) !important;
        transform: translateY(-1px) !important;
    }
    /* Secondary buttons (history items) */
    button[kind="secondary"] {
        background: #f3f4f6 !important;
        border: 1px solid #e5e7eb !important;
        color: #374151 !important;
        transition: all 0.2s ease !important;
    }
    button[kind="secondary"]:hover {
        background: #e5e7eb !important;
        border-color: #ff5a1f !important;
        color: #ff5a1f !important;
    }
    .stExpander {
        border: 1px solid #e5e7eb !important;
        border-radius: 8px !important;
        background: #ffffff !important;
    }
    .stTabs [data-baseweb="tab"] {
        color: #6b7280 !important;
    }
    .stTabs [aria-selected="true"] {
        color: #ff5a1f !important;
        border-bottom-color: #ff5a1f !important;
    }
    div[data-testid="stDownloadButton"] button {
        background: #fff7ed !important;
        border: 1px solid #ff5a1f !important;
        color: #c2410c !important;
    }
    div[data-testid="stDownloadButton"] button:hover {
        background: #ffedd5 !important;
    }
    /* Text input styling */
    input[data-testid="stTextInputRootElement"] input,
    .stTextInput input {
        background: #ffffff !important;
        border-color: #d1d5db !important;
        color: #1f2937 !important;
    }
    .stTextInput input:focus {
        border-color: #ff5a1f !important;
        box-shadow: 0 0 0 1px #ff5a1f !important;
    }
    /* Date input styling */
    .stDateInput input {
        background: #ffffff !important;
        border-color: #d1d5db !important;
        color: #1f2937 !important;
    }

    /* ── Top navigation bar ────────────────────────────────────────────── */
    div[data-testid="stHorizontalBlock"]:has(.nav-brand) {
        background: #ff5a1f !important;
        padding: 0.8rem 1.5rem !important;
        margin: -1rem -1rem 1.5rem -1rem !important;
        border-radius: 0 !important;
    }
    div[data-testid="stHorizontalBlock"]:has(.nav-brand) button {
        background: transparent !important;
        color: white !important;
        border: none !important;
        box-shadow: none !important;
        font-weight: 600 !important;
        letter-spacing: 0.02em !important;
    }
    div[data-testid="stHorizontalBlock"]:has(.nav-brand) button:hover {
        background: rgba(255,255,255,0.15) !important;
    }
    div[data-testid="stHorizontalBlock"]:has(.nav-brand) button:active {
        background: rgba(255,255,255,0.25) !important;
    }
    div[data-testid="stHorizontalBlock"]:has(.nav-brand) button:focus {
        outline: none !important;
        box-shadow: none !important;
    }
    div[data-testid="stHorizontalBlock"]:has(.nav-brand) button * {
        color: white !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Navigation bar ───────────────────────────────────────────────────────────

def _render_top_nav() -> None:
    """Render the top orange navigation bar."""
    cols = st.columns([3, 1, 1, 1, 2])
    with cols[0]:
        st.markdown(
            '<span class="nav-brand" style="color:white; font-size:1.3rem; font-weight:700;">A股多专家分析系统</span>',
            unsafe_allow_html=True,
        )
    with cols[1]:
        if st.button("首页", key="nav_home", use_container_width=True):
            st.session_state["current_page"] = "home"
            st.session_state.pop("viewing_history", None)
            st.rerun()
    with cols[2]:
        if st.button("历史分析", key="nav_history", use_container_width=True):
            st.session_state["current_page"] = "history"
            st.session_state.pop("viewing_history", None)
            st.rerun()
    with cols[3]:
        if st.button("新建分析", key="nav_new", use_container_width=True):
            st.session_state["current_page"] = "new"
            st.session_state.pop("viewing_history", None)
            st.rerun()
    with cols[4]:
        st.empty()


# ── Welcome screen helper ───────────────────────────────────────────────────

def _render_welcome() -> None:
    st.markdown(
        """
        <div style="max-width: 900px; margin: 0 auto; padding: 2rem 1rem;">
            <div style="text-align: center; margin-bottom: 2.5rem;">
                <div style="font-size: 3.5rem; margin-bottom: 0.5rem;">📈</div>
                <div style="font-size: 2.2rem; font-weight: 900; margin-bottom: 0.4rem;">
                    <span style="color: #ff5a1f;">A股多专家</span><span style="color: #1f2937;">投研系统</span>
                </div>
                <div style="color: #6b7280; font-size: 1.05rem; line-height: 1.6;">
                    7位AI分析师 + 多空辩论 + 风控评估，智能生成A股投研报告
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Pipeline flow pills
    st.markdown(
        """
        <div style="max-width: 900px; margin: 0 auto 2rem auto; padding: 0 1rem;">
            <div style="background: #ffffff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 1.2rem 1.5rem; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
                <div style="font-size: 0.85rem; color: #9ca3af; margin-bottom: 0.6rem; letter-spacing: 1px;">分析流程</div>
                <div style="display: flex; flex-wrap: wrap; justify-content: center; gap: 0.4rem; font-size: 0.85rem; color: #4b5563;">
                    <span style="background: #fff7ed; color: #c2410c; padding: 0.25rem 0.6rem; border-radius: 999px; font-weight: 600;">7位分析师</span>
                    <span style="color: #d1d5db;">→</span>
                    <span style="background: #fff7ed; color: #c2410c; padding: 0.25rem 0.6rem; border-radius: 999px; font-weight: 600;">质量门控</span>
                    <span style="color: #d1d5db;">→</span>
                    <span style="background: #fff7ed; color: #c2410c; padding: 0.25rem 0.6rem; border-radius: 999px; font-weight: 600;">多空辩论</span>
                    <span style="color: #d1d5db;">→</span>
                    <span style="background: #fff7ed; color: #c2410c; padding: 0.25rem 0.6rem; border-radius: 999px; font-weight: 600;">风控评估</span>
                    <span style="color: #d1d5db;">→</span>
                    <span style="background: #fff7ed; color: #c2410c; padding: 0.25rem 0.6rem; border-radius: 999px; font-weight: 600;">最终决策</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Feature cards grid
    st.markdown(
        """
        <div style="max-width: 900px; margin: 0 auto 2rem auto; padding: 0 1rem; display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem;">
            <div style="background: #ffffff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 1.2rem; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
                <div style="font-size: 1.5rem; margin-bottom: 0.4rem;">🤖</div>
                <div style="font-weight: 700; color: #1f2937; margin-bottom: 0.3rem; font-size: 0.95rem;">7位AI分析师</div>
                <div style="color: #6b7280; font-size: 0.82rem; line-height: 1.5;">市场、情绪、新闻、基本面、政策、游资、解禁全覆盖</div>
            </div>
            <div style="background: #ffffff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 1.2rem; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
                <div style="font-size: 1.5rem; margin-bottom: 0.4rem;">⚖️</div>
                <div style="font-weight: 700; color: #1f2937; margin-bottom: 0.3rem; font-size: 0.95rem;">多空辩论</div>
                <div style="color: #6b7280; font-size: 0.82rem; line-height: 1.5;">Bull vs Bear 投研辩论，风控三方评估，避免单一视角偏差</div>
            </div>
            <div style="background: #ffffff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 1.2rem; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
                <div style="font-size: 1.5rem; margin-bottom: 0.4rem;">📊</div>
                <div style="font-weight: 700; color: #1f2937; margin-bottom: 0.3rem; font-size: 0.95rem;">A股数据直连</div>
                <div style="color: #6b7280; font-size: 0.82rem; line-height: 1.5;">mootdx + 东财 + 新浪 + 同花顺，全免费零门槛</div>
            </div>
            <div style="background: #ffffff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 1.2rem; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
                <div style="font-size: 1.5rem; margin-bottom: 0.4rem;">📄</div>
                <div style="font-weight: 700; color: #1f2937; margin-bottom: 0.3rem; font-size: 0.95rem;">精简报告输出</div>
                <div style="color: #6b7280; font-size: 0.82rem; line-height: 1.5;">自动生成PDF与HTML精简报告，核心结论一目了然</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # CTA + Disclaimer
    st.markdown(
        """
        <div style="max-width: 900px; margin: 0 auto; padding: 0 1rem;">
            <div style="background: #ffffff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 1.2rem; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.04); margin-bottom: 1.5rem;">
                <div style="color: #4b5563; font-size: 1rem; font-weight: 600; margin-bottom: 0.3rem;">
                    点击上方「新建分析」按钮，开始分析
                </div>
                <div style="color: #9ca3af; font-size: 0.85rem;">支持6位代码或中文股票名称</div>
            </div>
            <div style="text-align: center; color: #9ca3af; font-size: 0.75rem; line-height: 1.6; max-width: 600px; margin: 0 auto;">
                ⚠️ 本项目仅供学习研究与技术演示，不构成任何投资建议。<br>
                投资决策请咨询持牌专业机构。作者不对使用本工具产生的任何损失承担责任。
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Home page ────────────────────────────────────────────────────────────────

def _render_home() -> None:
    """Render the home page: welcome, progress, report, or error."""
    tracker: ProgressTracker | None = st.session_state.get("tracker")
    viewing_history: str | None = st.session_state.get("viewing_history")

    # State 1: Viewing a historical analysis
    if viewing_history:
        try:
            state = load_analysis(viewing_history)
            signal = extract_signal(state)
            ticker = Path(viewing_history).parent.parent.name
            trade_date = Path(viewing_history).stem.replace("full_states_log_", "")
            render_report(state, ticker, trade_date, signal)
        except Exception as exc:
            st.error(f"加载失败: {exc}")
        return

    # State 2: Analysis running
    if tracker and tracker.is_running:
        render_progress(tracker)

        if st.button("⏹ 停止分析", use_container_width=True, type="secondary"):
            request_stop()
            st.session_state.pop("tracker", None)
            st.session_state.pop("start_analysis", None)
            st.rerun()

        import time
        time.sleep(0.5)
        st.rerun()
        return

    # State 3: Analysis complete
    if tracker and tracker.is_complete:
        render_report(
            tracker.final_state,
            tracker.ticker,
            tracker.trade_date,
            tracker.signal,
            elapsed=tracker.elapsed,
        )
        return

    # State 4: Analysis errored
    if tracker and tracker.error:
        st.error(f"分析失败: {tracker.error}")
        if st.button("重试"):
            st.session_state.pop("tracker", None)
            st.rerun()
        return

    # State 0: Idle — welcome screen
    _render_welcome()


# ── History page ─────────────────────────────────────────────────────────────

def _render_history_page() -> None:
    """Render the history analysis list page."""
    st.markdown("### 📜 历史分析")

    history = get_history(limit=200)
    if not history:
        st.info("暂无历史分析记录")
        return

    # White card container
    st.markdown(
        """
        <div style="background:#ffffff; border:1px solid #e5e7eb; border-radius:12px; overflow:hidden; margin-bottom:1.5rem;">
        """,
        unsafe_allow_html=True,
    )

    # Header row
    hdr_col1, hdr_col2, hdr_col3, hdr_col4 = st.columns([3, 2, 2, 1])
    with hdr_col1:
        st.markdown("<span style='color:#374151; font-weight:600; font-size:0.9rem;'>报告名称</span>", unsafe_allow_html=True)
    with hdr_col2:
        st.markdown("<span style='color:#374151; font-weight:600; font-size:0.9rem;'>分析日期</span>", unsafe_allow_html=True)
    with hdr_col3:
        st.markdown("<span style='color:#374151; font-weight:600; font-size:0.9rem;'>分析耗时</span>", unsafe_allow_html=True)
    with hdr_col4:
        st.markdown("<span style='color:#374151; font-weight:600; font-size:0.9rem;'>操作</span>", unsafe_allow_html=True)

    st.markdown("<div style='height:0.5rem; background:#f8f9fa; margin:0 -1rem;'></div>", unsafe_allow_html=True)

    for i, entry in enumerate(history):
        ticker = entry["ticker"]
        name = entry["name"]
        date_str = entry["date"]
        elapsed = entry["elapsed_str"]
        display_name = f"{ticker} {name}" if name else ticker

        col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
        with col1:
            st.markdown(f"<span style='color:#1f2937; font-weight:500;'>{display_name}</span>", unsafe_allow_html=True)
        with col2:
            st.markdown(f"<span style='color:#6b7280; font-size:0.9rem;'>{date_str}</span>", unsafe_allow_html=True)
        with col3:
            st.markdown(f"<span style='color:#6b7280; font-size:0.9rem;'>{elapsed}</span>", unsafe_allow_html=True)
        with col4:
            if st.button("查看", key=f"view_{ticker}_{date_str}", type="secondary"):
                st.session_state["viewing_history"] = entry["path"]
                st.session_state["current_page"] = "home"
                st.rerun()

        if i < len(history) - 1:
            st.markdown("<div style='height:1px; background:#f3f4f6; margin:0 -1rem;'></div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


# ── New analysis page ────────────────────────────────────────────────────────

def _render_new_analysis_page() -> None:
    """Render the new analysis page with ticker input and depth selector."""
    st.markdown("### ➕ 新建分析")

    ticker = st.text_input(
        "股票代码或名称",
        placeholder="例: 300750 或 宁德时代",
        key="input_ticker_new",
        help="输入6位A股代码或中文股票全称",
    )

    depth = st.selectbox(
        "分析模式",
        options=["快速", "中等", "深度"],
        index=2,
        help="快速=少量辩论轮次，深度=全面深入研究",
    )

    if st.button("开始分析", type="primary", use_container_width=True):
        if not ticker or not ticker.strip():
            st.error("❌ 请输入股票代码")
        else:
            resolved_code, err = _resolve_user_input(ticker)
            if err:
                st.error(f"❌ {err}")
            else:
                if resolved_code != ticker.strip():
                    st.success(f"✅ {ticker.strip()} → {resolved_code}")

                trade_date = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
                tracker = ProgressTracker(
                    ticker=resolved_code,
                    trade_date=trade_date,
                )
                st.session_state["tracker"] = tracker
                st.session_state["current_page"] = "home"

                depth_map = {"快速": 1, "中等": 3, "深度": 5}
                config = _build_config(depth=depth_map[depth])
                run_analysis_in_thread(
                    ticker=resolved_code,
                    trade_date=trade_date,
                    config=config,
                    tracker=tracker,
                    selected_analysts=_SELECTED_ANALYSTS,
                )
                st.rerun()


# ── Build config ─────────────────────────────────────────────────────────────

_SELECTED_ANALYSTS = [
    "market", "social", "news", "fundamentals", "policy", "hot_money", "lockup"
]


def _build_config(depth: int = 5) -> dict:
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "anthropic"
    config["backend_url"] = "https://api.minimaxi.com/anthropic"
    config["deep_think_llm"] = "claude-opus-4-6"
    config["quick_think_llm"] = "claude-sonnet-4-6"
    config["data_vendors"] = {
        "core_stock_apis": "a_stock",
        "technical_indicators": "a_stock",
        "fundamental_data": "a_stock",
        "news_data": "a_stock",
        "signal_data": "a_stock",
    }
    config["max_debate_rounds"] = depth
    config["max_risk_discuss_rounds"] = depth
    config["output_language"] = "Chinese"
    config["anthropic_effort"] = "high"
    return config


# ── Handle "Start Analysis" trigger (legacy, from sidebar era) ───────────────

start_req = st.session_state.pop("start_analysis", None)
if start_req:
    trade_date = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    tracker = ProgressTracker(
        ticker=start_req["ticker"],
        trade_date=trade_date,
    )
    st.session_state["tracker"] = tracker
    st.session_state["current_page"] = "home"
    run_analysis_in_thread(
        ticker=start_req["ticker"],
        trade_date=trade_date,
        config=_build_config(),
        tracker=tracker,
        selected_analysts=_SELECTED_ANALYSTS,
    )


# ── Reconnect to an active background run after page refresh ─────────────────

if "tracker" not in st.session_state:
    _active = get_active_tracker()
    if _active and (_active.is_running or _active.is_complete or _active.error):
        st.session_state["tracker"] = _active


# ── Initialize page routing ──────────────────────────────────────────────────

if "current_page" not in st.session_state:
    st.session_state["current_page"] = "home"


# ── Render top nav + page content ────────────────────────────────────────────

_render_top_nav()

current_page = st.session_state.get("current_page", "home")
if current_page == "home":
    _render_home()
elif current_page == "history":
    _render_history_page()
elif current_page == "new":
    _render_new_analysis_page()
