"""Client for a stdio tool server (spawns the process) or any object with .handle()."""
from __future__ import annotations

import json
import subprocess
import sys
from itertools import count


class RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code


class Client:
    def __init__(self, transport):
        self._send, self._ids = transport, count(1)
        self.request("initialize")

    @classmethod
    def spawn(cls, module: str = "toolbelt.examples") -> "Client":
        proc = subprocess.Popen([sys.executable, "-m", module], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)

        def send(msg: dict) -> dict:
            proc.stdin.write(json.dumps(msg) + "\n")
            proc.stdin.flush()
            return json.loads(proc.stdout.readline())

        c = cls(send)
        c._proc = proc
        return c

    @classmethod
    def in_process(cls, server) -> "Client":
        return cls(lambda msg: server.handle(msg))

    def request(self, method: str, params: dict | None = None):
        resp = self._send({"jsonrpc": "2.0", "id": next(self._ids), "method": method, "params": params or {}})
        if "error" in resp:
            raise RpcError(resp["error"]["code"], resp["error"]["message"])
        return resp["result"]

    def list_tools(self) -> list[dict]:
        return self.request("tools/list")["tools"]

    def call(self, name: str, **arguments) -> str:
        return self.request("tools/call", {"name": name, "arguments": arguments})["content"][0]["text"]

    def close(self) -> None:
        if getattr(self, "_proc", None):
            self._proc.stdin.close()
            self._proc.wait(timeout=5)
            self._proc.stdout.close()
