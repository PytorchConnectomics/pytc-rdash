import unittest

from dashboard.app import tracks


def spec(body):
    return "# x\n\n## TRACKS\n\n```rdash-tracks\n" + body + "\n```\n"


GOOD = spec('''{"tracks": {
  "data": {"clahe": {"status": "active"}, "u8": {}},
  "model": {"hf18": {"needs": ["clahe", "u8"]}, "ft": {"needs": ["u8"], "cube": "S1"}}},
 "runs": [{"cube": "S1", "path": ["clahe", "hf18"]}, {"cube": "S1", "path": ["u8", "ft"], "name": "finetune"}]}''')


class TrackTests(unittest.TestCase):
    def test_no_block_is_undeclared(self):
        self.assertEqual(tracks.parse("# spec\n")["declared"], False)

    def test_good_block(self):
        result = tracks.parse(GOOD)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["tasks"], ["data", "model"])
        self.assertEqual([(t["name"], t["task"], t["status"]) for t in result["tracks"]],
                         [("clahe", "data", "active"), ("u8", "data", "planned"),
                          ("hf18", "model", "planned"), ("ft", "model", "planned")])
        self.assertEqual(result["tracks"][3]["cube"], ["S1"])
        self.assertEqual([(r["name"], r["path"]) for r in result["runs"]],
                         [("clahe → hf18", {"data": "clahe", "model": "hf18"}),
                          ("finetune", {"data": "u8", "model": "ft"})])

    def test_task_columns(self):
        result = tracks.parse(spec('{"tasks": ["data", "error-correction", "data"], "tracks": {}}'))
        self.assertEqual((result["errors"], result["columns"]), ([], ["data", "error-correction"]))
        self.assertIn("tasks must be", tracks.parse(spec('{"tasks": ["Bad Name"], "tracks": {}}'))["errors"][0])

    def test_errors_are_reported_not_raised(self):
        cases = {
            spec("not json"): "not valid JSON",
            spec('{"tracks": {"data": {"a": {}}, "model": {"a": {}}}}'): "declared in both",
            spec('{"tracks": {"data": {"shared": {}}}}'): "other than shared",
            spec('{"tracks": {"data": {"a": {"status": "maybe"}}}}'): "unknown status",
            spec('{"tracks": {"data": {"a": {"needs": ["b"]}}}}'): "needs unknown track b",
            spec('{"tracks": {"data": {"a": {}}}, "runs": [{"path": ["z"]}]}'): "unknown track 'z'",
            spec('{"tracks": {"data": {"a": {}, "b": {}}}, "runs": [{"path": ["a", "b"]}]}'): "two data tracks",
            spec('{"tracks": {"data": {"a": {}, "b": {}}, "model": {"m": {"needs": ["a"]}}}, '
                 '"runs": [{"path": ["b", "m"]}]}'): "m does not take b",
            spec('{"tracks": {"data": {"a": {}}}, "runs": [{"path": ["a"]}, {"path": ["a"]}]}'): "listed twice",
        }
        for text, message in cases.items():
            with self.subTest(message=message):
                errors = tracks.parse(text)["errors"]
                self.assertTrue(any(message in e for e in errors), errors)

    def test_milestones(self):
        text = spec('''{"tracks": {
  "data": {"clahe": {}, "u8": {}}, "model": {"hf18": {"needs": ["clahe", "u8"]}}},
 "runs": [{"name": "a", "path": ["clahe", "hf18"]}, {"name": "b", "path": ["u8", "hf18"]}],
 "milestones": [{"id": "M1", "name": "pretrained", "runs": ["a", "b"], "status": "current"},
                {"id": "M2", "runs": ["b"], "tasks": ["model"]}]}''')
        result = tracks.parse(text)
        self.assertEqual(result["errors"], [])
        self.assertEqual([(m["id"], m["name"], m["runs"], m["tasks"], m["status"]) for m in result["milestones"]],
                         [("M1", "pretrained", ["a", "b"], [], "current"), ("M2", "", ["b"], ["model"], "planned")])

    def test_milestone_errors(self):
        base = '{"tracks": {"data": {"a": {}}}, "runs": [{"name": "r", "path": ["a"]}], "milestones": %s}'
        cases = {
            '[{"runs": ["r"]}]': "needs an id",
            '[{"id": "M1", "runs": ["zz"]}]': "unknown run 'zz'",
            '[{"id": "M1", "status": "soon"}]': "unknown status",
            '[{"id": "M1", "tasks": ["model"]}]': "declared task names",
            '[{"id": "M1"}, {"id": "M1"}]': "listed twice",
        }
        errors = tracks.parse(spec('{"tracks": {"data": {"a": {"milestone": "M9"}}}, "milestones": [{"id": "M1"}]}'))["errors"]
        self.assertTrue(any("unknown milestone M9" in e for e in errors), errors)
        for body, message in cases.items():
            with self.subTest(message=message):
                errors = tracks.parse(spec(base % body))["errors"]
                self.assertTrue(any(message in e for e in errors), errors)

    def test_split(self):
        self.assertEqual(tracks.split(" a, b ,,c "), ["a", "b", "c"])
        self.assertEqual(tracks.split(""), [])


if __name__ == "__main__":
    unittest.main()
