"""One-off script: translate existing risk assessments to Chinese HTML.

Usage:
    python scripts/batch_translate_risk.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Ensure project root is on path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from tradingagents.llm_clients.factory import create_llm_client
from tradingagents.reporting.compact_html_report import get_stock_name, _safe_filename
from tradingagents.reporting.risk_html_report import (
    generate_risk_html_report,
    save_risk_html_report,
)


def _results_dir() -> Path:
    return Path.home() / ".tradingagents" / "logs"


def main() -> None:
    root = _results_dir()
    if not root.exists():
        print("No history found.")
        return

    log_files = list(root.rglob("full_states_log_*.json"))
    if not log_files:
        print("No history files found.")
        return

    print(f"Found {len(log_files)} history file(s). Starting translation...\n")

    # Use MiniMax Anthropic endpoint (same as web UI)
    client = create_llm_client(
        provider="anthropic",
        model="claude-sonnet-4-6",
        base_url="https://api.minimaxi.com/anthropic",
    )
    llm = client.get_llm()

    for log_file in log_files:
        match = re.search(r"full_states_log_(\d{4}-\d{2}-\d{2})\.json$", log_file.name)
        if not match:
            continue
        trade_date = match.group(1)
        ticker = log_file.parent.parent.name

        print(f"Processing {ticker} @ {trade_date} ...", end=" ")

        try:
            with open(log_file, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            print(f"SKIP (load error: {exc})")
            continue

        risk_state = data.get("risk_debate_state", {})
        if not risk_state:
            print("SKIP (no risk data)")
            continue

        # Check if already translated
        stock_name = get_stock_name(ticker)
        safe_name = _safe_filename(stock_name) if stock_name else "unknown"
        out_path = (
            Path(__file__).resolve().parent.parent
            / "report"
            / f"{_safe_filename(ticker)}_{safe_name}_risk_{trade_date}.html"
        )
        if out_path.exists():
            print("SKIP (already exists)")
            continue

        try:
            html = generate_risk_html_report(llm, risk_state)
            save_risk_html_report(html, ticker, stock_name, trade_date)
            print("OK")
        except Exception as exc:
            print(f"FAIL ({exc})")

    print("\nDone.")


if __name__ == "__main__":
    main()
