"""Dependency-free MCP server for the native Codex file-editor entrypoint."""

# Configuration
plugin_version = "0.9.3"
resource_uri = "ui://structure-viewer/editor.html"

from pathlib import Path
from typing import Any
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trajectory import read_frames
from snapshot import save_snapshot, snapshot_context
from local_export import prepare_local_snapshot, snapshot_save_status
from path_access import StructurePaths
from media_export import MediaExports

media_exports = MediaExports()

selected_paths = StructurePaths()

plugin_root = Path(__file__).resolve().parent


def widget_html() -> str:
    """Inline all assets: no CDN, HTTP server or filesystem access in the UI."""
    html = (plugin_root / "web/index.html").read_text()
    for placeholder, filename in [
        ("/*__STYLE__*/", "style.css"),
        ("/*__I18N__*/", "i18n.js"),
        ("/*__3DMOL__*/", "vendor/3Dmol-min.js"),
        ("/*__PARSER__*/", "parser.js"),
        ("/*__APPEARANCE__*/", "appearance.js"),
        ("/*__GEOMETRY__*/", "geometry.js"),
        ("/*__ASE_TRAJ__*/", "ase-traj.js"),
        ("/*__VASP_STREAM__*/", "vasp-stream.js"),
        ("/*__SNAPSHOT__*/", "snapshot.js"),
        ("/*__SELECTION__*/", "selection.js"),
        ("/*__VIEWPORT__*/", "viewport.js"),
        ("/*__CONTROLS__*/", "controls.js"),
        ("/*__APP__*/", "app.js"),
        ("/*__ANIMATION__*/", "animation.js"),
    ]:
        asset = (plugin_root / "web" / filename).read_text()
        if filename == "i18n.js":
            asset = asset.replace("/*__LOCALES__*/{}", (plugin_root / "web/locales.json").read_text())
        if filename == "vendor/3Dmol-min.js":
            from renderer_adapter import resize_safe_renderer
            asset = resize_safe_renderer(asset)
            # Pinned-renderer adapter: modest ambient fill and a broad highlight.
            # The upstream imposter materials expose no lighting controls.
            highlight = " + vec3(0.20 * pow(max(dot(norm, normalize(vLight + vec3(0.0,0.0,1.0))), 0.0), 24.0))"
            asset = asset.replace("vec3 color = vLight*vColor;", "vec3 color = (vec3(0.30) + 0.70*vLight)*vColor" + highlight + ";")
            asset = asset.replace("color *= light;", "color = color*(vec3(0.30) + 0.70*light)" + highlight + ";")
        html = html.replace(placeholder, asset.replace("</script", "<\\/script"))
    return html


def tool_descriptor() -> dict[str, Any]:
    return {
        "name": "open_structure", "title": "Structure Viewer",
        "description": "Native read-only file viewer for atomic structures and trajectories.",
        "inputSchema": {
            "type": "object", "properties": {"file": {
                "type": "object", "properties": {
                    "name": {"type": "string"}, "resourceUri": {"type": "string"}},
                "required": ["name", "resourceUri"]}}, "required": ["file"]},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "_meta": {
            "ui": {"resourceUri": resource_uri, "visibility": ["app"]},
            "openai/ui": {"entrypoints": [{"type": "file", "extensions": [
                ".extxyz", ".xyz", ".traj", ".vasp"]}]},
        },
    }


