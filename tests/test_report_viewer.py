from __future__ import annotations

from web.components.report_viewer import _clean_html_for_embed


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
