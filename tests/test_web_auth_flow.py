"""Tests for authentication, role routing, admin CRUD, and password change."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web.auth_store import (
    init_auth_db,
    ensure_default_users,
    verify_password,
    create_user,
    update_user,
    delete_user,
    list_users,
    get_user_by_id,
    change_password,
    admin_reset_password,
)


class TestAuthStore(unittest.TestCase):
    def test_default_admin_created(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch("pathlib.Path.home", return_value=home):
                init_auth_db()
                ensure_default_users()
                users = list_users()
                usernames = {u["username"] for u in users}
                self.assertEqual(usernames, {"admin"})

    def test_verify_password_correct(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch("pathlib.Path.home", return_value=home):
                init_auth_db()
                ensure_default_users()
                user = verify_password("admin", "Admin@123!")
                self.assertIsNotNone(user)
                self.assertEqual(user["username"], "admin")
                self.assertTrue(user["must_change_password"])

    def test_verify_password_wrong(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch("pathlib.Path.home", return_value=home):
                init_auth_db()
                ensure_default_users()
                self.assertIsNone(verify_password("admin", "wrong"))
                self.assertIsNone(verify_password("nobody", "Admin@123!"))

    def test_create_user_and_duplicate_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch("pathlib.Path.home", return_value=home):
                init_auth_db()
                ensure_default_users()
                admin = verify_password("admin", "Admin@123!")
                u = create_user("tester", "password123", "user", admin["id"])
                self.assertEqual(u["username"], "tester")
                self.assertEqual(u["role"], "user")
                with self.assertRaises(ValueError):
                    create_user("tester", "password123", "user", admin["id"])

    def test_delete_user_protections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch("pathlib.Path.home", return_value=home):
                init_auth_db()
                ensure_default_users()
                admin = verify_password("admin", "Admin@123!")
                # Cannot delete self
                with self.assertRaises(ValueError):
                    delete_user(admin["id"], admin["id"])
                # Cannot delete last admin
                with self.assertRaises(ValueError):
                    delete_user(admin["id"], admin["id"])

    def test_admin_cannot_delete_last_admin_even_with_multiple(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch("pathlib.Path.home", return_value=home):
                init_auth_db()
                ensure_default_users()
                admin = verify_password("admin", "Admin@123!")
                u2 = create_user("admin2", "password123", "admin", admin["id"])
                # Disable second admin
                update_user(u2["id"], enabled=0)
                # Now only one enabled admin remains → cannot delete
                with self.assertRaises(ValueError):
                    delete_user(admin["id"], admin["id"])

    def test_change_password(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch("pathlib.Path.home", return_value=home):
                init_auth_db()
                ensure_default_users()
                admin = verify_password("admin", "Admin@123!")
                # Wrong old password
                with self.assertRaises(ValueError):
                    change_password(admin["id"], "wrong", "NewPass123")
                # Correct old password
                change_password(admin["id"], "Admin@123!", "NewPass123")
                self.assertIsNotNone(verify_password("admin", "NewPass123"))
                self.assertIsNone(verify_password("admin", "Admin@123!"))

    def test_admin_reset_password(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch("pathlib.Path.home", return_value=home):
                init_auth_db()
                ensure_default_users()
                admin = verify_password("admin", "Admin@123!")
                tester = create_user("tester", "password123", "user", admin["id"])
                admin_reset_password(tester["id"], "Reset123")
                user = verify_password("tester", "Reset123")
                self.assertIsNotNone(user)
                self.assertTrue(user["must_change_password"])

    def test_disable_user_blocks_login(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch("pathlib.Path.home", return_value=home):
                init_auth_db()
                ensure_default_users()
                admin = verify_password("admin", "Admin@123!")
                tester = create_user("tester", "password123", "user", admin["id"])
                update_user(tester["id"], enabled=0)
                self.assertIsNone(verify_password("tester", "password123"))


if __name__ == "__main__":
    unittest.main()
