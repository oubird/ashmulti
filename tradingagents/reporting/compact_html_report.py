"""Compact HTML report generation for TradingAgents-Astock.

Post-processing step: after the full multi-agent pipeline completes,
feed the raw final_state to an LLM and ask it to produce a concise,
well-formatted Chinese HTML report.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

COMPACT_HTML_REPORT_PROMPT = """你是一个专业的 A 股投研报告整理员。
你的任务不是重新分析股票，也不是新增事实，而是把输入的 TradingAgents-astock 多智能体完整报告，整理成一份简洁、正式、可读性强的中文 HTML 精简报告。

## 整理规则（必须遵守）

1. 只基于输入报告整理，不得编造新数据、新价格、新指标。
2. 如果不同角色观点矛盾，必须以 **最终交易决策（final_trade_decision）** 为准。
3. 删除所有英文角色名，例如：Market Analyst、News Analyst、Bull Researcher、Bear Researcher、Research Team Decision、Portfolio Manager、Aggressive Analyst、Conservative Analyst、Neutral Analyst 等。用中文职能描述替代或省略。
4. 删除模型过程语，例如："我现在为您撰写"、"基于获取的数据"、"虽然 API 返回无数据"、"下面开始分析"、"让我梳理一下" 等。
5. 删除冗长辩论，多空辩论只保留最核心的 3-5 条理由，用简洁语言概括。
6. 删除重复内容。同一事实只出现一次。
7. 删除夸张、营销化、无法验证的表达，例如 "极具爆发力"、"千载难逢"、"必将大涨"。
8. 保留重要风险提示。
9. 输出必须是完整 HTML 文件，不要 Markdown，不要用代码块包裹。
10. HTML 里的 CSS 直接写在 `<style>` 标签里，不依赖外部文件。
11. 必须包含免责声明。
12. 如果原报告没有明确给出某个数据（如具体止损位、目标价），就写 "报告未明确给出"，不要编造。

## HTML 结构要求

请按以下结构生成 HTML：

1. **标题区**
   - 股票名称 / 股票代码
   - 分析日期
   - 数据截止日期
   - 最终信号：买入 / 持有 / 卖出（用醒目颜色区分）
   - 一句话结论

2. **核心结论摘要**
   - 当前最终建议
   - 仓位建议
   - 买入或加仓条件
   - 止损位
   - 主要风险

3. **关键交易计划表**
   - 当前价格
   - 支撑位
   - 压力位
   - 止损位
   - 止盈 / 目标区间
   - 加仓条件
   - 减仓 / 离场条件
   - 建议仓位
   （如果原报告没有明确数据，写"报告未明确给出"）

4. **技术面精简**
   - 趋势
   - 成交量
   - MACD
   - RSI
   - BOLL
   - 均线
   - ATR / 波动率

5. **消息面 / 舆情 / 政策面**
   - 利好因素
   - 利空因素
   - 中性观察

6. **基本面精简**
   - 估值
   - 营收 / 利润趋势
   - ROE / 盈利能力
   - 现金流
   - 机构预测可靠性
   - 数据缺失说明

7. **多空观点压缩**
   用两列表格：
   - 多头核心理由
   - 空头核心风险

8. **最终决策解释**
   解释为什么最终建议是这个结果。如果最终建议比前面某些分析师更保守，要说明原因。

9. **风险提示**
   用醒目的风险区域列出。

10. **后续跟踪清单**
    列出 5-8 个后续需要关注的事项。

11. **免责声明**
    必须包含："本报告由 AI 系统基于公开信息和模型推理自动整理，仅供学习研究与技术演示，不构成任何投资建议。"

## 视觉要求

- 使用专业的投研报告风格，白底黑字，配色克制。
- 标题区可以用深色背景 + 白色文字，突出信号颜色（买入=绿色、卖出=红色、持有=橙色/黄色）。
- 表格要有清晰的边框和交替行背景色。
- 风险区域用浅红色背景 + 深红色边框。
- 字体使用系统默认无衬线字体（font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif）。
- 整体宽度 max-width: 900px，居中显示。
- 适当的 padding 和 margin，阅读舒适。

## 输入数据

以下是从 TradingAgents-Astock 多智能体系统输出的完整原始报告，请据此整理：

