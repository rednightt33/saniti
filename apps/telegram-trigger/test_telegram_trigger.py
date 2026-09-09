import io
import json
import unittest

from telegram_trigger import (
    CommandSpec,
    IncomingCommand,
    TelegramTrigger,
    extract_incoming_command,
    menu_markup,
    trigger_railway_run,
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
        self.assertEqual(callbacks, ["run_price", "run_recovery"])

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


if __name__ == "__main__":
    unittest.main()
