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
from web.components.sidebar import render_sidebar  # noqa: E402
from web.history import extract_signal, load_analysis  # noqa: E402
from web.progress import ProgressTracker  # noqa: E402
from web.runner import run_analysis_in_thread  # noqa: E402

# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="TradingAgents-Astock A股分析",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ───────────────────────────────────────────────────────────────

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&display=swap');

    /* Hide Streamlit chrome for clean video recording */
    #MainMenu, header[data-testid="stHeader"],
    footer, div[data-testid="stDecoration"],
    div[data-testid="stToolbar"] { display: none !important; }
    /* Ensure sidebar collapse/expand control is always visible */
    button[data-testid="collapsedControl"] { display: flex !important; }

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, sans-serif;
    }
    .stApp {
        background: #f8f9fa;
    }
    section[data-testid="stSidebar"] {
        background: #ffffff;
        border-right: 1px solid #e5e7eb;
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
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Welcome screen helper ───────────────────────────────────────────────────

def _render_welcome() -> None:
    st.markdown(
        """
        <div style="max-width: 900px; margin: 0 auto; padding: 2rem 1rem;">
            <div style="text-align: center; margin-bottom: 2.5rem;">
                <div style="font-size: 3.5rem; margin-bottom: 0.5rem;">📈</div>
                <div style="font-size: 2.2rem; font-weight: 900; margin-bottom: 0.4rem;">
                    <span style="color: #ff5a1f;">Trading</span><span style="color: #1f2937;">Agents</span><span style="color: #1f2937;">-</span><span style="color: #ff5a1f;">Astock</span>
                </div>
                <div style="color: #6b7280; font-size: 1.05rem; line-height: 1.6;">
                    A股多Agent投研分析系统
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
                    ← 在左侧输入股票代码，开始分析
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


# ── Build config ─────────────────────────────────────────────────────────────

# Fixed configuration — all choices are automated per user request
_SELECTED_ANALYSTS = [
    "market", "social", "news", "fundamentals", "policy", "hot_money", "lockup"
]


def _build_config() -> dict:
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "minimax"
    config["deep_think_llm"] = "MiniMax-M2.7"
    config["quick_think_llm"] = "MiniMax-M2.7-highspeed"
    config["data_vendors"] = {
        "core_stock_apis": "a_stock",
        "technical_indicators": "a_stock",
        "fundamental_data": "a_stock",
        "news_data": "a_stock",
        "signal_data": "a_stock",
    }
    config["max_debate_rounds"] = 5
    config["max_risk_discuss_rounds"] = 5
    config["output_language"] = "Chinese"
    return config


# ── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    render_sidebar()


# ── Handle "Start Analysis" trigger ──────────────────────────────────────────

start_req = st.session_state.pop("start_analysis", None)
if start_req:
    trade_date = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    tracker = ProgressTracker(
        ticker=start_req["ticker"],
        trade_date=trade_date,
    )
    st.session_state["tracker"] = tracker
    run_analysis_in_thread(
        ticker=start_req["ticker"],
        trade_date=trade_date,
        config=_build_config(),
        tracker=tracker,
        selected_analysts=_SELECTED_ANALYSTS,
    )


# ── Main area state machine ─────────────────────────────────────────────────

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

# State 2: Analysis running
elif tracker and tracker.is_running:
    render_progress(tracker)

# State 3: Analysis complete
elif tracker and tracker.is_complete:
    render_report(
        tracker.final_state,
        tracker.ticker,
        tracker.trade_date,
        tracker.signal,
        elapsed=tracker.elapsed,
    )

# State 4: Analysis errored
elif tracker and tracker.error:
    st.error(f"分析失败: {tracker.error}")
    if st.button("重试"):
        st.session_state.pop("tracker", None)
        st.rerun()

# State 0: Idle — welcome screen
else:
    _render_welcome()
