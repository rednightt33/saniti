import io
import json
import unittest

from telegram_trigger import (
    CommandSpec,
    IncomingCommand,
    TelegramTrigger,
    extract_incoming_command,
    extract_feature04_action,
    extract_pg_action,
    menu_markup,
    trigger_railway_run,
    wib_times,
)


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


class TelegramTriggerTests(unittest.TestCase):
    def test_extracts_button_command(self):
        command = extract_incoming_command(
            {
                "update_id": 100,
                "callback_query": {
                    "id": "callback-1",
                    "data": "run_price",
                    "message": {"chat": {"id": 709656232}},
                },
            }
        )
        self.assertEqual(
            command,
            IncomingCommand(100, "709656232", "RUN_PRICE", "callback-1"),
        )

    def test_extracts_typed_recovery_command(self):
        command = extract_incoming_command(
            {"update_id": 101, "message": {"chat": {"id": 709656232}, "text": "/run_recovery"}}
        )
        self.assertEqual(command.command, "RUN_RECOVERY")

    def test_menu_contains_only_allowlisted_commands(self):
        callbacks = [row[0]["callback_data"] for row in menu_markup()["inline_keyboard"]]
        self.assertEqual(callbacks, ["run_price", "run_recovery", "f04:status", "restart_postgres", "pg:status"])

    def test_extracts_feature04_column_retry(self):
        action = extract_feature04_action({
            "update_id": 202,
            "callback_query": {"id": "cb", "data": "f04:c:equity:BBCA.JK:adx_14",
                               "message": {"chat": {"id": 123}}},
        })
        self.assertEqual(action, (202, "123", "f04:c:equity:BBCA.JK:adx_14", "cb"))

    def test_feature04_retry_does_not_call_railway(self):
        retried = []
        triggered = []
        acknowledgements = []
        service = TelegramTrigger(
            "db", "bot", "123", "railway", {},
            feature_retry=lambda *args: retried.append(args) or ("id", "queued"),
            railway_trigger=lambda *args: triggered.append(args),
            messenger=lambda *args: 77,
            feature_ack=lambda *args: acknowledgements.append(args),
            callback_answer=lambda *args: None,
        )
        result = service.handle_update({
            "update_id": 203,
            "callback_query": {"id": "cb", "data": "f04:t:equity:BBCA.JK",
                               "message": {"chat": {"id": 123}}},
        })
        self.assertEqual(result, "feature04_retry")
        self.assertEqual(len(retried), 1)
        self.assertEqual(triggered, [])
        self.assertEqual(acknowledgements, [("db", "id", 77)])

    def test_feature04_failed_ack_is_recorded_as_missing_message(self):
        acknowledgements = []
        service = TelegramTrigger(
            "db", "bot", "123", "railway", {},
            feature_retry=lambda *args: ("id", "queued"),
            messenger=lambda *args: (_ for _ in ()).throw(RuntimeError("down")),
            feature_ack=lambda *args: acknowledgements.append(args),
            callback_answer=lambda *args: None,
        )
        result = service.handle_update({
            "update_id": 204,
            "callback_query": {"id": "cb", "data": "f04:t:equity:BBCA.JK",
                               "message": {"chat": {"id": 123}}},
        })
        self.assertEqual(result, "feature04_retry")
        self.assertEqual(acknowledgements, [("db", "id", None)])

    def test_railway_request_uses_project_token_and_instance_id(self):
        captured = {}

        def opener(request, timeout):
            captured["header"] = request.get_header("Project-access-token")
            captured["user_agent"] = request.get_header("User-agent")
            captured["payload"] = json.loads(request.data)
            return FakeResponse({"data": {"deploymentInstanceExecutionCreate": True}})

        self.assertTrue(trigger_railway_run("project-token", "instance-1", opener=opener))
        self.assertEqual(captured["header"], "project-token")
        self.assertEqual(captured["user_agent"], "Saniti-Telegram-Trigger/1.0")
        self.assertEqual(
            captured["payload"]["query"].strip().splitlines()[0],
            "mutation RunCronNow($input: DeploymentInstanceExecutionCreateInput!) {",
        )
        self.assertEqual(
            captured["payload"]["variables"]["input"]["serviceInstanceId"], "instance-1"
        )

    def test_unauthorized_chat_does_not_claim_or_trigger(self):
        events = []
        service = TelegramTrigger(
            "db",
            "bot",
            "123",
            "railway",
            {"RUN_PRICE": CommandSpec("RUN_PRICE", "idx-price-cron", "instance", "IDX DAILY")},
            claim=lambda *args: events.append("claim"),
            railway_trigger=lambda *args: events.append("trigger"),
        )
        result = service.handle_update(
            {"update_id": 1, "message": {"chat": {"id": 999}, "text": "/run_price"}}
        )
        self.assertEqual(result, "unauthorized")
        self.assertEqual(events, [])

    def test_duplicate_update_does_not_trigger_railway(self):
        events = []
        service = TelegramTrigger(
            "db",
            "bot",
            "123",
            "railway",
            {"RUN_PRICE": CommandSpec("RUN_PRICE", "idx-price-cron", "instance", "IDX DAILY")},
            claim=lambda *args: ("duplicate", 1),
            railway_trigger=lambda *args: events.append("trigger"),
        )
        result = service.handle_update(
            {"update_id": 1, "message": {"chat": {"id": 123}, "text": "/run_price"}}
        )
        self.assertEqual(result, "duplicate")
        self.assertEqual(events, [])

    def test_valid_command_triggers_only_mapped_service(self):
        triggered = []
        messages = []
        finishes = []
        service = TelegramTrigger(
            "db",
            "bot",
            "123",
            "railway-token",
            {"RUN_PRICE": CommandSpec("RUN_PRICE", "idx-price-cron", "daily-instance", "IDX DAILY")},
            claim=lambda *args: ("claimed", 7),
            finish=lambda *args: finishes.append(args),
            railway_trigger=lambda token, instance: triggered.append((token, instance)) or True,
            messenger=lambda *args: messages.append(args) or 1,
        )
        result = service.handle_update(
            {"update_id": 3, "message": {"chat": {"id": 123}, "text": "/run_price"}}
        )
        self.assertEqual(result, "triggered")
        self.assertEqual(triggered, [("railway-token", "daily-instance")])
        self.assertEqual(finishes[0][2], "TRIGGERED")
        self.assertIn("Final result will follow", messages[0][2])

    def test_ack_failure_does_not_change_successful_trigger(self):
        finishes = []
        service = TelegramTrigger(
            "db",
            "bot",
            "123",
            "railway-token",
            {
                "RUN_PRICE": CommandSpec(
                    "RUN_PRICE", "idx-price-cron", "daily-instance", "IDX DAILY"
                )
            },
            claim=lambda *args: ("claimed", 9),
            finish=lambda *args: finishes.append(args),
            railway_trigger=lambda token, instance: True,
            messenger=lambda *args: (_ for _ in ()).throw(RuntimeError("Telegram down")),
        )
        result = service.handle_update(
            {"update_id": 9, "message": {"chat": {"id": 123}, "text": "/run_price"}}
        )
        self.assertEqual(result, "triggered")
        self.assertEqual(finishes, [("db", 9, "TRIGGERED", None)])


