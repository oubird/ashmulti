from __future__ import annotations

from typing import Any

import web.components.report_viewer as report_viewer

from web.components.report_viewer import _clean_html_for_embed
from web.components.report_viewer import _copy_guard_html
from web.components.report_viewer import _inject_copy_guard


def test_copy_guard_html_blocks_streamlit_clear_cache_hotkey() -> None:
    html = _copy_guard_html()

    assert 'data-testid="ta-report-copy-guard-root"' in html
    assert 'const flagName = "__taCopyGuardInstalled";' in html
    assert 'window.addEventListener("keydown", handleKeyEvent, true);' in html
    assert 'window.addEventListener("keyup", handleKeyEvent, true);' in html
    assert 'document.addEventListener("keydown", handleKeyEvent, true);' in html
    assert 'document.addEventListener("keyup", handleKeyEvent, true);' in html
    assert "window.getSelection" in html
    assert "key === \"c\" || event.code === \"KeyC\"" in html
    assert "event.stopPropagation();" in html
    assert "event.stopImmediatePropagation();" in html
    assert "event.cancelBubble = true;" in html
    assert "ctrlKey" in html
    assert "metaKey" in html
    assert "preventDefault" not in html


def test_inject_copy_guard_uses_streamlit_html(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def fake_html(body: str, **kwargs: Any) -> None:
        captured["body"] = body
        captured["kwargs"] = kwargs

    monkeypatch.setattr(report_viewer.st, "html", fake_html)

    _inject_copy_guard()

    assert captured["kwargs"]["unsafe_allow_javascript"] is True
    assert captured["kwargs"]["width"] == "content"
    assert 'data-testid="ta-report-copy-guard-root"' in captured["body"]
    assert "handleKeyEvent" in captured["body"]


def test_clean_html_for_embed_wraps_report_and_injects_compact_table_css() -> None:
    html = """<!DOCTYPE html>
    <html>
      <head><style>table { width: 100%; }</style></head>
      <body><table><tr><th>列</th><td>值</td></tr></table></body>
    </html>
    """

    rendered = _clean_html_for_embed(html)

    assert '<div class="report-embed">' in rendered
    assert "table-layout: auto !important;" in rendered
    assert "display: inline-table !important;" in rendered
    assert "div[data-testid=\"stMarkdownContainer\"] table" in rendered
    assert "<html" not in rendered.lower()
    assert "<body" not in rendered.lower()
