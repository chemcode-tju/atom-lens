"""Dependency-free MCP server for the native Codex file-editor entrypoint."""

# Configuration
plugin_version = "0.3.0"
resource_uri = "ui://structure-viewer/editor.html"

from pathlib import Path
from typing import Any
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trajectory import read_frames

plugin_root = Path(__file__).resolve().parent


def widget_html() -> str:
    """Inline all assets: no CDN, HTTP server or filesystem access in the UI."""
    html = (plugin_root / "web/index.html").read_text()
    for placeholder, filename in [
        ("/*__STYLE__*/", "style.css"),
        ("/*__3DMOL__*/", "vendor/3Dmol-min.js"),
        ("/*__PARSER__*/", "parser.js"),
        ("/*__APPEARANCE__*/", "appearance.js"),
        ("/*__VIEWPORT__*/", "viewport.js"),
        ("/*__APP__*/", "app.js"),
    ]:
        asset = (plugin_root / "web" / filename).read_text()
        html = html.replace(placeholder, asset.replace("</script", "<\\/script"))
    return html


def tool_descriptor() -> dict[str, Any]:
    return {
        "name": "open_structure", "title": "Structure Viewer",
        "description": "Native file viewer/editor for atomic structures and trajectories.",
        "inputSchema": {
            "type": "object", "properties": {"file": {
                "type": "object", "properties": {
                    "name": {"type": "string"}, "resourceUri": {"type": "string"}},
                "required": ["name", "resourceUri"]}}, "required": ["file"]},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "_meta": {
            "ui": {"resourceUri": resource_uri, "visibility": ["app"]},
            "openai/ui": {"entrypoints": [{"type": "file", "extensions": [
                ".extxyz", ".xyz", ".poscar", ".contcar", ".vasp", ".xdatcar"]}]},
        },
    }


def dispatch(method: str, params: dict[str, Any]) -> dict[str, Any]:
    """Serve the UI and bounded reads; writes still go through the native host."""
    if method == "initialize":
        return {"protocolVersion": params.get("protocolVersion", "2025-11-25"),
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": {"name": "structure-viewer", "version": plugin_version}}
    if method in {"ping", "resources/subscribe", "resources/unsubscribe"}:
        return {}
    if method == "tools/list":
        return {"tools": [tool_descriptor(), {
            "name": "read_trajectory_frames", "title": "Read trajectory frames",
            "description": "Read a bounded batch of complete XYZ frames from the host-selected file.",
            "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
                "offset": {"type": "integer", "minimum": 0},
                "frameLimit": {"type": "integer", "minimum": 1, "maximum": 32},
                "version": {"type": "string"}}},
            "annotations": {"readOnlyHint": True, "openWorldHint": False},
            "_meta": {"ui": {"visibility": ["app"]}},
        }]}
    if method == "resources/list":
        return {"resources": [{"uri": resource_uri, "name": "Atomic structure editor",
                               "mimeType": "text/html;profile=mcp-app"}]}
    if method == "resources/templates/list":
        return {"resourceTemplates": []}
    if method == "resources/read" and params.get("uri") == resource_uri:
        return {"contents": [{"uri": resource_uri, "mimeType": "text/html;profile=mcp-app",
                              "text": widget_html(), "_meta": {"ui": {
                                  "prefersBorder": False,
                                  "csp": {"connectDomains": [], "resourceDomains": []}}}}]}
    if method == "tools/call" and params.get("name") == "open_structure":
        file = params.get("arguments", {}).get("file", {})
        if not isinstance(file.get("name"), str) or not isinstance(file.get("resourceUri"), str):
            raise ValueError("A host-provided file name and resource URI are required.")
        return {"content": [{"type": "text", "text": f"Opening {file['name']}"}],
                "structuredContent": {"file": file}}
    if method == "tools/call" and params.get("name") == "read_trajectory_frames":
        batch = read_frames(params)
        return {"content": [{"type": "text", "text": f"Read {batch.get('frameCount', 0)} frames"}],
                "structuredContent": batch}
    raise ValueError(f"Unsupported method or resource: {method}")


def main() -> None:
    """MCP STDIO uses one UTF-8 JSON-RPC message per line; stdout is protocol only."""
    for line in sys.stdin:
        request: dict[str, Any] = {}
        try:
            request = json.loads(line)
            if "id" not in request:
                continue
            result = dispatch(request["method"], request.get("params", {}))
            response = {"jsonrpc": "2.0", "id": request["id"], "result": result}
        except Exception as error:
            response = {"jsonrpc": "2.0", "id": request.get("id"),
                        "error": {"code": -32602, "message": str(error)}}
        print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
