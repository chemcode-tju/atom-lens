"use strict";
const $ = id => document.getElementById(id);
const pending = new Map();
let nextId = 1, hostName = "当前主机", fileRef, doc, frameIndex = 0, frameData, views;
let selection = [], timer = null, loading = false, readGeneration = 0;
let displayState = new StructureSelection.DisplayState();
let streamComplete = true, binaryTrajectory = false, pickedFile = false;
let drift = null, paintTicket = 0, snapshotTicket = 0, snapshotData = null;
let snapshotHost = null, activeRecord = null;
let navigationTarget = null, navigationTask = null;
let playbackGeneration = 0;
let playback = {fps:60, speed:1, step:1, loop:true};
function afterPaint(callback) { requestAnimationFrame(() => setTimeout(callback, 0)); }
function scheduleRender(reset = false) { const ticket=++paintTicket; afterPaint(() => { if(ticket===paintTicket)render(reset); }); }
function clearFollow() { drift=null;$("drift-enabled").checked=false;$("drift-state").textContent="未启用"; }
function sceneSettings() {
  return StructureScene.settings(frameData,{style:$("style").value,palette:$("palette").value,
    scale:Number($("radius-scale").value),cell:$("cell").checked,labels:$("labels").checked,
    hbonds:$("hbonds").checked,wrap:$("wrap").checked,drift,display:displayState});
}
function displayedFrame() {return StructureScene.transform(frameData,{drift,wrap:$("wrap").checked});}
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
function stop() { ++playbackGeneration; cancelAnimationFrame(timer); timer = null; $("play").textContent = "▶"; $("play").setAttribute("aria-label", "播放轨迹"); }
function updateTimeline() {
  if (!doc) return;
  $("timeline").max = doc.count - 1; $("timeline").value = frameIndex; $("timeline").disabled = doc.count < 2;
  $("frame-number").max = doc.count; $("frame-number").value = frameIndex + 1;
  $("frame-count").textContent = `/ ${doc.count}${streamComplete ? "" : "+"}`;
  const width=$("ticks").clientWidth;
  const canvas=document.createElement('canvas'),context=canvas.getContext('2d');
  context.font=getComputedStyle($("ticks")).font;
  const marks=StructureControls.timelineTicks(doc.count,width,text=>context.measureText(text).width);
  $("ticks").replaceChildren(...marks.map(({value,x})=>{
    const span=document.createElement('span');span.textContent=value;span.style.left=x+'px';return span;
  }));
}
function render(reset = false, strict = false) {
  if (!doc) return;
  try {
    if(!activeRecord)return;
    frameData = activeRecord.frame;
    if (!views) views = new StructureViews($("viewports"), chooseAtom, chooseBox);
    selection = selection.filter(i => i < frameData.atoms.length);
    views.renderScene(StructureScene.build(frameData,sceneSettings()),selection,reset);
    updateTimeline();
    if (!$("source-panel").hidden) $("source").value = activeRecord.text;
    $("source-title").textContent = doc.vaspPreview ? `第 ${frameIndex + 1} 帧 VASP 源码` : doc.xyz ? `第 ${frameIndex + 1} 帧源码` : "VASP 文件源码";
    updateSelection();
  } catch (error) { stop(); status(error.message, true); if(strict)throw error; }
}
function updateSelection() {
  $("atom-title").textContent=selection.length?`已选 ${selection.length}`:'';
  if(!frameData)return;
  const atoms=displayedFrame().atoms;
  $("measurement").textContent=selection.length>4?StructureSelection.formula(atoms,selection):StructureSelection.measure(atoms,selection);
  $("atom-list").textContent=selection.length===1?(()=>{const i=selection[0],a=atoms[i];return `${a.elem} #${i+1}  (${a.x.toFixed(4)}, ${a.y.toFixed(4)}, ${a.z.toFixed(4)}) Å`;})():selection.length<=4?selection.map(i=>`${atoms[i].elem} #${i+1}`).join(' → '):'';
  $("clear-selection").disabled=!selection.length;
  $("selection-count").textContent=`选中原子 · ${selection.length}`;
  $("apply-display").disabled=$("reset-selected-style").disabled=!selection.length;
}
function selectionChanged() {
  stop();
  updateSelection();
  const ticket=++paintTicket;
  afterPaint(()=>{if(ticket===paintTicket)views?.updateSelection(selection);});
}
function chooseAtom(index, shortcut = false) {
  if(!shortcut&&views?.mode!=="select")return;
  selection=StructureSelection.toggleIndices(selection,[index]);selectionChanged();
}
function chooseBox(indices, toggle) {
  if(!indices.length)return;
  selection=toggle?StructureSelection.toggleIndices(selection,indices):indices;selectionChanged();
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
$("clear-selection").onclick=()=>{selection=[];selectionChanged();};
$("display-settings").onclick=()=>{stop();populateElements();openPanel($("display-dialog"));};
$("display-close").onclick=()=>$("display-dialog").close();
$("show-elements").onclick=()=>{displayState.hiddenElements.clear();populateElements();scheduleRender();};
$("apply-display").onclick=()=>{
  const style=$("selection-style").value,palette=$("selection-palette").value,visible=$("selection-visible").value;
  displayState.apply(frameData,selection,{...(style?{style}:{}),...(palette?{palette,color:palette==='custom'?$("selection-color").value:null}:{}),...(visible?{visible:visible==='show'}:{})});scheduleRender();
};
$("reset-selected-style").onclick=()=>{displayState.reset(frameData,selection);scheduleRender();};
$("reset-display").onclick=()=>{resetDisplayState();populateElements();scheduleRender();};
async function go(index) {
  if(!doc)return;
  navigationTarget=Math.max(0,Math.min(doc.count-1,Number(index)||0));
  if(navigationTask)return navigationTask;
  const currentDoc=doc,generation=readGeneration;
  navigationTask=(async()=>{
    try {
      while(navigationTarget!==null&&doc===currentDoc&&generation===readGeneration) {
        const target=navigationTarget;navigationTarget=null;
        const record=await currentDoc.get(target);
        if(doc!==currentDoc||generation!==readGeneration)return;
        if(navigationTarget!==null&&navigationTarget!==target)continue;
        selection=StructureSelection.remap(frameData,record.frame,selection);
        displayState.transition(frameData,record.frame);
        activeRecord=record;frameData=record.frame;frameIndex=target;status("");
        let driftStopped=false;
        if(drift&&StructureSelection.remap(drift.referenceFrame,frameData,drift.indices).length!==drift.indices.length){clearFollow();driftStopped=true;}
        render();
        if(driftStopped)status('当前帧的原子无法与参考帧对应，已停用质心校正',true);
      }
    }catch(error){if(doc===currentDoc){stop();status(error.message,true);}}
    finally{if(generation===readGeneration)navigationTask=null;}
  })();
  return navigationTask;
}
function discardDocument() {doc?.dispose();doc=null;activeRecord=null;navigationTarget=null;navigationTask=null;}
async function showDocument(store,generation) {
  if(generation!==readGeneration){store.dispose();return;}
  doc=store;const record=await store.get(0);
  if(generation!==readGeneration)return;
  activeRecord=record;
  frameIndex=0;streamComplete=store.complete;render(true,true);status('');loading=false;
  // Render the first frame before starting any background index batch.
  afterPaint(()=>store.scan(()=>{if(doc===store){streamComplete=store.complete;updateTimeline();}})
    .catch(error=>{if(doc===store)status(`加载停止：${error.message}（保留已加载的 ${store.count} 帧）`,true);}));
}
async function loadFile(file, reload = false) {
  if (!file?.resourceUri || (!reload && fileRef?.resourceUri === file.resourceUri && (doc || loading))) return;
  pickedFile=false; binaryTrajectory=/\.traj$/i.test(file.name); clearFollow(); resetDisplayState();
  const generation = ++readGeneration;
  stop(); loading = true; streamComplete = false;
  fileRef = file; discardDocument(); frameIndex = 0; selection = [];
  $("source-toggle").hidden = binaryTrajectory; $("source-panel").hidden = true;
  $("filename").textContent = file.name; status("正在读取第一帧…");
  try {
    const call=async args=>{
      const result=await request('tools/call',{name:'read_trajectory_frames',arguments:{...(file.token?{token:file.token}:{}),...args}});
      if(result.isError)throw Error(result.content?.find(c=>c.text)?.text||'分段读取失败');
      return result.structuredContent;
    };
    const batch=await call({offset:0,frameLimit:1});
    if(generation!==readGeneration)return;
    if(batch?.supported===false)return loadFullFile(file);
    await showDocument(StructureTrajectory.host(file.name,call,batch),generation);
    if(!file.token)request('resources/subscribe',{uri:file.resourceUri}).catch(()=>{});
  }catch(error){if(generation===readGeneration)status(`加载停止：${error.message}`,true);}
  finally{if(generation===readGeneration)loading=false;}
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
    await showDocument(await StructureTrajectory.local(new Blob([text]),file.name),generation);
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
    stop(); discardDocument(); window.parent.postMessage({ jsonrpc: "2.0", id: message.id, result: {} }, "*");
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
  const run=++playbackGeneration;
  let previous=performance.now(), accumulator=0;
  const tick=async now=>{
    if(timer===null||run!==playbackGeneration)return;
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
      if(target!==frameIndex)await go(target);
    }
    if(timer!==null&&run===playbackGeneration)timer=requestAnimationFrame(tick);
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
for (const id of ["style", "palette", "radius-scale", "cell", "labels", "hbonds", "wrap"]) $(id).onchange = () => { stop(); status(""); scheduleRender(); };
function openPanel(panel) { if(!panel.open)panel.show(); }
for(const id of ['display-dialog','drift-dialog'])StructureControls.draggable($(id));
new ResizeObserver(()=>updateTimeline()).observe($("ticks"));
$("drift-settings").onclick=()=>{
  $("drift-reference").max=Math.max(0,(doc?.count||1)-1);
  openPanel($("drift-dialog"));
};
$("drift-close").onclick=()=>$("drift-dialog").close();
$("drift-use-selection").onclick=()=>{
  $("drift-atoms").value=selection.map(i=>i+1).join(', ');
  $("drift-source").value='indices';
};
$("drift-apply").onclick=async()=>{
  if(!doc)return;
  if(!$("drift-enabled").checked){clearFollow();$("drift-error").textContent='';render();return;}
  $("drift-apply").disabled=true;
  try {
    const reference=Number($("drift-reference").value);
    if(!Number.isInteger(reference)||reference<0||reference>=doc.count)throw Error('参考帧尚未加载或超出范围');
    const currentDoc=doc,generation=readGeneration,currentFrame=frameData;
    const currentIndices=$("drift-source").value==='all'?currentFrame.atoms.map((_,i)=>i):StructureControls.atomIndices($("drift-atoms").value,currentFrame.atoms.length);
    const referenceFrame=(await currentDoc.get(reference)).frame;
    if(doc!==currentDoc||generation!==readGeneration)return;
    let candidate=null;
    if($("drift-enabled").checked){
      const indices=StructureSelection.remap(currentFrame,referenceFrame,currentIndices);
      if(indices.length!==currentIndices.length)throw Error('所指定原子无法与参考帧对应');
      candidate={reference,referenceFrame,indices};
      StructureGeometry.removeDrift(frameData,referenceFrame,StructureSelection.remap(referenceFrame,frameData,indices),indices);
    }
    drift=candidate;$("drift-error").textContent='';render();
    $("drift-state").textContent=drift?`已应用：${drift.indices.length} 个原子 · 参考帧 ${reference}`:'未启用';
  }catch(error){$("drift-error").textContent=error.message;}finally{$("drift-apply").disabled=false;}
};
$("source-toggle").onclick = () => { stop(); $("source-panel").hidden = !$("source-panel").hidden; if(doc)$("source").value=activeRecord.text; };
request("ui/initialize", { protocolVersion: "2026-01-26", appInfo: { name: "Structure Viewer", version: "0.10.0" }, appCapabilities: {} })
  .then(() => { send("ui/notifications/initialized", {}); status("已连接，等待文件…"); })
  .catch(error => status(`连接失败：${error.message}`, true));

$("open-file").onclick=()=>$("file-picker").click();
$("file-picker").onchange=async()=>{
  const file=$("file-picker").files[0];if(!file)return;
  const generation=++readGeneration;stop();clearFollow();resetDisplayState();pickedFile=true;fileRef=null;frameIndex=0;selection=[];discardDocument();
  binaryTrajectory=/\.traj$/i.test(file.name);$("source-toggle").hidden=binaryTrajectory;$("source-panel").hidden=true;status("");$("filename").textContent=file.name;
  try {
    loading=true;streamComplete=false;
    await showDocument(await StructureTrajectory.local(file),generation);
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
  let job;
  try {
    job=await mediaCall({action:'begin',kind:'image',name});
    await uploadMedia(job.id,result.bytes);
    await saveMedia(job.id,snapshotHost,'snapshot');
  }catch(error){$("snapshot-result").textContent=error.message;}
  finally{if(job)await mediaCall({action:'cancel',id:job.id}).catch(()=>{});$("snapshot-save").disabled=false;$("snapshot-close").disabled=false;}
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
