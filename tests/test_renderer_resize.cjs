// Execute the actual patched, pinned renderer methods against a counting GPU.
const assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const source=execFileSync('python3',['-B','-c',`from pathlib import Path
import sys
sys.path.insert(0,'plugin')
from renderer_adapter import resize_safe_renderer
print(resize_safe_renderer(Path('plugin/web/vendor/3Dmol-min.js').read_text()))`],{encoding:'utf8',maxBuffer:4*1024*1024});
function method(signature,next){const start=source.indexOf(signature),end=source.indexOf(next,start);assert.ok(start>=0&&end>start);return new Function('return function '+source.slice(start,end))();}
const allocations={texture:0,framebuffer:0,buffer:0,program:0};
const gl=new Proxy({}, {get:(_,key)=>{
 const kind={createTexture:'texture',createFramebuffer:'framebuffer',createBuffer:'buffer'}[key];
 if(kind)return ()=>({id:++allocations[kind]});
 if(key==='getAttribLocation')return ()=>0;
 return ()=>{};
}});
global.ue={screen:{},screenaa:{},ssao:{},blur:{}};
global.window={devicePixelRatio:2};
let width=0,height=0,clears=0;
const canvas={style:{},get width(){return width;},set width(n){width=n;clears++;},get height(){return height;},set height(n){height=n;clears++;}};
const renderer={_canvas:canvas,_gl:gl,_viewportWidth:0,_viewportHeight:0,_fb:null,isWebGL1:()=>false,isLost:()=>false,
 buildProgram:()=>({id:++allocations.program})};
renderer.initFrameBuffer=method('initFrameBuffer(){','renderFrameBuffertoScreen(){');
renderer.setSize=method('setSize(e,t){','clear(e,t,i){');
renderer.setSize(400,600);
assert.deepEqual(allocations,{texture:4,framebuffer:1,buffer:1,program:3});
assert.equal(clears,2);
for(let i=0;i<100;i++)renderer.setSize(400,600);
assert.equal(clears,2,'unchanged size must not clear the drawing buffer');
for(let i=0;i<100;i++)renderer.setSize(400+i,600);
assert.equal(clears,101,'only the changed width is assigned');
assert.deepEqual(allocations,{texture:4,framebuffer:1,buffer:1,program:3},'resize must not leak GPU objects');
assert.equal(width,998);assert.equal(height,1200);
console.log('Pinned renderer: 200 resize calls reuse GPU objects; unchanged canvas sizes never clear the buffer.');
