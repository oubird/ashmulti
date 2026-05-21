"""Risk assessment Chinese HTML report generation.

Post-processing step: after the pipeline completes,
feed the raw risk_debate_state to an LLM and ask it to produce a
well-formatted Chinese HTML risk report.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from tradingagents.reporting.compact_html_report import (
    _safe_filename,
    _report_dir,
    get_stock_name,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

RISK_HTML_PROMPT = """你是一个专业的 A 股风控报告整理员。
你的任务是把输入的英文风控评估辩论内容，翻译成一份专业、正式的中文 HTML 报告。

## 整理规则（必须遵守）

1. 只基于输入内容翻译整理，不得编造新数据、新指标。
2. 删除所有英文角色名，例如：Aggressive Analyst、Conservative Analyst、Neutral Analyst、Risk Judge 等。用中文描述替代：激进观点、保守观点、中性观点、风控决策。
3. 删除模型过程语，例如："Let me analyze"、"Based on the data"、"I think" 等。
4. 所有英文内容必须翻译成中文，不得保留任何未翻译的英文段落。
5. 输出必须是完整 HTML 文件，不要 Markdown，不要用代码块包裹。
6. HTML 里的 CSS 直接写在 `<style>` 标签里，不依赖外部文件。
7. 视觉风格：白底黑字，配色克制专业。风险区域用浅红色背景 + 深红色边框。
8. 字体使用系统默认无衬线字体（font-family: -apple-system, BlinkMacSystemFont, "Noto Sans SC", "Segoe UI", Roboto, sans-serif）。
9. 整体宽度 max-width: 900px，居中显示。适当的 padding 和 margin。

## HTML 结构要求

请按以下结构生成 HTML：

1. **标题区**
   - 风控评估报告
   - 股票代码（如提供）
   - 分析日期（如提供）

2. **四方观点对比表**
   用清晰的两行两列表格或卡片布局：
   - 激进观点（看多/激进风险承受）
   - 保守观点（看空/谨慎风险承受）
   - 中性观点（平衡视角）
   - 风控决策（最终结论）

3. **核心风险摘要**
   - 主要风险点列表
   - 风险等级评估
   - 关键数据支撑

4. **风险提示区域**
   用醒目的红色区域列出关键风险警告。

## 输入数据

以下是从 TradingAgents-Astock 系统输出的风控评估原始英文辩论内容，请据此整理：

{report_source}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_risk_source(risk_debate_state: dict[str, Any]) -> str:
    """Extract risk debate content for the LLM prompt."""
    lines: list[str] = []
    if not risk_debate_state:
        lines.append("无风控评估数据")
        return "\n".join(lines)

    for key, label in (
        ("aggressive_history", "激进观点"),
        ("conservative_history", "保守观点"),
        ("neutral_history", "中性观点"),
        ("judge_decision", "风控决策"),
    ):
        content = risk_debate_state.get(key, "")
        if content:
            lines.append(f"{'='*40}")
            lines.append(f"【{label}】")
            text = str(content)
            if len(text) > 5000:
                text = text[:5000] + "\n... [内容过长，已截断]"
            lines.append(text)
            lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Markdown code fence stripper (reused)
# ---------------------------------------------------------------------------


def _strip_md_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        first_nl = t.find("\n")
        t = t[first_nl + 1 :] if first_nl != -1 else t[3:]
    if t.endswith("```"):
        t = t[:-3].strip()
    return t


# ---------------------------------------------------------------------------
# LLM generation
# ---------------------------------------------------------------------------


def generate_risk_html_report(
    llm: Any,
    risk_debate_state: dict[str, Any],
) -> str:
    """Call the LLM to generate a Chinese HTML risk report.

    Args:
        llm: A LangChain-compatible LLM.
        risk_debate_state: The risk debate dict from final_state.

    Returns:
        Raw HTML string from the LLM.
    """
    report_source = _build_risk_source(risk_debate_state)
    prompt = RISK_HTML_PROMPT.format(report_source=report_source)
    response = llm.invoke(prompt)
    content = getattr(response, "content", str(response))
    return _strip_md_fence(content)


# ---------------------------------------------------------------------------
# File saving / resolving
# ---------------------------------------------------------------------------


def save_risk_html_report(
    html: str,
    ticker: str,
    stock_name: str,
    trade_date: str,
) -> Path:
    """Save the risk HTML report to report/<ticker>_<name>_risk_<date>.html."""
    safe_name = _safe_filename(stock_name) if stock_name else "unknown"
    safe_ticker = _safe_filename(ticker)
    filename = f"{safe_ticker}_{safe_name}_risk_{trade_date}.html"

    report_dir = _report_dir()
    report_dir.mkdir(parents=True, exist_ok=True)

    out_path = report_dir / filename
    out_path.write_text(html, encoding="utf-8")
    logger.info("Risk HTML report saved to %s", out_path)
    return out_path


def _resolve_risk_html_report(ticker: str, trade_date: str) -> tuple[bool, bytes]:
    """Return (exists, bytes) for the risk HTML report."""
    stock_name = get_stock_name(ticker)
    safe_name = _safe_filename(stock_name) if stock_name else "unknown"
    html_file = _report_dir() / f"{_safe_filename(ticker)}_{safe_name}_risk_{trade_date}.html"
    if html_file.exists():
        return True, html_file.read_bytes()
    return False, b""
