"""TradingAgents A股分析 — Streamlit Web UI."""

from __future__ import annotations

import sys
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import streamlit as st
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

load_dotenv(_PROJECT_ROOT / ".env")

from tradingagents.default_config import DEFAULT_CONFIG  # noqa: E402

from web.components.progress_panel import render_progress  # noqa: E402
from web.components.report_viewer import render_report, _inject_copy_guard  # noqa: E402
from web.components.task_viewer import render_task_detail  # noqa: E402
from web.components.sidebar import _resolve_user_input  # noqa: E402
from web.history import extract_signal, get_history, load_analysis  # noqa: E402
from web.progress import ProgressTracker  # noqa: E402
from web.runner import get_active_tracker, request_stop, run_analysis_in_thread  # noqa: E402
from web.task_store import (  # noqa: E402
    apply_task_snapshot,
    build_resume_config,
    delete_task_artifacts,
    legacy_cli_date_dir,
    load_legacy_cli_final_state,
    load_task_record_by_path,
    save_task_record,
    task_key,
)
from web.auth_store import (  # noqa: E402
    init_auth_db,
    ensure_default_users,
    run_legacy_migration,
    verify_password,
    create_user,
    update_user,
    delete_user,
    list_users,
    get_user_by_id,
    change_password,
    admin_reset_password,
    require_auth,
)

# ── Page config ──────────────────────────────────────────────────────────────

_VERSION = "V1.0.8"