{report_source}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_code_to_name_map() -> dict[str, str]:
    """Lazy-load the code→name map from a_stock module."""
    from tradingagents.dataflows.a_stock import _build_name_code_map

    _, c2n = _build_name_code_map()
    return c2n


def get_stock_name(ticker: str) -> str:
    """Resolve a 6-digit ticker to its Chinese name."""
    c2n = _get_code_to_name_map()
    name = c2n.get(ticker, "")
    if not name:
        # Fallback: try stripping any exchange prefix/suffix
        clean = re.sub(r"[^0-9]", "", ticker)
        name = c2n.get(clean, "")
    return name or "unknown"


def _safe_filename(text: str) -> str:
    """Remove characters illegal in Windows filenames."""
    return re.sub(r'[\\/:*?"<>|]', "", text)


# ---------------------------------------------------------------------------
# Build report source text for the LLM
# ---------------------------------------------------------------------------


def build_compact_report_source(
    final_state: dict[str, Any],
    ticker: str,
    trade_date: str,
) -> str:
    """Extract and prioritize content from final_state for the LLM prompt."""
    lines: list[str] = []
    lines.append(f"股票代码: {ticker}")
    lines.append(f"分析日期: {trade_date}")
    lines.append("")

    # Priority 1: Final decision
    if final_state.get("final_trade_decision"):
        lines.append("=" * 60)
        lines.append("【最终交易决策】")
        lines.append(str(final_state["final_trade_decision"]))
        lines.append("")

    # Priority 2: Investment plan (Research Manager)
    if final_state.get("investment_plan"):
        lines.append("=" * 60)
        lines.append("【最终投资计划】")
        lines.append(str(final_state["investment_plan"]))
        lines.append("")

    # Priority 3: Trader plan
    if final_state.get("trader_investment_plan"):
        lines.append("=" * 60)
        lines.append("【交易员计划】")
        lines.append(str(final_state["trader_investment_plan"]))
        lines.append("")

    # Priority 4: Risk debate
    risk = final_state.get("risk_debate_state")
    if risk and isinstance(risk, dict):
        lines.append("=" * 60)
        lines.append("【风控评估结论】")
        if risk.get("judge_decision"):
            lines.append(str(risk["judge_decision"]))
        if risk.get("aggressive_history"):
            lines.append("激进观点: " + str(risk["aggressive_history"])[:2000])
        if risk.get("conservative_history"):
            lines.append("保守观点: " + str(risk["conservative_history"])[:2000])
        if risk.get("neutral_history"):
            lines.append("中立观点: " + str(risk["neutral_history"])[:2000])
        lines.append("")

    # Priority 5: Investment debate (Bull/Bear)
    debate = final_state.get("investment_debate_state")
    if debate and isinstance(debate, dict):
        lines.append("=" * 60)
        lines.append("【多空辩论】")
        if debate.get("judge_decision"):
            lines.append("研究经理结论: " + str(debate["judge_decision"]))
        if debate.get("bull_history"):
            lines.append("多头观点: " + str(debate["bull_history"])[:2000])
        if debate.get("bear_history"):
            lines.append("空头观点: " + str(debate["bear_history"])[:2000])
        lines.append("")

    # Priority 6: Individual analyst reports
    analyst_fields = [
        ("market_report", "【技术分析报告】"),
        ("sentiment_report", "【市场情绪报告】"),
        ("news_report", "【新闻舆情报告】"),
        ("fundamentals_report", "【基本面分析报告】"),
        ("policy_report", "【政策分析报告】"),
        ("hot_money_report", "【游资追踪报告】"),
        ("lockup_report", "【解禁/减持监控报告】"),
    ]
    for field, label in analyst_fields:
        content = final_state.get(field)
        if content:
            lines.append("=" * 60)
            lines.append(label)
            # Truncate very long reports to keep token cost reasonable
            text = str(content)
            if len(text) > 3000:
                text = text[:3000] + "\n... [内容过长，已截断]"
            lines.append(text)
            lines.append("")

    # Priority 7: Data quality summary
    dqs = final_state.get("data_quality_summary")
    if dqs:
        lines.append("=" * 60)
        lines.append("【数据质量摘要】")
        lines.append(str(dqs)[:2000])
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Markdown code fence stripper
# ---------------------------------------------------------------------------


