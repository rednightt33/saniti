import importlib.util
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("stockbit_marketwide_broker_activity.py")
SPEC = importlib.util.spec_from_file_location("stockbit_broker_activity", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class AuthenticationStopTests(unittest.TestCase):
    def test_authentication_limit_stops_without_needs_review(self):
        with tempfile.TemporaryDirectory() as directory:
            status_path = Path(directory) / "status.json"
            args = SimpleNamespace(
                from_date=date(2020, 12, 30),
                to_date=date(2020, 12, 30),
                date_order="descending",
                boards=("REGULER",),
                investors=("DOMESTIC",),
                workers=1,
                delay=0.0,
                timeout=1.0,
                page_limit=1000,
                expected_brokers=0,
                database_url_env="DATABASE_URL",
                schema="public",
                table="IDX_Broker_Summary",
                log_table="stockbit_broker_summary_load_log",
                daily_output_dir=Path(directory),
                no_daily_export=True,
                refresh_completed_dates=False,
                check_database_only=False,
                token_stdin=False,
                date_retries=3,
                authentication_failure_limit=5,
                retry_base_seconds=0.0,
                status_file=status_path,
            )
            connection = FakeConnection()
            target = MODULE.TargetTable(
                schema="public",
                table="IDX_Broker_Summary",
                columns={key: key for key in MODULE.CANONICAL_KEYS},
                data_types={key: "text" for key in MODULE.CANONICAL_KEYS},
                generated=frozenset(),
            )

            with (
                patch.object(MODULE, "parse_args", return_value=args),
                patch.object(MODULE, "connect_database", return_value=connection),
                patch.object(MODULE, "resolve_target_table", return_value=target),
                patch.object(MODULE, "create_load_log"),
                patch.object(MODULE, "completed_dates", return_value=set()),
                patch.object(MODULE, "StockbitFetcher") as fetcher_class,
                patch.object(
                    MODULE,
                    "fetch_date",
                    side_effect=MODULE.StockbitAuthenticationLimitError(
                        "Stockbit authentication failed 5 consecutive times (last HTTP 401)"
                    ),
                ),
                patch.object(MODULE, "record_needs_review") as record_needs_review,
                patch.dict(os.environ, {"DATABASE_URL": "postgresql://test", "STOCKBIT_TOKEN": "a.b.c"}),
            ):
                fetcher_class.return_value.broker_directory.return_value = []
                exit_code = MODULE.main()

            self.assertEqual(exit_code, 3)
            self.assertTrue(connection.closed)
            record_needs_review.assert_not_called()
            self.assertEqual(MODULE.json.loads(status_path.read_text())["state"], "STOPPED_INVALID_TOKEN")


if __name__ == "__main__":
    unittest.main()
