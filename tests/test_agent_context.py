import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location(
    "agent_context", Path(__file__).parents[1] / "scripts/agent_context.py"
)
context = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(context)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.transcript = self.root / "history with spaces.jsonl"

    def write(self, *records):
        self.transcript.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    def test_provider_formats_tools_opt_in_and_output_bound(self):
        self.write(
            {"type": "user", "message": {"content": "original goal"}},
            {"type": "assistant", "message": {"content": [
                {"type": "thinking", "thinking": "PRIVATE_REASONING"},
                {"type": "tool_use", "name": "Bash", "input": {"command": "TOOL_ONLY"}},
            ]}},
            {"type": "response_item", "payload": {"type": "message", "role": "assistant",
                "content": [{"type": "output_text", "text": "done " + "x" * 100000}]}},
            {"type": "event_msg", "payload": {"type": "agent_message", "message": "DUPLICATE"}},
        )
        output = "\n".join(context.excerpts(self.transcript))
        self.assertIn("original goal", output)
        self.assertIn("done", output)
        self.assertLess(len(output), 1000)
        self.assertNotIn("TOOL_ONLY", output)
        self.assertNotIn("PRIVATE_REASONING", output)
        self.assertNotIn("DUPLICATE", output)
        self.assertIn("TOOL_ONLY", "\n".join(context.excerpts(self.transcript, tools=True)))

    def test_recovery_keeps_initial_goal_and_recent_work(self):
        self.write(*({"type": "user", "message": {"content": f"step {i}"}} for i in range(100)))
        rows = context.excerpts(self.transcript, limit=5)
        self.assertEqual(len(rows), 9)
        self.assertIn("step 0", rows[0])
        self.assertIn("step 99", rows[-1])

    def test_literal_search_and_pagination(self):
        self.write({"type": "user", "message": {"content": "a" * 500 + "NEEDLE" + "b" * 500}})
        self.assertIn("NEEDLE", context.excerpts(self.transcript, find="needle")[0])
        result = context.excerpts(self.transcript, line=1, offset=500, chars=6)
        self.assertTrue(result[0].endswith("NEEDLE"))

    def test_partial_unknown_and_missing_files(self):
        self.write({"type": "future_format", "secret": "DO_NOT_DUMP"})
        with self.transcript.open("a") as stream:
            stream.write('{"type":')
        output = "\n".join(context.excerpts(self.transcript))
        self.assertIn("No readable messages", output)
        self.assertNotIn("DO_NOT_DUMP", output)
        with self.assertRaises(FileNotFoundError):
            context.excerpts(self.root / "missing")

    def test_pointers_are_private_metadata_and_survive_null_compact_path(self):
        self.write({"type": "user", "message": {"content": "DO_NOT_COPY"}})
        event = {"session_id": "../../same-session", "hook_event_name": "PreCompact",
                 "transcript_path": str(self.transcript)}
        self.assertIsNone(context.hook(event, "codex", self.root))
        context.hook(event, "claude", self.root)
        pointers = list((self.root / ".agent-context/sessions").glob("*.json"))
        self.assertEqual(len(pointers), 2)
        for path in pointers:
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertNotIn("DO_NOT_COPY", path.read_text())
        output = context.hook({**event, "hook_event_name": "SessionStart",
                               "source": "compact", "transcript_path": None}, "codex", self.root)
        self.assertIn(str(self.transcript), output["hookSpecificOutput"]["additionalContext"])
        other = context.hook({**event, "session_id": "new-session", "transcript_path": None,
                              "hook_event_name": "SessionStart"}, "codex", self.root)
        self.assertNotIn(str(self.transcript), other["hookSpecificOutput"]["additionalContext"])

    def test_configured_commands_work_from_subdirectory_without_model_calls(self):
        source = Path(__file__).parents[1]
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "scripts").mkdir()
        (self.root / "api").mkdir()
        shutil.copy(source / "scripts/agent_context.py", self.root / "scripts/agent_context.py")
        self.write({"type": "user", "message": {"content": "goal"}})
        for file in (".claude/settings.json", ".codex/hooks.json"):
            config = json.loads((source / file).read_text())
            for event, groups in config["hooks"].items():
                command = groups[0]["hooks"][0]["command"]
                result = subprocess.run(command, shell=True, cwd=self.root / "api", text=True,
                    input=json.dumps({"session_id": "test", "transcript_path": str(self.transcript),
                                      "hook_event_name": event, "source": "compact"}),
                    capture_output=True, check=True)
                if event == "SessionStart":
                    self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["hookEventName"], event)
                else:
                    self.assertEqual(result.stdout, "")
        self.assertEqual(len(list((self.root / ".agent-context/sessions").glob("*.json"))), 2)


if __name__ == "__main__":
    unittest.main()