class PostgresRestartControlTests(unittest.TestCase):
    """EXEC-PG-RESTART-CRON (user go 2026-11-03): restart button, auto ON/OFF switch and status."""

    def service(self, events, commands=None):
        return TelegramTrigger(
            "db", "bot", "123", "railway-token",
            commands if commands is not None else {
                "RESTART_POSTGRES": CommandSpec("RESTART_POSTGRES", "postgres-memory-cron", "pg-instance",
                                                "Restart Postgres")},
            claim=lambda *args: ("claimed", 5),
            finish=lambda *args: events.append(("finish", args[2])),
            railway_trigger=lambda token, instance: events.append(("run", instance)) or True,
            messenger=lambda token, chat, text, markup=None: events.append(("msg", text)) or 1,
            callback_answer=lambda *args: None,
            pg_status=lambda db, cron: events.append(("status", cron)) or ("status text", {}),
            pg_switch=lambda db, update_id, chat, command: events.append(("switch", command)),
            pg_cron=lambda: "45 2,13 * * *",
        )

    def test_restart_button_runs_only_the_cron_service(self):
        events = []
        result = self.service(events).handle_update(
            {"update_id": 7, "callback_query": {"id": "cb", "data": "restart_postgres",
                                                "message": {"chat": {"id": 123}}}})
        self.assertEqual(result, "triggered")
        self.assertIn(("run", "pg-instance"), events)
        self.assertIn(("finish", "TRIGGERED"), events)

    def test_typed_restart_command_is_recognised(self):
        command = extract_incoming_command(
            {"update_id": 8, "message": {"chat": {"id": 123}, "text": "/restart_postgres"}})
        self.assertEqual(command.command, "RESTART_POSTGRES")

    def test_restart_without_the_cron_wired_is_not_configured(self):
        events = []
        result = self.service(events, commands={}).handle_update(
            {"update_id": 9, "message": {"chat": {"id": 123}, "text": "/restart_postgres"}})
        self.assertEqual(result, "not_configured")
        self.assertFalse([e for e in events if e[0] == "run"])

    def test_switch_records_the_command_and_replies_with_status(self):
        events = []
        result = self.service(events).handle_update(
            {"update_id": 10, "callback_query": {"id": "cb", "data": "pg:off", "message": {"chat": {"id": 123}}}})
        self.assertEqual(result, "pg_switch")
        self.assertEqual(events[0], ("switch", "PG_AUTO_OFF"))
        self.assertIn(("status", "45 2,13 * * *"), events)
        self.assertFalse([e for e in events if e[0] == "run"])     # a switch never restarts

    def test_status_and_typed_switches(self):
        self.assertEqual(extract_pg_action({"update_id": 1, "message": {"chat": {"id": 1}, "text": "/pg_auto_on"}})[2],
                         "pg:on")
        self.assertEqual(extract_pg_action(
            {"update_id": 1, "message": {"chat": {"id": 1}, "text": "/pg_restart_status"}})[2], "pg:status")
        self.assertIsNone(extract_pg_action({"update_id": 1, "callback_query": {"data": "pg:drop",
                                                                                  "message": {"chat": {"id": 1}}}}))
        events = []
        self.assertEqual(self.service(events).handle_update(
            {"update_id": 11, "message": {"chat": {"id": 123}, "text": "/pg_restart_status"}}), "pg_status")
        self.assertFalse([e for e in events if e[0] == "switch"])

    def test_other_chats_cannot_switch(self):
        events = []
        self.assertEqual(self.service(events).handle_update(
            {"update_id": 12, "message": {"chat": {"id": 999}, "text": "/pg_auto_off"}}), "unauthorized")
        self.assertEqual(events, [])

    def test_cron_reads_as_wib_times(self):
        self.assertEqual(wib_times("45 2,13 * * *"), "09:45 dan 20:45 WIB")
        self.assertEqual(wib_times(None), "tidak terbaca")


if __name__ == "__main__":
    unittest.main()
