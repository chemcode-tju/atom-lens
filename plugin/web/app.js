"use strict";
const $ = id => document.getElementById(id);
const pending = new Map();
let nextId = 1, hostName = "当前主机", fileRef, doc, frameIndex = 0, frameData, views;
let selection = [], timer = null, loading = false, readGeneration = 0;
let displayState = new StructureSelection.DisplayState();
let streamComplete = true, binaryTrajectory = false, pickedFile = false;
let anchor = null, paintTicket = 0, snapshotTicket = 0, snapshotData = null;
let snapshotHost = null;
let playback = {fps:60, speed:1, step:1, loop:true};
function afterPaint(callback) { requestAnimationFrame(() => setTimeout(callback, 0)); }
function scheduleRender(reset = false) { const ticket=++paintTicket; afterPaint(() => { if(ticket===paintTicket)render(reset); }); }
function clearFollow() { anchor=null; $("follow").checked=false; }
function setFollow(index) {
  if(!doc)return;
  const frame=doc.frame(frameIndex),atom=frame.atoms[index];
  if(!atom) { status("原子序号超出范围",true); return; }
  anchor={index,id:atom.id,element:atom.elem,signature:frame.atoms.map(a=>a.elem).join(',')};
  $("follow").checked=true;$("follow-number").value=index+1;render();
}
function send(method, params) { window.parent.postMessage({ jsonrpc: "2.0", method, params }, "*"); }
function request(method, params, timeoutMs = 60000) {
  const id = nextId++;
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => { pending.delete(id); reject(Error(`请求超时：${method}`)); }, timeoutMs);
    pending.set(id, { resolve, reject, timeout });
    window.parent.postMessage({ jsonrpc: "2.0", id, method, params }, "*");
  });
}
function status(text, error = false) { $("status").textContent = error ? text : ""; $("status").hidden = !error; }
function stop() { cancelAnimationFrame(timer); timer = null; $("play").textContent = "▶"; $("play").setAttribute("aria-label", "播放轨迹"); }
function updateTimeline() {
  if (!doc) return;
  $("timeline").max = doc.count - 1; $("timeline").value = frameIndex; $("timeline").disabled = doc.count < 2;
  $("frame-number").max = doc.count; $("frame-number").value = frameIndex + 1;
  $("frame-count").textContent = `/ ${doc.count}${streamComplete ? "" : "+"}`;
  const maxTicks = Math.max(2, Math.floor($("ticks").clientWidth / 45));
  const rough = Math.max(1, (doc.count - 1) / maxTicks);
  const base = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 5, 10].find(n => n * base >= rough) * base;
  const marks = [1];
  for (let n = step; n < doc.count - step * 0.45; n += step) if (n > 1) marks.push(n);
  if (doc.count > 1) marks.push(doc.count);
  $("ticks").replaceChildren(...marks.map(n => {
    const span = document.createElement("span"); span.textContent = n;
    span.style.left = `${(n - 1) / Math.max(1, doc.count - 1) * 100}%`;
    return span;
  }));
}
function render(reset = false) {
  if (!doc) return;
  try {
    frameData = doc.frame(frameIndex);
    if (!views) views = new StructureViews($("viewports"), chooseAtom, chooseBox);
    selection = selection.filter(i => i < frameData.atoms.length);
    const displayed = $("wrap").checked ? StructureGeometry.wrap(frameData) : frameData;
    const follow = $("follow").checked ? StructureGeometry.followAtom(displayed, anchor) : null;
    views.render(displayed, {style: $("style").value, palette: $("palette").value,
      scale: Number($("radius-scale").value), cell: $("cell").checked, labels: $("labels").checked, hbonds: $("hbonds").checked, lighting: true, follow, display: displayState}, selection, reset);
    updateTimeline();
    if (!$("source-panel").hidden) $("source").value = doc.frameText(frameIndex);
    $("source-title").textContent = doc.xyz ? `第 ${frameIndex + 1} 帧源码` : "VASP 文件源码";
    updateSelection();
  } catch (error) { stop(); status(error.message, true); }
}
function updateSelection() {
  $("atom-panel").hidden = selection.length === 0;
  $("atom-title").textContent = `已选 ${selection.length} 个原子`;
  if(!frameData)return;
  const displayed = $("wrap").checked ? StructureGeometry.wrap(frameData) : frameData;
  $("measurement").textContent = StructureSelection.measure(displayed.atoms, selection);
  $("atom-list").replaceChildren(...selection.map((index, order) => {
    const atom=displayed.atoms[index], row=document.createElement('div');
    row.textContent=`${order+1}. ${atom.elem} #${index+1}   (${atom.x.toFixed(4)}, ${atom.y.toFixed(4)}, ${atom.z.toFixed(4)}) Å`;
    return row;
  }));
  $("selection-count").textContent=`选中原子 · ${selection.length}`;
  $("apply-display").disabled=$("reset-selected-style").disabled=!selection.length;
}
function chooseAtom(index) {
  if(views?.mode!=="select")return;
  stop(); selection=selection.includes(index)?selection.filter(i=>i!==index):[...selection,index];render();
}
function chooseBox(indices, append) {
  stop();selection=append?[...new Set([...selection,...indices])]:indices;render();
}
function resetDisplayState() { displayState=new StructureSelection.DisplayState();selection=[]; }
function populateElements() {
  if(!frameData)return;
  $("element-list").replaceChildren(...[...new Set(frameData.atoms.map(a=>a.elem))].sort().map(elem=>{
    const label=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.checked=!displayState.hiddenElements.has(elem);
    input.onchange=()=>{if(input.checked)displayState.hiddenElements.delete(elem);else displayState.hiddenElements.add(elem);scheduleRender();};
    label.append(input,document.createTextNode(elem));return label;
  }));
  updateSelection();
}
$("clear-selection").onclick=()=>{selection=[];render();};
$("display-settings").onclick=()=>{stop();populateElements();$("display-dialog").showModal();};
$("display-close").onclick=()=>$("display-dialog").close();
$("show-elements").onclick=()=>{displayState.hiddenElements.clear();populateElements();scheduleRender();};
$("apply-display").onclick=()=>{
  const style=$("selection-style").value,palette=$("selection-palette").value,visible=$("selection-visible").value;
  displayState.apply(frameData,selection,{...(style?{style}:{}),...(palette?{palette,color:palette==='custom'?$("selection-color").value:null}:{}),...(visible?{visible:visible==='show'}:{})});scheduleRender();
};
$("reset-selected-style").onclick=()=>{displayState.reset(frameData,selection);scheduleRender();};
$("reset-display").onclick=()=>{resetDisplayState();populateElements();scheduleRender();};
function go(index) {
  if (!doc) return;
  const target = Math.max(0, Math.min(doc.count - 1, Number(index) || 0));
  try { if($("follow").checked)StructureGeometry.followAtom(doc.frame(target),anchor); }
  catch(error){stop();status(error.message,true);return;}
  const previousFrame=doc.frame(frameIndex),nextFrame=doc.frame(target);
  selection=StructureSelection.remap(previousFrame,nextFrame,selection);
  displayState.transition(previousFrame,nextFrame);
  frameIndex=target;status("");render();
}
async function loadFile(file, reload = false) {
  if (!file?.resourceUri || (!reload && fileRef?.resourceUri === file.resourceUri && (doc || loading))) return;
  pickedFile=false; binaryTrajectory=/\.traj$/i.test(file.name); clearFollow(); resetDisplayState();
  if (!/\.(extxyz|xyz|traj)$/i.test(file.name)) { frameIndex=0; return loadFullFile(file); }
  const generation = ++readGeneration;
  stop(); loading = true; streamComplete = false;
  fileRef = file; doc = null; frameIndex = 0; selection = [];
  $("source-toggle").hidden = binaryTrajectory; $("source-panel").hidden = true;
  $("filename").textContent = file.name; status("正在读取第一帧…");
  let offset = 0, version;
  try {
    while (generation === readGeneration) {
      const result = await request("tools/call", { name: "read_trajectory_frames", arguments: {
        ...(file.token ? {token:file.token} : {}), offset, frameLimit: offset === 0 ? 1 : 32, ...(version ? { version } : {})
      } });
      if (generation !== readGeneration) return;
      if (result.isError) throw Error(result.content?.find(c => c.text)?.text || "分段读取失败");
      const batch = result.structuredContent;
      if (batch?.supported === false && offset === 0) return loadFullFile(file);
      if (!batch || typeof batch.text !== "string" || !Number.isInteger(batch.nextOffset) || batch.nextOffset < offset || (!batch.eof && batch.nextOffset === offset)) throw Error("分段读取返回无效数据");
      const first = !doc;
      if (first) doc = new StructureParser.ProgressiveXYZDocument(binaryTrajectory ? "preview.extxyz" : file.name);
      doc.append(batch.text);
      if (first && !doc.count) throw Error("没有有效结构帧");
      streamComplete = batch.eof; offset = batch.nextOffset; version = batch.version;
      if (first) { doc.frame(0); render(true); if(!file.token)request("resources/subscribe", { uri: file.resourceUri }).catch(() => {}); }
      else updateTimeline();
      status("");
      if (streamComplete) break;
      // Yield to input and paint before requesting the next bounded batch.
      await new Promise(resolve => setTimeout(resolve, 40));
    }
  } catch (error) {
    if (generation === readGeneration) { stop(); status(`加载停止：${error.message}${doc?.count ? `（保留已加载的 ${doc.count} 帧）` : ""}`, true); }
  } finally { if (generation === readGeneration) loading = false; }
}
async function loadFullFile(file) {
  if (!file?.resourceUri) return;
  if (/\.traj$/i.test(file.name)) { status("当前宿主不支持轨迹分段读取，请使用“打开”选择本地 .traj 文件", true); return; }
  loading = true; const generation = ++readGeneration; stop();
  $("source-toggle").hidden=false;
  fileRef = file; $("filename").textContent = file.name; status("");
  try {
    const result = file.token ? await request('tools/call',{name:'read_structure_source',arguments:{token:file.token}}) : await request("resources/read", { uri: file.resourceUri, _meta: { "openai/resource": { representation: "text" } } });
    if(result.isError)throw Error(result.content?.find(c=>c.text)?.text||'结构读取失败');
    if (generation !== readGeneration) return;
    const content = file.token ? result.structuredContent : (result.contents?.find(c => c.uri === file.resourceUri) || result.contents?.[0]);
    if (!content) throw Error("Codex 未返回文件内容");
    let text = content.text;
    if (text === undefined && content.blob) text = new TextDecoder().decode(Uint8Array.from(atob(content.blob), c => c.charCodeAt(0)));
    if (typeof text !== "string") throw Error("文件超过宿主读取限制或不是文本文件");
    const parsed = new StructureParser.StructureDocument(file.name, text); parsed.frame(0);
    doc = parsed;
    streamComplete = true;
    frameIndex = Math.min(frameIndex, doc.count - 1); selection = []; render(true);
    if(!file.token)request("resources/subscribe", { uri: file.resourceUri }).catch(() => {});
  } catch (error) { if (generation === readGeneration) status(`完整读取失败：${error.message}`, true); }
  finally { if (generation === readGeneration) { loading = false; } }
}
window.addEventListener("message", event => {
  if (event.source !== window.parent || event.data?.jsonrpc !== "2.0") return;
  const message = event.data;
  if (pending.has(message.id)) {
    const p = pending.get(message.id); pending.delete(message.id); clearTimeout(p.timeout);
    message.error ? p.reject(Error(message.error.message || "宿主请求失败")) : p.resolve(message.result); return;
  }
  if (message.method === "ui/notifications/tool-input" && message.params?.arguments?.file) loadFile(message.params.arguments.file);
  if (message.method === "ui/notifications/tool-result") {
    const result=message.params?.structuredContent;
    if(result?.host){hostName=result.host;$("path-host").textContent=`${hostName} 上的完整路径`;}
    if(result?.file)loadFile(result.file);
    else if(result?.browser&&!doc)$("path-dialog").showModal();
  }
  if (message.method === "notifications/resources/updated" && message.params?.uri === fileRef?.resourceUri) {
    loadFile(fileRef, true);
  }
  if (message.method === "ui/resource-teardown" && message.id !== undefined) {
    stop(); window.parent.postMessage({ jsonrpc: "2.0", id: message.id, result: {} }, "*");
  }
});
$("timeline").addEventListener("input", e => { stop(); go(e.target.value); });
$("frame-number").addEventListener("change", e => { stop(); go(Number(e.target.value) - 1); });
$("previous").onclick = () => { stop(); go(frameIndex - 1); };
$("next").onclick = () => { stop(); go(frameIndex + 1); };
$("play").onclick = () => {
  if (timer) return stop();
  if (!doc || doc.count < 2) return;
  if(frameIndex===doc.count-1 && streamComplete)go(0);
  $("play").textContent = "Ⅱ"; $("play").setAttribute("aria-label", "暂停轨迹");
  let previous=performance.now(), accumulator=0;
  const tick=now=>{
    if(timer===null)return;
    accumulator+=Math.min(now-previous,250)*playback.fps*playback.speed/1000;previous=now;
    const steps=Math.floor(accumulator);
    if(steps>0){
      accumulator-=steps;
      let target=frameIndex+steps*playback.step;
      if(target>=doc.count){
        if(!streamComplete){target=doc.count-1;accumulator=0;}
        else if(playback.loop)target%=doc.count;
        else {go(doc.count-1);stop();return;}
      }
      if(target!==frameIndex)go(target);
    }
    if(timer!==null)timer=requestAnimationFrame(tick);
  };
  timer=requestAnimationFrame(tick);
};
$("playback-settings").onclick=()=>{
  stop();$("animation-fps").value=playback.fps;$("playback-speed").value=playback.speed;
  $("playback-step").value=playback.step;$("playback-loop").checked=playback.loop;$("playback-dialog").showModal();
};
$("playback-apply").onclick=event=>{
  if(!$("playback-dialog").querySelector('form').reportValidity()){event.preventDefault();return;}
  playback={fps:Number($("animation-fps").value),speed:Number($("playback-speed").value),step:Number($("playback-step").value),loop:$("playback-loop").checked};
};
$("reset").onclick = () => views?.fit();
document.querySelectorAll("[data-orientation]").forEach(button=>button.onclick=()=>{views?.setOrientation(button.dataset.orientation);$("orientation").open=false;});
$("layout").onchange = event => views?.setLayout(event.target.value);
$("expand").onclick = () => views?.toggleExpand();
for (const mode of ["rotate", "pan", "zoom", "select", "box"]) $(mode).onclick = () => views?.setMode(mode);
$("first").onclick = () => { stop(); go(0); };
$("last").onclick = () => { stop(); if (doc) go(doc.count - 1); };
for (const id of ["style", "palette", "radius-scale", "cell", "labels", "hbonds", "wrap"]) $(id).onchange = () => { stop(); status(""); scheduleRender(id==="wrap"); };
$("follow").onchange=()=>{stop();if($("follow").checked)setFollow(Number($("follow-number").value)-1);else {anchor=null;render();}};
$("follow-apply").onclick=()=>{stop();setFollow(Number($("follow-number").value)-1);};
$("follow-selected").onclick=()=>setFollow(selection[selection.length-1]);
$("source-toggle").onclick = () => { stop(); $("source-panel").hidden = !$("source-panel").hidden; if(doc)$("source").value=doc.frameText(frameIndex); };
request("ui/initialize", { protocolVersion: "2026-01-26", appInfo: { name: "Structure Viewer", version: "0.7.0" }, appCapabilities: {} })
  .then(() => { send("ui/notifications/initialized", {}); status("已连接，等待文件…"); })
  .catch(error => status(`连接失败：${error.message}`, true));

