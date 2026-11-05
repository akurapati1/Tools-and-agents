import io
import json
import unittest

from toolbelt.client import Client, RpcError
from toolbelt.examples import server
from toolbelt.router import ToolRouter
from toolbelt.server import INVALID_PARAMS, INVALID_REQUEST, METHOD_NOT_FOUND, PARSE_ERROR, TOOL_ERROR, ToolServer
from toolbelt.validation import validate


class Validation(unittest.TestCase):
    def test_schema_subset(self):
        s = {"type": "object", "required": ["n"], "additionalProperties": False,
             "properties": {"n": {"type": "integer", "minimum": 1, "maximum": 5}, "mode": {"type": "string", "enum": ["a", "b"]}, "xs": {"type": "array", "items": {"type": "number"}}}}
        self.assertEqual(validate({"n": 3, "mode": "a", "xs": [1, 2.5]}, s), [])
        errs = " | ".join(validate({"n": 9, "mode": "z", "xs": [1, "x"], "extra": 1}, s))
        for frag in ("maximum", "not one of", "xs[1]", "unexpected property"):
            self.assertIn(frag, errs)
        self.assertIn("missing required", validate({}, s)[0])
        self.assertIn("expected integer", validate({"n": True}, s)[0])   # bool is not an integer


class Protocol(unittest.TestCase):
    def rpc(self, **kw):
        return server.handle({"jsonrpc": "2.0", "id": 1, **kw})

    def test_list_and_schema_generation(self):
        tools = {t["name"]: t for t in self.rpc(method="tools/list")["result"]["tools"]}
        self.assertEqual(len(tools), 7)
        conv = tools["convert_units"]["inputSchema"]
        self.assertEqual(conv["properties"]["frm"]["enum"], ["km", "mi", "kg", "lb", "c", "f"])
        self.assertEqual(sorted(conv["required"]), ["frm", "to", "value"])
        self.assertEqual(tools["extract_emails"]["inputSchema"]["properties"]["text"], {"type": "string"})
        self.assertEqual(tools["add"]["description"], "Add two numbers.")

    def test_calls_and_errors(self):
        call = lambda name, **a: self.rpc(method="tools/call", params={"name": name, "arguments": a})
        self.assertEqual(call("add", a=2, b=3)["result"]["content"][0]["text"], "5")
        self.assertEqual(call("convert_units", value=100, frm="c", to="f")["result"]["content"][0]["text"], "212.0")
        self.assertEqual(call("slugify", text="Hello, World! 2026")["result"]["content"][0]["text"], "hello-world-2026")
        self.assertEqual(call("days_between", start="2026-01-01", end="2026-03-01")["result"]["content"][0]["text"], "59")
        self.assertEqual(call("add", a="x", b=1)["error"]["code"], INVALID_PARAMS)
        self.assertEqual(call("add", a=1)["error"]["code"], INVALID_PARAMS)
        self.assertEqual(call("nope")["error"]["code"], INVALID_PARAMS)
        self.assertEqual(call("days_between", start="bad", end="2026-01-01")["error"]["code"], TOOL_ERROR)
        self.assertEqual(call("convert_units", value=1, frm="km", to="kg")["error"]["code"], TOOL_ERROR)
        self.assertEqual(self.rpc(method="bogus")["error"]["code"], METHOD_NOT_FOUND)
        self.assertEqual(server.handle({"id": 1})["error"]["code"], INVALID_REQUEST)
        self.assertIsNone(server.handle({"jsonrpc": "2.0", "method": "tools/list"}))   # notification: no reply

    def test_buggy_tool_does_not_crash_server(self):
        s = ToolServer()

        @s.tool
        def boom(x: int) -> int:
            """Always fails."""
            return 1 // 0

        r = s.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "boom", "arguments": {"x": 1}}})
        self.assertIn("ZeroDivisionError", r["error"]["message"])

    def test_stdio_loop_handles_garbage(self):
        out = io.StringIO()
        inp = io.StringIO('{bad json\n\n' + json.dumps({"jsonrpc": "2.0", "id": 7, "method": "tools/list"}) + "\n")
        server.serve_stdio(inp, out)
        lines = [json.loads(l) for l in out.getvalue().splitlines()]
        self.assertEqual(lines[0]["error"]["code"], PARSE_ERROR)
        self.assertEqual(lines[1]["id"], 7)


class ClientTests(unittest.TestCase):
    def test_in_process(self):
        c = Client.in_process(server)
        self.assertEqual(json.loads(c.call("word_count", text="a b c\nd"))["words"], 4)
        with self.assertRaises(RpcError) as cm:
            c.call("add", a=1)
        self.assertEqual(cm.exception.code, INVALID_PARAMS)

    def test_real_subprocess_over_stdio(self):
        c = Client.spawn()
        try:
            self.assertEqual(len(c.list_tools()), 7)
            self.assertEqual(c.call("sha256", text="abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
            self.assertEqual(json.loads(c.call("extract_emails", text="mail a@x.io or b.c@y.org")), ["a@x.io", "b.c@y.org"])
        finally:
            c.close()


class Routing(unittest.TestCase):
    tools = Client.in_process(server).list_tools()
    router = ToolRouter(tools)

    def test_selects_relevant_tool_first(self):
        cases = {"what is the sha256 hash of this password": "sha256", "how many days between 2026-01-01 and 2026-02-01": "days_between",
                 "convert 5 miles to kilometers": "convert_units", "make a url slug from my blog title": "slugify",
                 "pull the email addresses out of this text": "extract_emails", "count the words in this paragraph": "word_count",
                 "what is 17 plus 25": "add"}
        for q, want in cases.items():
            self.assertEqual(self.router.select(q, 1)[0]["name"], want, q)

    def test_no_match_and_savings(self):
        self.assertEqual(self.router.select("zzzz qqqq", 3), [])
        self.assertGreater(self.router.savings("hash this text", 2), 0.5)


if __name__ == "__main__":
    unittest.main()
