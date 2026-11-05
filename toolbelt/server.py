"""JSON-RPC 2.0 tool server (initialize, tools/list, tools/call) with schema generation from type hints."""
from __future__ import annotations

import inspect
import json
import sys
import typing
from dataclasses import dataclass
from typing import Any, Callable, Literal

from .validation import validate

PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, TOOL_ERROR = -32700, -32600, -32601, -32602, -32000
PY2JSON = {str: "string", int: "integer", float: "number", bool: "boolean", list: "array", dict: "object"}


def _schema_for(tp) -> dict:
    origin = typing.get_origin(tp)
    if origin is Literal:
        return {"type": "string", "enum": list(typing.get_args(tp))}
    if origin in (list, typing.List):
        args = typing.get_args(tp)
        return {"type": "array", "items": _schema_for(args[0]) if args else {}}
    return {"type": PY2JSON.get(tp, "string")}


@dataclass
class ToolDef:
    name: str
    description: str
    fn: Callable
    input_schema: dict

    def public(self) -> dict:
        return {"name": self.name, "description": self.description, "inputSchema": self.input_schema}


class ToolError(Exception):
    pass


class ToolServer:
    def __init__(self, name: str = "toolbelt", version: str = "1.0.0"):
        self.info = {"name": name, "version": version}
        self.tools: dict[str, ToolDef] = {}

    def tool(self, fn: Callable | None = None, *, name: str | None = None):
        def reg(f: Callable) -> Callable:
            hints = typing.get_type_hints(f)
            props, required = {}, []
            for pname, p in inspect.signature(f).parameters.items():
                props[pname] = _schema_for(hints.get(pname, str))
                if p.default is inspect.Parameter.empty:
                    required.append(pname)
            schema = {"type": "object", "properties": props, "required": required, "additionalProperties": False}
            doc = (inspect.getdoc(f) or f.__name__).strip().splitlines()[0]
            self.tools[name or f.__name__] = ToolDef(name or f.__name__, doc, f, schema)
            return f
        return reg(fn) if fn else reg

    # ---- protocol
    def handle(self, req: Any) -> dict | None:
        if not isinstance(req, dict) or req.get("jsonrpc") != "2.0" or not isinstance(req.get("method"), str):
            return self._err(req.get("id") if isinstance(req, dict) else None, INVALID_REQUEST, "invalid request")
        rid, method, params = req.get("id"), req["method"], req.get("params") or {}
        if "id" not in req:  # notification: never answered
            return None
        if method == "initialize":
            return self._ok(rid, {"protocolVersion": "toolbelt-1", "serverInfo": self.info, "capabilities": {"tools": {}}})
        if method == "tools/list":
            return self._ok(rid, {"tools": [t.public() for t in self.tools.values()]})
        if method == "tools/call":
            return self._call(rid, params)
        return self._err(rid, METHOD_NOT_FOUND, f"method not found: {method}")

    def _call(self, rid, params: dict) -> dict:
        name, args = params.get("name"), params.get("arguments") or {}
        tool = self.tools.get(name)
        if not tool:
            return self._err(rid, INVALID_PARAMS, f"unknown tool: {name}")
        problems = validate(args, tool.input_schema, "arguments")
        if problems:
            return self._err(rid, INVALID_PARAMS, "; ".join(problems))
        try:
            result = tool.fn(**args)
        except ToolError as exc:
            return self._err(rid, TOOL_ERROR, str(exc))
        except Exception as exc:  # a buggy tool must not take the server down
            return self._err(rid, TOOL_ERROR, f"{type(exc).__name__}: {exc}")
        return self._ok(rid, {"content": [{"type": "text", "text": json.dumps(result) if not isinstance(result, str) else result}], "isError": False})

    @staticmethod
    def _ok(rid, result) -> dict:
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    @staticmethod
    def _err(rid, code: int, msg: str) -> dict:
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": msg}}

    def serve_stdio(self, inp=sys.stdin, out=sys.stdout) -> None:
        for line in inp:
            if not line.strip():
                continue
            try:
                resp = self.handle(json.loads(line))
            except json.JSONDecodeError:
                resp = self._err(None, PARSE_ERROR, "parse error")
            if resp is not None:
                out.write(json.dumps(resp) + "\n")
                out.flush()