$("open-file").onclick=()=>$("file-picker").click();
$("file-picker").onchange=async()=>{
  const file=$("file-picker").files[0];if(!file)return;
  const generation=++readGeneration;stop();clearFollow();resetDisplayState();pickedFile=true;fileRef=null;frameIndex=0;selection=[];doc=null;
  binaryTrajectory=/\.traj$/i.test(file.name);$("source-toggle").hidden=binaryTrajectory;$("source-panel").hidden=true;status("");$("filename").textContent=file.name;
  try {
    if(binaryTrajectory){
      loading=true;streamComplete=false;const trajectory=await ASETrajectory.open(file);
      if(generation!==readGeneration)return;doc=new StructureParser.ProgressiveXYZDocument('preview.extxyz');
      for(let index=0;index<trajectory.count;index++){
        const block=await trajectory.frameText(index);if(generation!==readGeneration)return;doc.append(block);streamComplete=index===trajectory.count-1;
        if(index===0)render(true);else updateTimeline();
        if(index%16===0)await new Promise(resolve=>setTimeout(resolve,0));
      }
    } else {
      const text=await file.text();if(generation!==readGeneration)return;
      doc=new StructureParser.StructureDocument(file.name,text);streamComplete=true;render(true);
    }
  } catch(error){status(error.message,true);}finally{if(generation===readGeneration)loading=false;$("file-picker").value='';}
};
function snapshotOptions(){return {dpi:Number($("snapshot-dpi").value),format:$("snapshot-format").value,transparent:$("snapshot-transparent").checked,crop:$("snapshot-crop").checked};}
async function refreshSnapshot(){
  const ticket=++snapshotTicket;snapshotData=null;$("snapshot-save").disabled=true;$("snapshot-result").textContent='';
  try {
    const result=await StructureSnapshot.capture(views,snapshotOptions());
    if(ticket!==snapshotTicket)return;snapshotData=result;$("snapshot-preview").src=result.preview;$("snapshot-preview").hidden=false;$("snapshot-save").disabled=false;
  }catch(error){if(ticket===snapshotTicket)$("snapshot-result").textContent=error.message;}
}
$("snapshot").onclick=async()=>{
  if(!views||!doc)return;stop();$("snapshot-name").value=$("filename").textContent.replace(/\.[^.]+$/,'').replace(/[^\p{L}\p{N}_ .()\-]/gu,'_')+'-frame-'+(frameIndex+1);
  snapshotData=null;$("snapshot-save").disabled=true;$("snapshot-preview").hidden=true;
  $("snapshot-dialog").showModal();snapshotHost=null;
  $("snapshot-result").textContent='';
  try {
    const response=await request('tools/call',{name:'snapshot_context',arguments:fileRef?.token?{token:fileRef.token}:{}});
    if(response.isError||!response.structuredContent)throw Error('无法读取保存位置，请重新打开查看器');
    snapshotHost=response.structuredContent;
    const serverOption=$("snapshot-destination").querySelector('[value="server"]');
    serverOption.hidden=snapshotHost.nativePicker||pickedFile;
    serverOption.textContent='服务器 · '+snapshotHost.host;
    $("snapshot-destination").value=(!snapshotHost.nativePicker&&!pickedFile)?'server':'local';
    $("snapshot-directory").value=pickedFile?'':snapshotHost.directory;
    updateSnapshotDestination();afterPaint(refreshSnapshot);
  }catch(error){$("snapshot-result").textContent=error.message;}
};
for(const id of ["snapshot-format","snapshot-dpi","snapshot-transparent","snapshot-crop"])$(id).onchange=()=>{
  snapshotData=null;$("snapshot-save").disabled=true;
  $("snapshot-transparent").disabled=$("snapshot-format").value!=='png';afterPaint(refreshSnapshot);
};
$("snapshot-close").onclick=()=>{$("snapshot-dialog").close();++snapshotTicket;};
function updateSnapshotDestination(){
  const server=$("snapshot-destination").value==='server';
  $("snapshot-directory-row").hidden=!server;
  $("snapshot-save").textContent=server?'保存到服务器':'选择本地文件夹并保存…';
}
$("snapshot-destination").onchange=updateSnapshotDestination;
$("snapshot-save").onclick=async()=>{
  if(!snapshotData||!snapshotHost)return;
  const result=snapshotData,format=$("snapshot-format").value,name=$("snapshot-name").value+'.'+format;
  if(!/^[\p{L}\p{N}_ .()\-]{1,100}\.(png|jpeg|pdf)$/u.test(name)||name.startsWith('.')){$("snapshot-result").textContent='请使用字母、数字、中文、空格、下划线或短横线命名';return;}
  $("snapshot-save").disabled=true;$("snapshot-close").disabled=true;
  try {
    const local=$("snapshot-destination").value==='local';
    if(local&&!snapshotHost.nativePicker){
      // Ask the parent host to download. Direct iframe anchor downloads are
      // blocked by Codex's MCP sandbox. Blob is structured-cloned, not JSON.
      await request('ui/download-file',{blob:new Blob([result.bytes],{type:result.mime}),name});
      $("snapshot-result").textContent='已交给 Mac 保存窗口；请在窗口中选择位置并完成保存';
    }else{
      let binary='';for(let i=0;i<result.bytes.length;i+=32768)binary+=String.fromCharCode(...result.bytes.subarray(i,i+32768));
      const saved=await request('tools/call',{name:'save_structure_snapshot',arguments:{name,data:btoa(binary),destination:local?'native':'server',...(!local?{directory:$("snapshot-directory").value.trim()}:{}),...(fileRef?.token?{token:fileRef.token}:{})}},660000);
      if(saved.isError)throw Error(saved.content?.find(c=>c.text)?.text||'保存失败');
      if(saved.structuredContent?.cancelled){$("snapshot-result").textContent='已取消保存';return;}
      if(!saved.structuredContent?.path)throw Error('宿主未确认保存路径');$("snapshot-result").textContent='已保存：'+saved.structuredContent.path;
    }
  }catch(error){$("snapshot-result").textContent=error.message;}finally{$("snapshot-save").disabled=false;$("snapshot-close").disabled=false;}
};

$("open-path").onclick=async()=>{
  stop();$("structure-path").value=fileRef?.path||'';$("path-error").textContent='';$("path-dialog").showModal();
  try {const r=await request('tools/call',{name:'open_structure_path',arguments:{}});if(r.structuredContent?.host){hostName=r.structuredContent.host;$("path-host").textContent=`${hostName} 上的完整路径`;}}catch(e){$("path-error").textContent=e.message;}
};
$("path-close").onclick=()=>$("path-dialog").close();
$("path-load").onclick=async()=>{
  const path=$("structure-path").value.trim();if(!path)return;
  $("path-load").disabled=true;$("path-error").textContent='';
  try {
    const result=await request('tools/call',{name:'open_structure_path',arguments:{path}});
    if(result.isError)throw Error(result.content?.find(c=>c.text)?.text||'打开失败');
    if(!result.structuredContent?.file)throw Error('未返回结构文件');
    $("path-dialog").close();await loadFile(result.structuredContent.file);
  }catch(e){$("path-error").textContent=e.message;}finally{$("path-load").disabled=false;}
};
$("structure-path").onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();$("path-load").click();}};
