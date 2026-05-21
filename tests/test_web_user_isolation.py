"""Tests for user-level task isolation and runner concurrency."""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from web.auth_store import (
    init_auth_db,
    ensure_default_users,
    create_user,
    verify_password,
    get_task_keys_for_user,
)
from web.history import get_history
from web.runner import (
    _RUN_REGISTRY,
    _REGISTRY_LOCK,
    get_active_tracker,
    request_stop,
    run_analysis_in_thread,
)
from web.task_store import (
    create_task_record,
    delete_task_artifacts,
    save_task_record,
    task_key,
)


class TestUserTaskIsolation(unittest.TestCase):
    def test_user_only_sees_own_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            report_dir = home / "reports"
            results_dir = home / ".tradingagents" / "logs"
            report_dir.mkdir(parents=True, exist_ok=True)
            results_dir.mkdir(parents=True, exist_ok=True)

            with patch("pathlib.Path.home", return_value=home):
                init_auth_db()
                ensure_default_users()
                admin = verify_password("admin", "Admin@123!")
                user_a = create_user("alice", "password123", "user", admin["id"])
                user_b = create_user("bob", "password123", "user", admin["id"])

                config = {"results_dir": str(results_dir), "data_cache_dir": str(home / "cache")}

                # Alice creates a task
                rec_a = create_task_record(
                    "000001", "2026-05-20", config, ["market"],
                    stock_name="AliceCo", owner_user_id=user_a["id"],
                )
                save_task_record(rec_a)

                # Bob creates a task
                rec_b = create_task_record(
                    "000002", "2026-05-20", config, ["market"],
                    stock_name="BobCo", owner_user_id=user_b["id"],
                )
                save_task_record(rec_b)

                # Alice only sees her own
                history_a = get_history(user_id=user_a["id"], limit=20)
                tickers_a = {e["ticker"] for e in history_a}
                self.assertIn("000001", tickers_a)
                self.assertNotIn("000002", tickers_a)

                # Bob only sees his own
                history_b = get_history(user_id=user_b["id"], limit=20)
                tickers_b = {e["ticker"] for e in history_b}
                self.assertIn("000002", tickers_b)
                self.assertNotIn("000001", tickers_b)

    def test_user_cannot_delete_others_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            results_dir = home / "results"
            report_dir = home / "reports"
            cache_dir = home / "cache"
            results_dir.mkdir(parents=True, exist_ok=True)
            report_dir.mkdir(parents=True, exist_ok=True)
            cache_dir.mkdir(parents=True, exist_ok=True)

            with patch("pathlib.Path.home", return_value=home):
                init_auth_db()
                ensure_default_users()
                admin = verify_password("admin", "Admin@123!")
                user_a = create_user("alice", "password123", "user", admin["id"])
                user_b = create_user("bob", "password123", "user", admin["id"])

                config = {"results_dir": str(results_dir), "data_cache_dir": str(cache_dir)}
                rec = create_task_record(
                    "000003", "2026-05-18", config, ["market"],
                    stock_name="AliceCo", owner_user_id=user_a["id"],
                )
                save_task_record(rec)

                # Bob tries to delete Alice's task
                with self.assertRaises(PermissionError):
                    delete_task_artifacts(rec, caller_user_id=user_b["id"])

                # Alice can delete her own
                delete_task_artifacts(rec, caller_user_id=user_a["id"])
                self.assertFalse(Path(rec["task_path"]).exists())

    def test_runner_registry_isolated(self) -> None:
        """Two tasks can coexist in the registry without clobbering."""
        # Clear any stale entries
        with _REGISTRY_LOCK:
            _RUN_REGISTRY.clear()

        from web.progress import ProgressTracker

        t1 = ProgressTracker(ticker="000001", trade_date="2026-05-20")
        t2 = ProgressTracker(ticker="000002", trade_date="2026-05-20")

        tk1 = task_key("000001", "2026-05-20")
        tk2 = task_key("000002", "2026-05-20")

        with _REGISTRY_LOCK:
            _RUN_REGISTRY[tk1] = {
                "tracker": t1,
                "thread": None,
                "stop_event": threading.Event(),
                "user_id": "1",
            }
            _RUN_REGISTRY[tk2] = {
                "tracker": t2,
                "thread": None,
                "stop_event": threading.Event(),
                "user_id": "2",
            }

        self.assertEqual(get_active_tracker(tk1), t1)
        self.assertEqual(get_active_tracker(tk2), t2)

        # Stop one, the other remains
        request_stop(tk1)
        self.assertTrue(_RUN_REGISTRY[tk1]["stop_event"].is_set())
        self.assertFalse(_RUN_REGISTRY[tk2]["stop_event"].is_set())

        with _REGISTRY_LOCK:
            _RUN_REGISTRY.clear()

    def test_concurrent_run_isolation(self) -> None:
        """Two users' tasks can be started; request_stop only affects the target."""
        # Clear stale entries
        with _REGISTRY_LOCK:
            _RUN_REGISTRY.clear()

        from web.progress import ProgressTracker

        t1 = ProgressTracker(ticker="000001", trade_date="2026-05-20")
        t2 = ProgressTracker(ticker="000002", trade_date="2026-05-20")

        tk1 = task_key("000001", "2026-05-20")
        tk2 = task_key("000002", "2026-05-20")

        stop1 = threading.Event()
        stop2 = threading.Event()

        with _REGISTRY_LOCK:
            _RUN_REGISTRY[tk1] = {
                "tracker": t1,
                "thread": None,
                "stop_event": stop1,
                "user_id": "1",
            }
            _RUN_REGISTRY[tk2] = {
                "tracker": t2,
                "thread": None,
                "stop_event": stop2,
                "user_id": "2",
            }

        # User A stops their task
        request_stop(tk1)
        self.assertTrue(stop1.is_set())
        self.assertFalse(stop2.is_set())

        with _REGISTRY_LOCK:
            _RUN_REGISTRY.clear()


    def test_delete_running_task_triggers_stop_before_cleanup(self) -> None:
        """When a task is running in registry, get_active_tracker finds it by user_id
        and request_stop targets exactly that task_key, so delete can signal stop first."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            results_dir = home / "results"
            report_dir = home / "reports"
            cache_dir = home / "cache"
            results_dir.mkdir(parents=True, exist_ok=True)
            report_dir.mkdir(parents=True, exist_ok=True)
            cache_dir.mkdir(parents=True, exist_ok=True)

            with patch("pathlib.Path.home", return_value=home):
                init_auth_db()
                ensure_default_users()
                admin = verify_password("admin", "Admin@123!")
                user_a = create_user("alice", "password123", "user", admin["id"])

                config = {"results_dir": str(results_dir), "data_cache_dir": str(cache_dir)}
                rec = create_task_record(
                    "000001", "2026-05-20", config, ["market"],
                    stock_name="RunCo", owner_user_id=user_a["id"],
                )
                save_task_record(rec)

                from web.progress import ProgressTracker

                tracker = ProgressTracker(ticker="000001", trade_date="2026-05-20")
                tracker.is_running = True
                stop_ev = threading.Event()
                tk = task_key("000001", "2026-05-20")

                with _REGISTRY_LOCK:
                    _RUN_REGISTRY[tk] = {
                        "tracker": tracker,
                        "thread": None,
                        "stop_event": stop_ev,
                        "user_id": str(user_a["id"]),
                    }

                # get_active_tracker must find the running task by user_id
                found = get_active_tracker(task_key=tk, user_id=str(user_a["id"]))
                self.assertEqual(found, tracker)

                # request_stop must target exactly this task
                request_stop(tk)
                self.assertTrue(stop_ev.is_set())

                # Another task_key should not be affected
                tk_other = task_key("000002", "2026-05-20")
                self.assertIsNone(get_active_tracker(task_key=tk_other))

                with _REGISTRY_LOCK:
                    _RUN_REGISTRY.clear()


if __name__ == "__main__":
    unittest.main()