def strip_markdown_code_fence(text: str) -> str:
    """Remove ```html ... ``` or ``` ... ``` wrappers if present."""
    t = text.strip()
    # Match opening fence with optional language tag
    if t.startswith("```"):
        # Find first newline after opening fence
        first_nl = t.find("\n")
        if first_nl != -1:
            t = t[first_nl + 1 :]
        else:
            t = t[3:]
    # Remove closing fence
    if t.endswith("```"):
        t = t[:-3].strip()
    return t


# ---------------------------------------------------------------------------
# HTML validation
# ---------------------------------------------------------------------------


def validate_html_report(html: str) -> tuple[bool, str]:
    """Lightweight validation. Returns (ok, reason)."""
    if "<!DOCTYPE html>" not in html and "<!doctype html>" not in html.lower():
        return False, "缺少 <!DOCTYPE html>"
    if "<html" not in html.lower() or "</html>" not in html.lower():
        return False, "缺少 <html> 标签"
    if "<style>" not in html.lower():
        return False, "缺少 <style> 标签"
    if "免责声明" not in html:
        return False, "缺少免责声明"
    if "<script" in html.lower():
        return False, "不应包含 <script>"
    # Heuristic: flag if too many English role names remain
    english_labels = [
        "Market Analyst", "News Analyst", "Bull Researcher", "Bear Researcher",
        "Research Manager", "Portfolio Manager", "Aggressive Analyst",
        "Conservative Analyst", "Neutral Analyst", "Social Analyst",
        "Fundamentals Analyst", "Policy Analyst", "Hot Money Tracker",
        "Lockup Watcher",
    ]
    bad_count = sum(1 for label in english_labels if label in html)
    if bad_count >= 3:
        return False, f"仍包含 {bad_count} 处英文角色名"
    return True, ""


# ---------------------------------------------------------------------------
# LLM generation
# ---------------------------------------------------------------------------


def generate_compact_html_report(
    llm: Any,
    final_state: dict[str, Any],
    ticker: str,
    trade_date: str,
    config: dict[str, Any] | None = None,
) -> str:
    """Call the LLM to generate a compact HTML report from final_state.

    Args:
        llm: A LangChain-compatible LLM (e.g. quick_thinking_llm).
        final_state: The complete agent state dict.
        ticker: Stock ticker code.
        trade_date: Analysis date string.
        config: Optional config dict (unused currently, reserved).

    Returns:
        Raw HTML string from the LLM.
    """
    report_source = build_compact_report_source(final_state, ticker, trade_date)

    # Rough token guard: if source is extremely long, truncate further
    max_source_chars = 25000
    if len(report_source) > max_source_chars:
        logger.warning(
            "Report source too long (%d chars), truncating to %d",
            len(report_source),
            max_source_chars,
        )
        report_source = report_source[:max_source_chars] + "\n\n... [内容已截断，请基于已有信息整理]"

    prompt = COMPACT_HTML_REPORT_PROMPT.format(report_source=report_source)

    response = llm.invoke(prompt)
    content = getattr(response, "content", str(response))

    html = strip_markdown_code_fence(content)
    return html


# ---------------------------------------------------------------------------
# File saving
# ---------------------------------------------------------------------------


def _report_dir() -> Path:
    """Return the report output directory (project_root/report)."""
    # Prefer project root resolution via default_config
    try:
        from tradingagents.default_config import DEFAULT_CONFIG

        project_dir = Path(DEFAULT_CONFIG["project_dir"])
    except Exception:
        project_dir = Path.cwd()
    return project_dir / "report"


def save_compact_html_report(
    html: str,
    ticker: str,
    stock_name: str,
    trade_date: str,
) -> Path:
    """Save the compact HTML report to report/<ticker>_<name>_<date>.html.

    Returns the saved file path.
    """
    safe_name = _safe_filename(stock_name) if stock_name else "unknown"
    safe_ticker = _safe_filename(ticker)
    filename = f"{safe_ticker}_{safe_name}_{trade_date}.html"

    report_dir = _report_dir()
    report_dir.mkdir(parents=True, exist_ok=True)

    out_path = report_dir / filename
    out_path.write_text(html, encoding="utf-8")
    logger.info("Compact HTML report saved to %s", out_path)
    return out_path
