"""Offline tests: python3 -m unittest discover -s checks -p 'test_*.py'."""

from pathlib import Path
import tempfile
import unittest

from check_tool_names import catalog_names, find_unknown, load_allowlist, suggestion

CATALOG = {"tools": [
    {"name": "models_list", "inputSchema": {"properties": {"project_id": {"type": "string"}}}},
    {"name": "workflows_run", "inputSchema": {"properties": {
        "workflow_id": {"type": "string"},
        "parameters": {"type": "object", "properties": {"batch_size": {"type": "integer"}}},
    }}},
    {"name": "workflow_evals_cases_create", "inputSchema": {}},
]}


class CheckToolNamesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tools, self.params = catalog_names(CATALOG)

    def write(self, text, relative="skills/demo/SKILL.md"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def unknown(self, allow=frozenset()):
        return [name for _, _, name in find_unknown(self.root, self.tools, self.params, set(allow))]

    def test_known_tools_and_calls_pass(self):
        self.write("Call `models_list`, then `workflows_run(workflow_id=…)`.")
        self.assertEqual(self.unknown(), [])

    def test_missing_tool_with_known_prefix_is_reported(self):
        self.write("Use `models_infer` on one image.")
        self.assertEqual(self.unknown(), ["models_infer"])

    def test_missing_tool_with_new_prefix_and_verb_is_reported(self):
        self.write("Open it with `widgets_preview`.")
        self.assertEqual(self.unknown(), ["widgets_preview"])

    def test_shortened_tool_name_is_reported_with_suggestion(self):
        self.write("`cases_create` takes `ground_truth_state`.")
        self.assertEqual(self.unknown(), ["cases_create"])
        self.assertEqual(suggestion("cases_create", self.tools), "workflow_evals_cases_create")

    def test_parameters_nested_parameters_and_unrelated_names_pass(self):
        self.write("Pass `project_id`, `workflow_id` and `batch_size`; set `max_runtime_seconds`.")
        self.assertEqual(self.unknown(), [])

    def test_allowlist_and_chatgpt_overrides(self):
        self.write("Set `models_folder`.", "chatgpt/skills/demo/SKILL.md")
        self.assertEqual(self.unknown(), ["models_folder"])
        self.assertEqual(self.unknown({"models_folder"}), [])

    def test_allowlist_ignores_comments(self):
        path = self.root / "allow.txt"
        path.write_text("# header\napi_key  # SDK argument\n\n", encoding="utf-8")
        self.assertEqual(load_allowlist(path), {"api_key"})


if __name__ == "__main__":
    unittest.main()
