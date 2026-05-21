from __future__ import annotations

from typing import Any

import web.components.report_viewer as report_viewer

from web.components.report_viewer import _clean_html_for_embed
from web.components.report_viewer import _copy_guard_html
from web.components.report_viewer import _fix_dark_title_text_color
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


def test_clean_html_for_embed_strengthens_compact_header_title_color() -> None:
    html = """<!DOCTYPE html>
    <html>
      <head>
        <style>
          .header { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: #fff; }
          .header h1 { font-size: 28px; margin-bottom: 10px; }
          .signal-hold { display: inline-block; }
        </style>
      </head>
      <body>
        <div class="container">
          <div class="header">
            <h1>锐捷网络</h1>
            <div class="signal-hold">持有 (HOLD)</div>
          </div>
        </div>
      </body>
    </html>
    """

    rendered = _clean_html_for_embed(html)

    assert '.header h1 { color: #ffffff !important; }' in rendered
    assert rendered.count('.header h1 { color: #ffffff !important; }') == 1


def test_fix_dark_title_text_color_injects_white_when_missing() -> None:
    """Dark background without explicit color → inject white."""
    html = '<div style="background-color: #1a1f3c; padding: 20px;"><h1>贵州茅台</h1></div>'
    fixed = _fix_dark_title_text_color(html)
    assert 'color: #ffffff !important;' in fixed
    assert 'background-color: #1a1f3c' in fixed


def test_fix_dark_title_text_color_replaces_black() -> None:
    """Dark background with black color → replace with white."""
    html = '<div style="background: #2c3e50; color: black; padding: 20px;"><h1>贵州茅台</h1></div>'
    fixed = _fix_dark_title_text_color(html)
    assert 'color: #ffffff !important;' in fixed
    assert 'color: black' not in fixed


def test_fix_dark_title_text_color_replaces_hex_black() -> None:
    """Dark background with #000000 → replace with white."""
    html = '<header style="background-color: #1e3a5f; color: #000000;"><h1>贵州茅台</h1></header>'
    fixed = _fix_dark_title_text_color(html)
    assert 'color: #ffffff !important' in fixed
    assert '#000000' not in fixed


def test_fix_dark_title_text_color_preserves_existing_white() -> None:
    """Dark background already has white color → leave unchanged."""
    html = '<div style="background-color: #0f172a; color: #ffffff;"><h1>贵州茅台</h1></div>'
    fixed = _fix_dark_title_text_color(html)
    # Only the explicit color: #ffffff should remain; no extra injection
    assert fixed.count('color: #ffffff') == 1
    assert 'color: #ffffff' in fixed


def test_fix_dark_title_text_color_ignores_light_background() -> None:
    """Light background without color → do not modify."""
    html = '<div style="background-color: #f8f9fa; padding: 20px;"><h1>贵州茅台</h1></div>'
    fixed = _fix_dark_title_text_color(html)
    # Should not inject a standalone "color:" declaration (background-color is OK)
    assert '; color: #' not in fixed
    assert 'color: #ffffff' not in fixed


def test_fix_dark_title_text_color_only_first_match() -> None:
    """Only the first dark-background element is fixed."""
    html = (
        '<div style="background-color: #1a1f3c; padding: 20px;"><h1>标题</h1></div>'
        '<div style="background-color: #2c3e50; padding: 10px;"><p>正文</p></div>'
    )
    fixed = _fix_dark_title_text_color(html)
    # First div should be fixed
    assert 'color: #ffffff !important;' in fixed
    # Count occurrences: only one injection
    assert fixed.count('color: #ffffff !important;') == 1


def test_fix_dark_title_text_color_with_rgb_dark_background() -> None:
    """RGB dark background without color → inject white."""
    html = '<section style="background-color: rgb(20, 30, 50); padding: 20px;"><h1>贵州茅台</h1></section>'
    fixed = _fix_dark_title_text_color(html)
    assert 'color: #ffffff !important;' in fixed


def test_fix_dark_title_text_color_with_hsl_dark_background() -> None:
    """HSL dark background without color → inject white."""
    html = '<div style="background: hsl(220, 40%, 15%); padding: 20px;"><h1>贵州茅台</h1></div>'
    fixed = _fix_dark_title_text_color(html)
    assert 'color: #ffffff !important;' in fixed
