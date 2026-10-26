"""Check MCP discovery, file-entrypoint declarations and self-contained UI."""
from pathlib import Path
import importlib.util
import json
import subprocess
import sys
import unittest

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("viewer_server", root / "plugin/server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class ServerTests(unittest.TestCase):
    def test_entrypoint(self) -> None:
        tool = server.dispatch("tools/list", {})["tools"][0]
        self.assertIn(".extxyz", tool["_meta"]["openai/ui"]["entrypoints"][0]["extensions"])
        self.assertEqual(tool["_meta"]["ui"]["visibility"], ["app"])

    def test_resource(self) -> None:
        resource = server.dispatch("resources/read", {"uri": server.resource_uri})["contents"][0]
        self.assertNotIn("/*__", resource["text"])
        self.assertIn('id="timeline"', resource["text"])
        self.assertEqual(resource["mimeType"], "text/html;profile=mcp-app")

    def test_stdio(self) -> None:
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ]
        config = json.loads((root / "plugin/.mcp.json").read_text())["mcpServers"]["structure-viewer"]
        result = subprocess.run([config["command"], *config["args"]],
                                cwd=root / "plugin" / config["cwd"],
                                input="\n".join(json.dumps(r) for r in requests) + "\n",
                                text=True, capture_output=True, check=True)
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([reply["id"] for reply in replies], [1, 2])
        self.assertIn("tools", replies[1]["result"])


if __name__ == "__main__":
    unittest.main()
