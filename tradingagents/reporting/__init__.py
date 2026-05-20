"""Reporting utilities for TradingAgents-Astock."""

from .compact_html_report import (
    COMPACT_HTML_REPORT_PROMPT,
    build_compact_report_source,
    generate_compact_html_report,
    get_stock_name,
    save_compact_html_report,
    strip_markdown_code_fence,
    validate_html_report,
)

__all__ = [
    "COMPACT_HTML_REPORT_PROMPT",
    "build_compact_report_source",
    "generate_compact_html_report",
    "get_stock_name",
    "save_compact_html_report",
    "strip_markdown_code_fence",
    "validate_html_report",
]