st.set_page_config(
    page_title="A股多专家投研系统",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Initialize auth DB & run legacy migration once ───────────────────────────
init_auth_db()
ensure_default_users()
_migration_result = run_legacy_migration()

# ── Custom CSS ───────────────────────────────────────────────────────────────

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;600;700&display=swap');

    /* Hide Streamlit chrome */
    #MainMenu, header[data-testid="stHeader"],
    footer, div[data-testid="stDecoration"],
    div[data-testid="stToolbar"] { display: none !important; }
    /* Hide sidebar completely */
    section[data-testid="stSidebar"] { display: none !important; }
    button[data-testid="collapsedControl"] { display: none !important; }

    html, body, [class*="css"] {
        font-family: 'Noto Sans SC', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
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

    /* ── Sticky report header bar ──────────────────────────────────────── */
    div[data-testid="stHorizontalBlock"]:has(.sticky-header-marker) {
        position: sticky !important;
        top: 0 !important;
        z-index: 99 !important;
        background: #f8f9fa !important;
        padding: 0.8rem 1.5rem !important;
        margin: -1rem -1rem 1rem -1rem !important;
        border-bottom: 1px solid #e5e7eb !important;
        border-radius: 0 !important;
    }
    /* Embedded report: no iframe border feel */
    .embedded-report {
        border: none !important;
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
    /* Hide "Press Enter to submit form" hint inside forms */
    div[data-testid="InputInstructions"] {
        display: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Navigation bar ───────────────────────────────────────────────────────────

def _render_user_menu() -> None:
    """Render user avatar dropdown in the top-right corner."""
    user = st.session_state.get("auth_user")
    if not user:
        return
    username = user.get("username", "")
    role_label = "管理" if user.get("role") == "admin" else "用户"
    with st.popover(f"👤 {username} ({role_label})", use_container_width=False):
        if user.get("role") == "user":
            if st.button("🏠 个人主页", key="menu_profile", use_container_width=True):
                st.session_state["current_page"] = "profile"
                st.rerun()
        if st.button("🔐 修改密码", key="menu_change_pwd", use_container_width=True):
            st.session_state["current_page"] = "change_password"
            st.rerun()
        st.markdown("<hr style='margin:0.5rem 0;'>", unsafe_allow_html=True)
        if st.button("🚪 退出登录", key="menu_logout", use_container_width=True):
            st.session_state.pop("auth_user", None)
            st.session_state.pop("tracker", None)
            st.session_state.pop("viewing_history", None)
            st.session_state.pop("viewing_task", None)
            st.session_state["current_page"] = "login"
            st.rerun()


def _render_top_nav() -> None:
    """Render the top orange navigation bar."""
    cols = st.columns([3, 1, 1, 1, 1.5])
    with cols[0]:
        st.markdown(
            f'<span class="nav-brand" style="color:white; font-size:1.3rem; font-weight:700;">A股多专家分析系统</span>'
            f'<span style="color:white; font-size:0.75rem; opacity:0.85; margin-left:0.5rem;">{_VERSION}</span>',
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
        _render_user_menu()


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


def _status_color(label: str) -> str:
    """Return a simple color for history/status labels."""
    return {
        "完成": "#16a34a",
        "中断": "#dc2626",
        "进行中": "#f97316",
        "可恢复": "#2563eb",
        "已删除": "#6b7280",
    }.get(label, "#6b7280")


_HISTORY_HTML_RE = re.compile(
    r"^(?P<ticker>\d{6})_.+_(?P<trade_date>\d{4}-\d{2}-\d{2})(?:_risk)?$"
)


def _infer_history_identity(source_path: Path) -> tuple[str, str] | None:
    """Infer ticker and trade date from a history artifact path."""
    if source_path.name.startswith("full_states_log_") and source_path.suffix.lower() == ".json":
        return source_path.parent.parent.name, source_path.stem.replace("full_states_log_", "")

    if source_path.suffix.lower() == ".html":
        match = _HISTORY_HTML_RE.match(source_path.stem)
        if match:
            return match.group("ticker"), match.group("trade_date")

    if source_path.name == "complete_report.md" and source_path.parent.name == "reports":
        try:
            trade_date = source_path.parent.parent.name
            ticker = source_path.parent.parent.parent.name
        except Exception:
            return None
        if re.fullmatch(r"\d{6}", ticker) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", trade_date):
            return ticker, trade_date

    if source_path.name == "reports" and source_path.is_dir():
        try:
            trade_date = source_path.parent.name
            ticker = source_path.parent.parent.name
        except Exception:
            return None
        if re.fullmatch(r"\d{6}", ticker) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", trade_date):
            return ticker, trade_date

    return None


def _load_history_report_state(viewing_history: Any) -> tuple[dict[str, Any], str, str, str]:
    """Load a report-view target into (state, ticker, trade_date, signal)."""
    candidates: list[Path] = []

    if isinstance(viewing_history, dict):
        ticker = str(viewing_history.get("ticker") or "")
        trade_date = str(viewing_history.get("date") or viewing_history.get("trade_date") or "")
        if ticker and trade_date and viewing_history.get("legacy_cli"):
            state = load_legacy_cli_final_state(ticker, trade_date)
            if state:
                return state, ticker, trade_date, extract_signal(state)

        for key in ("task_path", "log_path", "path", "view_path"):
            value = viewing_history.get(key)
            if value:
                candidates.append(Path(str(value)))
    else:
        candidates.append(Path(str(viewing_history)))

    for source_path in candidates:
        if not source_path:
            continue

        if source_path.suffix.lower() == ".json":
            if source_path.name.startswith("full_states_log_"):
                state = load_analysis(str(source_path))
                ticker = source_path.parent.parent.name
                trade_date = source_path.stem.replace("full_states_log_", "")
                return state, ticker, trade_date, extract_signal(state)

            record = load_task_record_by_path(source_path)
            if record:
                ticker = str(record.get("ticker") or source_path.parent.name)
                trade_date = str(record.get("trade_date") or source_path.stem)
                if record.get("legacy_cli"):
                    state = load_legacy_cli_final_state(ticker, trade_date)
                    if state:
                        return state, ticker, trade_date, extract_signal(state)

                final_state_path = record.get("final_state_path")
                if final_state_path:
                    final_path = Path(str(final_state_path))
                    if final_path.exists() and final_path.suffix.lower() == ".json":
                        state = load_analysis(str(final_path))
                        return state, ticker, trade_date, extract_signal(state)

            # If the task JSON itself does not exist, fall back to next candidate
            # (e.g. log_path pointing to a real full_states_log_*.json)
            if not source_path.exists():
                continue

            state = load_analysis(str(source_path))
            ticker = source_path.parent.parent.name if source_path.name.startswith("full_states_log_") else source_path.parent.name
            trade_date = source_path.stem.replace("full_states_log_", "")
            return state, ticker, trade_date, extract_signal(state)

        identity = _infer_history_identity(source_path)
        if identity:
            ticker, trade_date = identity
            state = load_legacy_cli_final_state(ticker, trade_date)
            if state:
                return state, ticker, trade_date, extract_signal(state)

    raise FileNotFoundError(f"无法加载历史报告: {viewing_history}")


# ── Login page ───────────────────────────────────────────────────────────────

def _render_login() -> None:
    """Render the login page."""
    st.markdown(
        """
        <div style="max-width: 400px; margin: 4rem auto; padding: 2rem; background: #ffffff;
                    border: 1px solid #e5e7eb; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.06);">
            <div style="text-align: center; margin-bottom: 1.5rem;">
                <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">📈</div>
                <div style="font-size: 1.4rem; font-weight: 700; color: #1f2937;">A股多专家分析系统</div>
                <div style="color: #9ca3af; font-size: 0.85rem;">请登录后继续</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Centered narrow form aligned with title card (~400px)
    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("用户名", placeholder="请输入用户名")
            password = st.text_input("密码", type="password", placeholder="请输入密码")
            submitted = st.form_submit_button("登录", use_container_width=True, type="primary")

        if submitted:
            if not username or not password:
                st.error("请输入用户名和密码")
            else:
                user = verify_password(username.strip(), password)
                if user is None:
                    st.error("用户名或密码错误")
                else:
                    st.session_state["auth_user"] = user
                    st.session_state.pop("viewing_history", None)
                    st.session_state.pop("viewing_task", None)
                    st.session_state.pop("tracker", None)
                    if user.get("must_change_password"):
                        st.session_state["current_page"] = "force_change_password"
                    elif user.get("role") == "admin":
                        st.session_state["current_page"] = "admin"
                    else:
                        st.session_state["current_page"] = "home"
                    st.rerun()
        return


# ── Force change password page ───────────────────────────────────────────────

def _render_force_change_password() -> None:
    """Force password change on first login or after admin reset."""
    user = st.session_state.get("auth_user")
    if not user:
        st.session_state["current_page"] = "login"
        st.rerun()
        return

    st.markdown(
        """
        <div style="max-width: 400px; margin: 4rem auto; padding: 2rem; background: #ffffff;
                    border: 1px solid #e5e7eb; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.06);">
            <div style="text-align: center; margin-bottom: 1.5rem;">
                <div style="font-size: 2rem; margin-bottom: 0.5rem;">🔐</div>
                <div style="font-size: 1.2rem; font-weight: 700; color: #1f2937;">首次登录，请修改密码</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        with st.form("force_change_password_form"):
            old_pwd = st.text_input("旧密码", type="password")
            new_pwd = st.text_input("新密码", type="password")
            confirm_pwd = st.text_input("确认新密码", type="password")
            submitted = st.form_submit_button("确认修改", use_container_width=True, type="primary")

    if submitted:
        if not old_pwd or not new_pwd or not confirm_pwd:
            st.error("请填写所有密码字段")
            return
        if new_pwd != confirm_pwd:
            st.error("两次输入的新密码不一致")
            return
        try:
            change_password(user["id"], old_pwd, new_pwd)
            st.success("密码修改成功，请重新登录")
            st.session_state.pop("auth_user", None)
            st.session_state["current_page"] = "login"
            st.rerun()
        except ValueError as e:
            st.error(f"修改失败: {e}")


# ── Admin page ───────────────────────────────────────────────────────────────

def _render_admin_page() -> None:
    """Admin-only user management page."""
    user = st.session_state.get("auth_user")
    if not user or user.get("role") != "admin":
        st.error("无权访问管理页面")
        st.session_state["current_page"] = "login"
        st.rerun()
        return

    st.markdown("### 👤 用户管理")

    # New user section
    with st.expander("➕ 新建用户"):
        with st.form("create_user_form"):
            new_username = st.text_input("用户名")
            new_role = st.selectbox("角色", options=["user", "admin"], index=0)
            new_password = st.text_input("初始密码", type="password")
            submitted = st.form_submit_button("创建用户", use_container_width=True, type="primary")
        if submitted:
            if not new_username or not new_password:
                st.error("用户名和密码不能为空")
            else:
                try:
                    create_user(new_username.strip(), new_password, new_role, user["id"])
                    st.success(f"用户 {new_username} 创建成功")
                    st.rerun()
                except ValueError as e:
                    st.error(f"创建失败: {e}")

    # User list
    all_users = list_users()
    if not all_users:
        st.info("暂无用户")
        return

    st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)
    for u in all_users:
        c1, c2, c3, c4, c5, c6 = st.columns([2, 1, 1, 1.5, 1.5, 2])
        with c1:
            st.markdown(f"<span style='font-weight:600;'>{u['username']}</span>", unsafe_allow_html=True)
        with c2:
            badge = "🔴 管理" if u["role"] == "admin" else "🔵 用户"
            st.markdown(badge)
        with c3:
            st.markdown("✅ 启用" if u["enabled"] else "❌ 禁用")
        with c4:
            st.markdown("🔐 需改密" if u["must_change_password"] else "—")
        with c5:
            st.caption(u.get("created_at", "")[:10])
        with c6:
            a1, a2, a3 = st.columns(3)
            with a1:
                if st.button("重置密码", key=f"reset_{u['id']}", use_container_width=True):
                    st.session_state[f"show_reset_{u['id']}"] = True
            with a2:
                disabled = u["id"] == user["id"]
                if st.button(
                    "禁用" if u["enabled"] else "启用",
                    key=f"toggle_{u['id']}",
                    use_container_width=True,
                    disabled=disabled and u["enabled"],
                ):
                    try:
                        update_user(u["id"], enabled=0 if u["enabled"] else 1)
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
            with a3:
                disabled = u["id"] == user["id"]
                if st.button("删除", key=f"del_{u['id']}", use_container_width=True, disabled=disabled):
                    try:
                        delete_user(u["id"], user["id"])
                        st.success(f"已删除 {u['username']}")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

        # Reset password inline
        if st.session_state.get(f"show_reset_{u['id']}"):
            with st.form(f"reset_form_{u['id']}"):
                reset_pwd = st.text_input("新密码", type="password")
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.form_submit_button("确认重置", use_container_width=True, type="primary"):
                        if reset_pwd:
                            try:
                                admin_reset_password(u["id"], reset_pwd)
                                st.success("密码已重置，用户下次登录需修改密码")
                                st.session_state.pop(f"show_reset_{u['id']}", None)
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))
                        else:
                            st.error("请输入新密码")
                with col_b:
                    if st.form_submit_button("取消", use_container_width=True):
                        st.session_state.pop(f"show_reset_{u['id']}", None)
                        st.rerun()

        st.markdown("<div style='height:1px; background:#f3f4f6; margin:0.5rem 0;'></div>", unsafe_allow_html=True)


# ── Change password page (self-service) ──────────────────────────────────────

def _render_change_password() -> None:
    """Self-service password change for normal users."""
    user = st.session_state.get("auth_user")
    if not user:
        st.session_state["current_page"] = "login"
        st.rerun()
        return

    st.markdown("### 🔐 修改密码")
    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        with st.form("change_password_form"):
            old_pwd = st.text_input("旧密码", type="password")
            new_pwd = st.text_input("新密码", type="password")
            confirm_pwd = st.text_input("确认新密码", type="password")
            submitted = st.form_submit_button("确认修改", use_container_width=True, type="primary")

    if submitted:
        if not old_pwd or not new_pwd or not confirm_pwd:
            st.error("请填写所有字段")
            return
        if new_pwd != confirm_pwd:
            st.error("两次输入的新密码不一致")
            return
        try:
            change_password(user["id"], old_pwd, new_pwd)
            st.success("密码修改成功")
            if user.get("role") == "admin":
                st.session_state["current_page"] = "admin"
            else:
                st.session_state["current_page"] = "home"
            st.rerun()
        except ValueError as e:
            st.error(f"修改失败: {e}")


# ── Profile page ─────────────────────────────────────────────────────────────

def _render_profile() -> None:
    """Simple profile page for normal users."""
    user = st.session_state.get("auth_user")
    if not user:
        st.session_state["current_page"] = "login"
        st.rerun()
        return

    st.markdown("### 🏠 个人主页")
    st.markdown(f"**用户名**: {user.get('username', '')}")
    st.markdown(f"**角色**: {'管理员' if user.get('role') == 'admin' else '普通用户'}")
    st.markdown(f"**状态**: {'启用' if user.get('enabled') else '禁用'}")


# ── Home page ────────────────────────────────────────────────────────────────

def _render_home() -> None:
    """Render the home page: welcome, progress, report, or error."""
    tracker: ProgressTracker | None = st.session_state.get("tracker")
    viewing_task: dict[str, Any] | None = st.session_state.get("viewing_task")
    viewing_history: Any = st.session_state.get("viewing_history")

    # State 0.5: Viewing an interrupted or resumable task
    if viewing_task:
        try:
            render_task_detail(viewing_task)
        except Exception as exc:
            st.error(f"加载任务详情失败: {exc}")
        return

    # State 1: Viewing a historical analysis
    if viewing_history:
        try:
            state, ticker, trade_date, signal = _load_history_report_state(viewing_history)
            render_report(state, ticker, trade_date, signal)
        except Exception as exc:
            st.error(f"加载失败: {exc}")
        return

    # State 2: Analysis running
    if tracker and tracker.is_running:
        render_progress(tracker)

        if st.button("⏹ 停止分析", use_container_width=True, type="secondary"):
            tk = task_key(tracker.ticker, tracker.trade_date)
            request_stop(tk)
            st.session_state.pop("tracker", None)
            st.session_state.pop("start_analysis", None)
            st.session_state["suppress_tracker_reconnect"] = True
            st.rerun()

        import time
        time.sleep(0.5)
        st.rerun()
        return

    # State 3: Analysis complete
    if tracker and tracker.is_complete:
        if tracker.postprocess_error:
            st.warning(f"任务已完成，但报告生成存在问题：{tracker.postprocess_error}")
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
    user = st.session_state.get("auth_user")
    if not user:
        st.error("请先登录")
        st.session_state["current_page"] = "login"
        st.rerun()
        return

    st.markdown("### 📜 历史分析")

    # Use cached history if available to avoid repeated file scanning
    cache_key = f"history_cache_{user['id']}"
    if cache_key not in st.session_state:
        st.session_state[cache_key] = get_history(user_id=user["id"], limit=200)
    history = st.session_state[cache_key]

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
    hdr_col1, hdr_col2, hdr_col3, hdr_col4, hdr_col5, hdr_col6 = st.columns([3, 2, 1.2, 1.5, 1.2, 1.8])
    with hdr_col1:
        st.markdown("<span style='color:#374151; font-weight:600; font-size:0.9rem;'>报告名称</span>", unsafe_allow_html=True)
    with hdr_col2:
        st.markdown("<span style='color:#374151; font-weight:600; font-size:0.9rem;'>分析日期</span>", unsafe_allow_html=True)
    with hdr_col3:
        st.markdown("<span style='color:#374151; font-weight:600; font-size:0.9rem;'>状态</span>", unsafe_allow_html=True)
    with hdr_col4:
        st.markdown("<span style='color:#374151; font-weight:600; font-size:0.9rem;'>分析模式</span>", unsafe_allow_html=True)
    with hdr_col5:
        st.markdown("<span style='color:#374151; font-weight:600; font-size:0.9rem;'>分析耗时</span>", unsafe_allow_html=True)
    with hdr_col6:
        st.markdown("<span style='color:#374151; font-weight:600; font-size:0.9rem;'>操作</span>", unsafe_allow_html=True)

    st.markdown("<div style='height:0.5rem; background:#f8f9fa; margin:0 -1rem;'></div>", unsafe_allow_html=True)

    for i, entry in enumerate(history):
        ticker = entry["ticker"]
        name = entry["name"]
        date_str = entry["date"]
        elapsed = entry["elapsed_str"]
        mode = entry.get("analysis_mode", "—")
        status_label = entry.get("status_label", "—")
        display_name = f"{ticker} {name}" if name else ticker

        col1, col2, col3, col4, col5, col6 = st.columns([3, 2, 1.2, 1.5, 1.2, 1.8])
        with col1:
            st.markdown(f"<span style='color:#1f2937; font-weight:500;'>{display_name}</span>", unsafe_allow_html=True)
        with col2:
            st.markdown(f"<span style='color:#6b7280; font-size:0.9rem;'>{date_str}</span>", unsafe_allow_html=True)
        with col3:
            st.markdown(
                f"<span style='color:{_status_color(status_label)}; font-size:0.9rem; font-weight:600;'>{status_label}</span>",
                unsafe_allow_html=True,
            )
        with col4:
            st.markdown(f"<span style='color:#6b7280; font-size:0.9rem;'>{mode}</span>", unsafe_allow_html=True)
        with col5:
            st.markdown(f"<span style='color:#6b7280; font-size:0.9rem;'>{elapsed}</span>", unsafe_allow_html=True)
        with col6:
            a1, a2, a3 = st.columns(3)
            with a1:
                if st.button("查看", key=f"view_{ticker}_{date_str}", type="secondary", use_container_width=True):
                    if entry.get("view_mode") == "report":
                        st.session_state["viewing_history"] = dict(entry)
                        st.session_state.pop("viewing_task", None)
                    else:
                        st.session_state["viewing_task"] = entry
                        st.session_state.pop("viewing_history", None)
                    st.session_state["current_page"] = "home"
                    st.rerun()
            with a2:
                if st.button(
                    "继续",
                    key=f"continue_{ticker}_{date_str}",
                    disabled=not bool(entry.get("can_continue")),
                    type="secondary",
                    use_container_width=True,
                ):
                    _queue_history_continue(entry)
            with a3:
                if st.button("删除", key=f"delete_{ticker}_{date_str}", type="secondary", use_container_width=True):
                    _delete_history_entry(entry)

        if i < len(history) - 1:
            st.markdown("<div style='height:1px; background:#f3f4f6; margin:0 -1rem;'></div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


# ── New analysis page ────────────────────────────────────────────────────────

def _render_new_analysis_page() -> None:
    """Render the new analysis page with ticker input and depth selector."""
    user = st.session_state.get("auth_user")
    if not user:
        st.error("请先登录")
        st.session_state["current_page"] = "login"
        st.rerun()
        return

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
                depth_map = {"快速": 1, "中等": 3, "深度": 5}
                request = {
                    "ticker": resolved_code,
                    "trade_date": trade_date,
                    "config": _build_config(depth=depth_map[depth]),
                    "selected_analysts": _SELECTED_ANALYSTS,
                    "user_id": str(user["id"]),
                }
                _launch_analysis_request(request)
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
    config["checkpoint_enabled"] = True
    return config


def _launch_analysis_request(request: dict[str, Any]) -> None:
    """Start a background analysis or report-repair request."""
    ticker = request["ticker"]
    trade_date = request.get("trade_date") or (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    config = request.get("config") or _build_config()
    selected_analysts = request.get("selected_analysts") or _SELECTED_ANALYSTS
    task_record = request.get("task_record")
    repair_only = bool(request.get("repair_only"))
    user_id = str(request.get("user_id", ""))

    tracker = ProgressTracker(
        ticker=ticker,
        trade_date=trade_date,
    )
    tracker.run_mode = "repair" if repair_only else "analysis"
    if task_record:
        apply_task_snapshot(tracker, task_record)
        tracker.error = None
        tracker.postprocess_error = None
        tracker.run_mode = "repair" if repair_only else "analysis"

    st.session_state["tracker"] = tracker
    st.session_state["current_page"] = "home"
    st.session_state.pop("suppress_tracker_reconnect", None)
    st.session_state.pop("viewing_task", None)
    st.session_state.pop("viewing_history", None)
    # Clear per-user history cache
    user = st.session_state.get("auth_user")
    if user:
        st.session_state.pop(f"history_cache_{user['id']}", None)

    run_analysis_in_thread(
        ticker=ticker,
        trade_date=trade_date,
        config=config,
        tracker=tracker,
        selected_analysts=selected_analysts,
        task_record=task_record,
        repair_only=repair_only,
        user_id=user_id,
    )


def _queue_history_continue(entry: dict[str, Any]) -> None:
    """Queue a continue/repair request from a history row."""
    mode = entry.get("continue_mode", "none")
    if mode == "none":
        return

    user = st.session_state.get("auth_user")
    user_id = str(user["id"]) if user else ""

    task_record = None
    config = _build_config()
    selected_analysts = _SELECTED_ANALYSTS

    task_path = entry.get("task_path") or ""
    if task_path:
        task_record = load_task_record_by_path(task_path)
    elif entry.get("legacy_cli"):
        legacy_dir = legacy_cli_date_dir(entry["ticker"], entry["date"])
        if legacy_dir.exists():
            task_record = {
                "ticker": entry["ticker"],
                "trade_date": entry["date"],
                "task_path": "",
                "config": _build_config(),
                "selected_analysts": _SELECTED_ANALYSTS,
                "stock_name": entry.get("stock_name") or entry.get("name") or "",
                "analysis_complete": True,
                "report_complete": bool(entry.get("report_complete")),
                "status": "recoverable" if not entry.get("report_complete") else "completed",
                "final_state_path": str(legacy_dir / "reports" / "complete_report.md"),
                "legacy_cli": True,
                "source": "legacy_cli",
            }

    if task_record and isinstance(task_record.get("config"), dict):
        config = build_resume_config(task_record)
        selected_analysts = task_record.get("selected_analysts") or selected_analysts
    elif task_record is None and mode == "repair":
        # Repair-only requests can run from the currently configured model.
        config = _build_config()

    request = {
        "ticker": entry["ticker"],
        "trade_date": entry["date"],
        "config": config,
        "selected_analysts": selected_analysts,
        "task_record": task_record,
        "repair_only": mode == "repair",
        "user_id": user_id,
    }
    st.session_state["start_analysis"] = request
    st.session_state.pop("viewing_task", None)
    st.session_state.pop("viewing_history", None)
    if user:
        st.session_state.pop(f"history_cache_{user['id']}", None)
    st.session_state["current_page"] = "home"
    st.rerun()


def _delete_history_entry(entry: dict[str, Any]) -> None:
    """Delete the task represented by a history row."""
    user = st.session_state.get("auth_user")
    caller_id = user["id"] if user else None

    task_path = entry.get("task_path") or ""
    task_record = load_task_record_by_path(task_path) if task_path else None

    # Ownership check
    if caller_id is not None:
        tk = task_key(entry["ticker"], entry["date"])
        from web.auth_store import get_task_owner
        owner = get_task_owner(tk)
        if owner is not None and owner != caller_id and user.get("role") != "admin":
            st.error("无权删除他人任务")
            return

    tk = task_key(entry["ticker"], entry["date"])
    active = get_active_tracker(task_key=tk, user_id=str(user["id"]) if user else "")
    is_active_task = bool(
        active
        and active.is_running
        and active.ticker == entry["ticker"]
        and active.trade_date == entry["date"]
    )

    if is_active_task:
        record = dict(task_record or entry)
        record.setdefault("ticker", entry["ticker"])
        record.setdefault("trade_date", entry["date"])
        record.setdefault("task_path", entry.get("task_path") or "")
        if not record.get("config"):
            record["config"] = _build_config()
        record["delete_requested"] = True
        save_task_record(record)
        request_stop(tk)
        st.session_state.pop("tracker", None)
        st.session_state["suppress_tracker_reconnect"] = True
    else:
        record = dict(task_record or entry)
        record.setdefault("ticker", entry["ticker"])
        record.setdefault("trade_date", entry["date"])
        record.setdefault("task_path", entry.get("task_path") or "")
        if not record.get("config"):
            record["config"] = _build_config()
        try:
            delete_task_artifacts(record, caller_user_id=caller_id)
        except PermissionError as e:
            st.error(str(e))
            return

    st.session_state.pop("viewing_task", None)
    st.session_state.pop("viewing_history", None)
    if user:
        st.session_state.pop(f"history_cache_{user['id']}", None)
    st.rerun()


# ── Handle "Start Analysis" trigger (legacy, from sidebar era) ───────────────

start_req = st.session_state.pop("start_analysis", None)
if start_req:
    _launch_analysis_request(start_req)


# ── Reconnect to an active background run after page refresh ─────────────────

if "tracker" not in st.session_state:
    if not st.session_state.get("suppress_tracker_reconnect"):
        user = st.session_state.get("auth_user")
        _active = get_active_tracker(user_id=str(user["id"]) if user else "")
        if _active and (_active.is_running or _active.is_complete or _active.error):
            st.session_state["tracker"] = _active


# ── Initialize page routing ──────────────────────────────────────────────────

if "current_page" not in st.session_state:
    st.session_state["current_page"] = "login"


# ── Route guard ──────────────────────────────────────────────────────────────

user = st.session_state.get("auth_user")
current_page = st.session_state.get("current_page", "login")

# Not logged in → force login
if not user:
    current_page = "login"
    st.session_state["current_page"] = "login"
else:
    # Force password change
    if user.get("must_change_password") and current_page != "force_change_password":
        current_page = "force_change_password"
        st.session_state["current_page"] = "force_change_password"
    # Admin route guard
    elif user.get("role") == "admin":
        if current_page not in ("admin", "change_password", "force_change_password", "login"):
            current_page = "admin"
            st.session_state["current_page"] = "admin"
    # Normal user route guard
    elif user.get("role") == "user":
        if current_page in ("admin",):
            current_page = "home"
            st.session_state["current_page"] = "home"


# ── Render top nav + page content ────────────────────────────────────────────

# Install copy guard globally (prevents Streamlit clear-cache popup on Ctrl+C)
_inject_copy_guard()

if current_page != "login":
    _render_top_nav()

current_page = st.session_state.get("current_page", "login")
if current_page == "login":
    _render_login()
elif current_page == "force_change_password":
    _render_force_change_password()
elif current_page == "admin":
    _render_admin_page()
elif current_page == "profile":
    _render_profile()
elif current_page == "change_password":
    _render_change_password()
elif current_page == "home":
    _render_home()
elif current_page == "history":
    _render_history_page()
elif current_page == "new":
    _render_new_analysis_page()
