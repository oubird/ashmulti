"""Tests for web task persistence, history merge, and runner regressions."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from web.history import get_history
from web.runner import _run
from web.task_store import (
    build_resume_config,
    continue_mode,
    create_task_record,
    delete_task_artifacts,
    display_status,
    save_task_record,
)


class TestWebTaskHistory(unittest.TestCase):
    def test_history_merges_completed_and_interrupted_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            report_dir = home / "reports"
            results_dir = home / ".tradingagents" / "logs"
            report_dir.mkdir(parents=True, exist_ok=True)
            results_dir.mkdir(parents=True, exist_ok=True)

            ticker_done = "000001"
            date_done = "2026-05-20"
            stock_name = "TestCo"
            ticker_stop = "000002"
            date_stop = "2026-05-19"

            config = {"results_dir": str(results_dir), "data_cache_dir": str(home / "cache")}
            with patch("pathlib.Path.home", return_value=home):
                done_record = create_task_record(ticker_done, date_done, config, ["market"], stock_name=stock_name)
                save_task_record(done_record)

                log_dir = results_dir / ticker_done / "TradingAgentsStrategy_logs"
                log_dir.mkdir(parents=True, exist_ok=True)
                log_path = log_dir / f"full_states_log_{date_done}.json"
                log_path.write_text(
                    json.dumps(
                        {
                            "stock_name": stock_name,
                            "elapsed_seconds": 125.0,
                            "analysis_mode": "深度",
                            "final_trade_decision": "BUY",
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                (report_dir / f"{ticker_done}_{stock_name}_{date_done}.html").write_text("<html>compact</html>", encoding="utf-8")
                (report_dir / f"{ticker_done}_{stock_name}_risk_{date_done}.html").write_text("<html>risk</html>", encoding="utf-8")

                stopped_record = create_task_record(
                    ticker_stop,
                    date_stop,
                    config,
                    ["market"],
                    stock_name="StopCo",
                )
                stopped_record.update(
                    {
                        "status": "interrupted",
                        "analysis_complete": False,
                        "report_complete": False,
                        "is_running": False,
                        "is_complete": False,
                        "error": "用户已取消",
                    }
                )
                save_task_record(stopped_record)

            with patch("pathlib.Path.home", return_value=home), patch("web.history._get_code_to_name_map", return_value={}), patch(
                "web.history._report_dir", return_value=report_dir
            ):
                history = get_history(limit=20)

            rows = {(entry["ticker"], entry["date"]): entry for entry in history}
            self.assertIn((ticker_done, date_done), rows)
            self.assertIn((ticker_stop, date_stop), rows)

            done_entry = rows[(ticker_done, date_done)]
            self.assertEqual(done_entry["status_label"], "完成")
            self.assertEqual(done_entry["view_mode"], "report")
            self.assertEqual(done_entry["continue_mode"], "none")
            self.assertFalse(done_entry["can_continue"])

            stop_entry = rows[(ticker_stop, date_stop)]
            self.assertEqual(stop_entry["status_label"], "中断")
            self.assertEqual(stop_entry["view_mode"], "task")
            self.assertEqual(stop_entry["continue_mode"], "resume")
            self.assertTrue(stop_entry["can_continue"])

    def test_status_and_continue_modes_cover_repair_and_completed(self) -> None:
        interrupted = {
            "status": "interrupted",
            "analysis_complete": False,
            "report_complete": False,
            "report_error": "",
        }
        repairable = {
            "status": "recoverable",
            "analysis_complete": True,
            "report_complete": False,
            "report_error": "报告生成失败",
        }
        completed = {
            "status": "completed",
            "analysis_complete": True,
            "report_complete": True,
            "report_error": "",
        }

        self.assertEqual(display_status(interrupted), "中断")
        self.assertEqual(continue_mode(interrupted), "resume")
        self.assertEqual(display_status(repairable), "可恢复")
        self.assertEqual(continue_mode(repairable), "repair")
        self.assertEqual(display_status(completed), "完成")
        self.assertEqual(continue_mode(completed), "none")
        self.assertEqual(
            continue_mode(
                {
                    "status": "completed",
                    "analysis_complete": True,
                    "report_complete": False,
                    "report_error": "compact failed",
                }
            ),
            "repair",
        )

    def test_delete_requested_rows_are_hidden_from_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            report_dir = home / "reports"
            results_dir = home / ".tradingagents" / "logs"
            report_dir.mkdir(parents=True, exist_ok=True)
            results_dir.mkdir(parents=True, exist_ok=True)

            ticker = "000005"
            trade_date = "2026-05-16"
            stock_name = "HiddenCo"
            config = {"results_dir": str(results_dir), "data_cache_dir": str(home / "cache")}

            with patch("pathlib.Path.home", return_value=home):
                record = create_task_record(ticker, trade_date, config, ["market"], stock_name=stock_name)
                record["delete_requested"] = True
                save_task_record(record)

                log_dir = results_dir / ticker / "TradingAgentsStrategy_logs"
                log_dir.mkdir(parents=True, exist_ok=True)
                log_path = log_dir / f"full_states_log_{trade_date}.json"
                log_path.write_text(
                    json.dumps({"stock_name": stock_name, "elapsed_seconds": 30.0, "analysis_mode": "快速"}, ensure_ascii=False),
                    encoding="utf-8",
                )
                (report_dir / f"{ticker}_{stock_name}_{trade_date}.html").write_text("<html>compact</html>", encoding="utf-8")
                (report_dir / f"{ticker}_{stock_name}_risk_{trade_date}.html").write_text("<html>risk</html>", encoding="utf-8")

            with patch("pathlib.Path.home", return_value=home), patch("web.history._get_code_to_name_map", return_value={}), patch(
                "web.history._report_dir", return_value=report_dir
            ):
                history = get_history(limit=20)

            self.assertNotIn((ticker, trade_date), {(entry["ticker"], entry["date"]): entry for entry in history})


class TestWebTaskDeletion(unittest.TestCase):
    def test_delete_task_artifacts_removes_generated_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            results_dir = home / "results"
            report_dir = home / "reports"
            cache_dir = home / "cache"
            results_dir.mkdir(parents=True, exist_ok=True)
            report_dir.mkdir(parents=True, exist_ok=True)
            cache_dir.mkdir(parents=True, exist_ok=True)

            ticker = "000003"
            trade_date = "2026-05-18"
            stock_name = "DeleteCo"
            config = {"results_dir": str(results_dir), "data_cache_dir": str(cache_dir)}

            with patch("pathlib.Path.home", return_value=home):
                record = create_task_record(ticker, trade_date, config, ["market"], stock_name=stock_name)
                save_task_record(record)

                task_path = Path(record["task_path"])
                log_path = results_dir / ticker / "TradingAgentsStrategy_logs" / f"full_states_log_{trade_date}.json"
                report_path = report_dir / f"{ticker}_{stock_name}_{trade_date}.html"
                risk_path = report_dir / f"{ticker}_{stock_name}_risk_{trade_date}.html"

                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text("{}", encoding="utf-8")
                report_path.write_text("<html>compact</html>", encoding="utf-8")
                risk_path.write_text("<html>risk</html>", encoding="utf-8")
                task_path.parent.mkdir(parents=True, exist_ok=True)
                task_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

            with patch("pathlib.Path.home", return_value=home), patch("web.task_store._report_dir", return_value=report_dir), patch(
                "web.task_store.clear_checkpoint"
            ) as mock_clear:
                delete_task_artifacts(
                    {
                        **record,
                        "task_path": str(task_path),
                        "final_state_path": str(log_path),
                    }
                )

            mock_clear.assert_called_once_with(str(cache_dir), ticker, trade_date)
            self.assertFalse(task_path.exists())
            self.assertFalse(log_path.exists())
            self.assertFalse(report_path.exists())
            self.assertFalse(risk_path.exists())


class TestWebRunnerRegression(unittest.TestCase):
    def test_run_creates_task_record_without_scope_error(self) -> None:
        class _StubStats:
            def get_stats(self) -> dict[str, int]:
                return {"llm_calls": 0, "tool_calls": 0, "tokens_in": 0, "tokens_out": 0}

        class _StubPropagator:
            def create_initial_state(self, ticker: str, trade_date: str) -> dict[str, str]:
                return {"ticker": ticker, "trade_date": trade_date}

            def get_graph_args(self, callbacks=None) -> dict[str, object]:
                return {}

        class _StubWorkflow:
            def compile(self, checkpointer=None):
                return self

        class _StubGraph:
            def __init__(self, *args, **kwargs):
                self.propagator = _StubPropagator()
                self.workflow = _StubWorkflow()
                self.graph = self
                self.quick_thinking_llm = object()
                self.ticker = ""

            def stream(self, init_state, **kwargs):
                if False:  # pragma: no cover - the stream is intentionally empty
                    yield init_state
                return

            def process_signal(self, text: str) -> str:
                return "Hold"

            def _log_state(self, *args, **kwargs) -> None:
                return None

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            config = {
                "checkpoint_enabled": False,
                "results_dir": str(home / "results"),
                "data_cache_dir": str(home / "cache"),
            }
            ticker = "000004"
            trade_date = "2026-05-17"
            task_path = home / ".tradingagents" / "web_tasks" / ticker / f"{trade_date}.json"

            with patch("pathlib.Path.home", return_value=home), patch("web.runner._build_runtime_config", return_value=config), patch(
                "web.runner.get_stock_name", return_value="Test Stock"
            ), patch("cli.stats_handler.StatsCallbackHandler", return_value=_StubStats()), patch(
                "tradingagents.graph.trading_graph.TradingAgentsGraph", _StubGraph
            ):
                from web.progress import ProgressTracker

                tracker = ProgressTracker(ticker=ticker, trade_date=trade_date)
                with self.assertRaisesRegex(RuntimeError, "分析没有返回任何结果"):
                    _run(
                        ticker=ticker,
                        trade_date=trade_date,
                        config=config,
                        tracker=tracker,
                        selected_analysts=["market"],
                    )

            self.assertTrue(task_path.exists())
            saved = json.loads(task_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["stock_name"], "Test Stock")
            self.assertEqual(saved["task_key"], f"{ticker}__{trade_date}")


if __name__ == "__main__":
    unittest.main()