def dispatch(method: str, params: dict[str, Any]) -> dict[str, Any]:
    """Serve the UI, bounded structure reads, and explicit snapshot exports."""
    if method == "initialize":
        return {"protocolVersion": params.get("protocolVersion", "2025-11-25"),
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": {"name": "structure-viewer", "version": plugin_version}}
    if method in {"ping", "resources/subscribe", "resources/unsubscribe"}:
        return {}
    if method == "tools/list":
        return {"tools": [tool_descriptor(), {
            "name": "structure_media_export", "title": "Export structure images and animations",
            "description": "User-requested chunked PNG/JPEG/PDF and GIF/MOV/MP4 export, with native Mac or server saving.",
            "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
                "language": {"type": "string", "enum": ["zh-CN", "en"]},
                "action": {"type": "string", "enum": ["begin", "append", "finish", "status", "save", "cancel"]},
                "id": {"type": "string"}, "kind": {"type": "string", "enum": ["image", "animation"]},
                "name": {"type": "string"}, "fps": {"type": "number", "exclusiveMinimum": 0},
                "chunk": {"type": "integer", "minimum": 0}, "data": {"type": "string"}, "last": {"type": "boolean"},
                "destination": {"type": "string", "enum": ["native", "server", "helper"]},
                "directory": {"type": "string"}, "token": {"type": "string"}}, "required": ["action"]},
            "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
            "_meta": {"ui": {"visibility": ["app"]}},
        }, {
            "name": "open_structure_path", "title": "Structure Viewer",
            "description": "Open an atomic structure in the viewer using its unchanged absolute path on this host, including bare POSCAR, CONTCAR and XDATCAR. Omit path to open the structure browser. Use this for user-requested VASP viewing instead of renaming or copying files.",
            "inputSchema": {"type": "object", "additionalProperties": False,
                            "properties": {"path": {"type": "string"}}},
            "annotations": {"readOnlyHint": True, "openWorldHint": False},
            "_meta": {"ui": {"resourceUri": resource_uri, "visibility": ["app", "model"]},
                      "openai/ui": {"entrypoints": [{"type": "thread"}]}},
        }, {
            "name": "read_structure_source", "title": "Read selected VASP structure",
            "description": "Read the structure already selected through the path browser.",
            "inputSchema": {"type": "object", "additionalProperties": False,
                            "properties": {"token": {"type": "string"}}, "required": ["token"]},
            "annotations": {"readOnlyHint": True, "openWorldHint": False},
            "_meta": {"ui": {"visibility": ["app"]}},
        }, {
            "name": "read_trajectory_frames", "title": "Read trajectory frames",
            "description": "Read a bounded batch of complete XYZ, ASE or VASP trajectory frames from the host-selected file.",
            "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
                "token": {"type": "string"},
                "offset": {"type": "integer", "minimum": 0},
                "frameLimit": {"type": "integer", "minimum": 1, "maximum": 32},
                "version": {"type": "string"}}},
            "annotations": {"readOnlyHint": True, "openWorldHint": False},
            "_meta": {"ui": {"visibility": ["app"]}},
        }, {
            "name": "snapshot_save_status", "title": "Mac snapshot save status",
            "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
            "annotations": {"readOnlyHint": True, "openWorldHint": False},
            "_meta": {"ui": {"visibility": ["app"]}},
        }, {
            "name": "prepare_local_snapshot", "title": "Prepare Mac snapshot save",
            "description": "Stage a user-requested image for the installed Mac snapshot saver to retrieve over SSH.",
            "inputSchema": {"type": "object", "additionalProperties": False, "properties": {"language": {"type": "string", "enum": ["zh-CN", "en"]}, "name": {"type": "string"}, "data": {"type": "string"}}, "required": ["name", "data"]},
            "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
            "_meta": {"ui": {"visibility": ["app"]}},
        }, {
            "name": "snapshot_context", "title": "Snapshot destinations",
            "description": "Identify the plugin host and the opened structure directory for snapshot saving.",
            "inputSchema": {"type": "object", "additionalProperties": False, "properties": {"token": {"type": "string"}}},
            "annotations": {"readOnlyHint": True, "openWorldHint": False},
            "_meta": {"ui": {"visibility": ["app"]}},
        }, {
            "name": "save_structure_snapshot", "title": "Save structure snapshot",
            "description": "Save a user-requested PNG/JPEG/PDF in a chosen directory; use the native macOS folder chooser locally. Never overwrite existing files.",
            "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
                "token": {"type": "string"}, "destination": {"type": "string", "enum": ["native", "server"]}, "directory": {"type": "string"}, "name": {"type": "string"}, "data": {"type": "string"}}, "required": ["name", "data"]},
            "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
            "_meta": {"ui": {"visibility": ["app"]}},
        }]}
    if method == "resources/list":
        return {"resources": [{"uri": resource_uri, "name": "Atomic structure viewer",
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
    if method == "tools/call" and params.get("name") == "open_structure_path":
        result = selected_paths.open(params.get("arguments", {}).get("path"))
        return {"content": [{"type": "text", "text": f"Structure Viewer on {result['host']}"}],
                "structuredContent": result}
    if method == "tools/call" and params.get("name") == "read_structure_source":
        result = selected_paths.read_source(params)
        return {"content": [{"type": "text", "text": "Read selected structure"}], "structuredContent": result}
    if method == "tools/call" and params.get("name") == "read_trajectory_frames":
        batch = read_frames(selected_paths.bind(params))
        return {"content": [{"type": "text", "text": f"Read {batch.get('frameCount', 0)} frames"}],
                "structuredContent": batch}
    if method == "tools/call" and params.get("name") == "structure_media_export":
        arguments = params.get("arguments", {})
        action = arguments.get("action")
        if action not in {"begin", "append", "finish", "status", "save", "cancel"}:
            raise ValueError("未知导出操作")
        result = media_exports.save(selected_paths.bind(params)) if action == "save" else getattr(media_exports, action)(arguments)
        return {"content": [], "structuredContent": result}
    if method == "tools/call" and params.get("name") == "snapshot_save_status":
        result = snapshot_save_status(params.get("arguments", {}))
        return {"content": [{"type": "text", "text": json.dumps(result)}], "structuredContent": result}
    if method == "tools/call" and params.get("name") == "prepare_local_snapshot":
        result = prepare_local_snapshot(params.get("arguments", {}))
        return {"content": [], "structuredContent": result}
    if method == "tools/call" and params.get("name") == "snapshot_context":
        result = snapshot_context(selected_paths.bind(params))
        return {"content": [], "structuredContent": result}
    if method == "tools/call" and params.get("name") == "save_structure_snapshot":
        result = save_snapshot(selected_paths.bind(params))
        return {"content": [{"type": "text", "text": "Cancelled" if result.get("cancelled") else f"Saved {result['path']}"}], "structuredContent": result}
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
