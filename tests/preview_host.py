"""Development-only MCP Apps host simulator; saves only to test-results/."""

# Configuration
fixture_file = "test-data/train.extxyz"
port = 8767
batch_delay_seconds = 0.2
host_color_scheme = "light"

from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import hashlib
import importlib.util
import json
import time

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("viewer_server", root / "plugin/server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

host_html = """<!doctype html><html><head><meta charset="utf-8"><title>Structure Viewer — protocol test host</title></head>
<body style="margin:0;overflow:hidden"><iframe title="Structure editor" src="/widget" style="display:block;border:0;width:100%;height:100vh"></iframe>
<script>
let currentText,etag;
async function fixture(){if(currentText===undefined){const r=await fetch('/fixture');currentText=await r.text();etag=r.headers.get('ETag');}return currentText;}
addEventListener('message',async event=>{
 const iframe=document.querySelector('iframe');if(event.source!==iframe.contentWindow)return;
 const m=event.data;if(m?.jsonrpc!=='2.0')return;
 const send=(method,params)=>iframe.contentWindow.postMessage({jsonrpc:'2.0',method,params},location.origin);
 if(m.method==='ui/notifications/initialized'){send('ui/notifications/tool-input',{arguments:{file:{name:'__NAME__',resourceUri:'codex-resource://test-fixture'}}});return;}
 if(m.id===undefined)return;
 let result={};try{
 if(m.method==='ui/initialize')result={protocolVersion:'2026-01-26',hostInfo:{name:'Protocol test host',version:'1'},hostCapabilities:{experimental:{'openai/resource':{}}},hostContext:{displayMode:'fullscreen'}};
 else if(m.method==='resources/read')result={contents:[{uri:'codex-resource://test-fixture',text:await fixture(),_meta:{'openai/resource':{etag,writable:true}}}]};
 else if(m.method==='tools/call'){
   const r=await fetch('/tools',{method:'POST',body:JSON.stringify(m.params)});
   if(!r.ok)throw Error(await r.text());result=await r.json();
 }
 else if(m.method==='openai/resources/write'){
   if(m.params.ifMatch!==etag)result={outcome:'conflict',etag};
   else {const r=await fetch('/save',{method:'POST',body:m.params.text});if(!r.ok)throw Error(await r.text());currentText=m.params.text;etag=r.headers.get('ETag');result={outcome:'saved',etag};}
 }
 iframe.contentWindow.postMessage({jsonrpc:'2.0',id:m.id,result},location.origin);
 }catch(e){iframe.contentWindow.postMessage({jsonrpc:'2.0',id:m.id,error:{code:-32000,message:e.message}},location.origin);}
});
</script></body></html>"""


class TestHost(BaseHTTPRequestHandler):
    def reply(self, body: bytes, mime: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", f"{mime}; charset=utf-8")
        self.send_header("ETag", hashlib.sha256(body).hexdigest())
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/":
            self.reply(host_html.replace("__NAME__", Path(fixture_file).name).encode(), "text/html")
        elif self.path == "/widget":
            html = server.widget_html().replace('<html lang="zh-CN">', f'<html lang="zh-CN" style="color-scheme:{host_color_scheme}">')
            self.reply(html.encode(), "text/html")
        elif self.path == "/fixture":
            self.reply((root / fixture_file).read_bytes(), "text/plain")
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        if self.path == "/tools":
            try:
                length = int(self.headers.get("Content-Length", 0))
                if length > 24 * 1048576:
                    raise ValueError("Request too large")
                params = json.loads(self.rfile.read(length))
                params["_meta"] = {"openai/resource": {"path": str(root / fixture_file)}}
                time.sleep(batch_delay_seconds)
                self.reply(json.dumps(server.dispatch("tools/call", params)).encode(), "application/json")
            except Exception as error:
                self.send_error(400, str(error))
            return
        if self.path != "/save":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        if length > 64 * 1048576:
            self.send_error(413)
            return
        content = self.rfile.read(length)
        output = root / "test-results/roundtrip.extxyz"
        output.parent.mkdir(exist_ok=True)
        output.write_bytes(content)
        self.reply(content, "text/plain")


def main() -> None:
    print(f"Development test host: http://127.0.0.1:{port}", flush=True)
    HTTPServer(("127.0.0.1", port), TestHost).serve_forever()


if __name__ == "__main__":
    main()
