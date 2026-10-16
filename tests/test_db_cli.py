"""현재 scripts/db.py CLI 동작을 Docker 없이 검사한다."""

import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


SCRIPT_PATH = (
    Path(__file__)
    .resolve()
    .parents[1]
    / "scripts"
    / "db.py"
)

spec = (
    importlib.util.spec_from_file_location(
        "db_cli",
        SCRIPT_PATH,
    )
)

db = (
    importlib.util.module_from_spec(
        spec
    )
)

spec.loader.exec_module(
    db
)


class DatabaseUtilityTests(
    unittest.TestCase
):
    def test_tables_action(
        self,
    ):
        with (
            patch(
                "sys.argv",
                [
                    "db.py",
                    "tables",
                ],
            ),
            patch.object(
                db,
                "show_tables",
            ) as show_tables,
        ):

            self.assertEqual(
                db.main(),
                0,
            )

            show_tables.assert_called_once_with()

    def test_verify_action(
        self,
    ):
        with (
            patch(
                "sys.argv",
                [
                    "db.py",
                    "verify",
                ],
            ),
            patch.object(
                db,
                "verify_schema",
            ) as verify_schema,
        ):

            self.assertEqual(
                db.main(),
                0,
            )

            verify_schema.assert_called_once_with()

    def test_backup_action(
        self,
    ):
        with (
            patch(
                "sys.argv",
                [
                    "db.py",
                    "backup",
                ],
            ),
            patch.object(
                db,
                "backup",
            ) as backup,
        ):

            self.assertEqual(
                db.main(),
                0,
            )

            backup.assert_called_once_with()

    def test_backup_failure_returns_error(
        self,
    ):
        with (
            patch(
                "sys.argv",
                [
                    "db.py",
                    "backup",
                ],
            ),
            patch.object(
                db,
                "backup",
                side_effect=(
                    RuntimeError(
                        "backup failed"
                    )
                ),
            ),
        ):

            self.assertEqual(
                db.main(),
                1,
            )

    def test_docker_command_failure_returns_error(
        self,
    ):
        with (
            patch(
                "sys.argv",
                [
                    "db.py",
                    "tables",
                ],
            ),
            patch.object(
                db,
                "show_tables",
                side_effect=(
                    subprocess
                    .CalledProcessError(
                        1,
                        "docker",
                    )
                ),
            ),
        ):

            self.assertEqual(
                db.main(),
                1,
            )


if __name__ == "__main__":
    unittest.main()