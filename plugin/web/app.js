"use strict";
const $ = id => document.getElementById(id);
const pending = new Map();
let nextId = 1, hostName = "当前主机", fileRef, doc, frameIndex = 0, frameData, views;
let selection = [], timer = null, loading = false, readGeneration = 0;
let displayState = new StructureSelection.DisplayState();
let streamComplete = true, binaryTrajectory = false, pickedFile = false;
let drift = null, paintTicket = 0, selectionTicket = 0, snapshotTicket = 0, snapshotData = null;
let snapshotHost = null, activeRecord = null, snapshotSaving = false;
let navigationTarget = null, navigationTask = null;
let playbackGeneration = 0;
let timelineSeek=null,viewVisible=true,resumeWhenVisible=false,tickLayout='';
let concurrentIndex=false;
let desktopLanguage=false;
let inspector;
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
function showImportNote(text) {
  const fragments=document.createDocumentFragment();
  for(const [i,part] of text.split(/ · |；(?=部分元素|未提供 units)/).entries()) {
    if(i)fragments.append(' · ');
    const span=document.createElement('span');
    span.textContent=part;
    fragments.append(span);
  }
  $("import-note").replaceChildren(fragments);
}
function status(text, error = false) { $("status").textContent = error ? text : ""; $("status").hidden = !error; }
function displayPlayback(playing) {
  const button = $("play"), label = playing ? "暂停轨迹" : "播放轨迹";
  button.querySelector("use").setAttribute("href", "#i-" + (playing ? "pause" : "play"));
  button.setAttribute("aria-label", label);
  button.title = label;
}
function stop() { ++playbackGeneration; cancelAnimationFrame(timer); timer = null; timelineSeek=null;resumeWhenVisible=false;doc?.setPlayback?.(frameIndex,false);displayPlayback(false); }
function updateTimeline() {
  if (!doc) return;
  $("timeline").max = doc.count - 1; if(!timelineSeek)$("timeline").value = frameIndex; $("timeline").disabled = doc.count < 2;
  $("frame-number").max = doc.count;
  if(document.activeElement!==$("frame-number"))$("frame-number").value = frameIndex + 1;
  const total = String(doc.count) + (streamComplete ? "" : "+");
  $("frame-total").textContent = total;
  const single = streamComplete && doc.count === 1;
  const changed=$("trajectory-tools").classList.contains("single-frame")!==single;
  $("trajectory-tools").classList.toggle("single-frame", single);
  if(changed)views?.resizeToLayout();
  $("frame-number").readOnly = single;
  $("first").disabled = $("previous").disabled = frameIndex === 0;
  $("next").disabled = $("last").disabled = frameIndex === doc.count - 1;
  $("play").disabled = !doc.count || single;
  $("frame-number").closest(".frame-label").style.setProperty("--frame-digits", Math.max(2, total.length) + "ch");
  if (single) return;
  const width=$("ticks").clientWidth;
  if(!width)return;
  const font=getComputedStyle($("ticks")).font,key=JSON.stringify([doc.count,width,font]);
  if(tickLayout===key)return;tickLayout=key;
  const canvas=document.createElement('canvas'),context=canvas.getContext('2d');
  context.font=font;
  const marks=StructureControls.timelineTicks(doc.count,width,text=>context.measureText(text).width);
  $("ticks").replaceChildren(...marks.map(({value,x,tickX})=>{
    const span=document.createElement('span');span.textContent=value;span.style.left=x+'px';span.style.setProperty('--tick-offset',(tickX-x)+'px');return span;
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
    inspector?.update(frameData,frameIndex,selection);
  } catch (error) { stop(); status(error.message, true); if(strict)throw error; }
}
function updateSelection() {
  const count = selection.length;
  $("atom-panel").hidden = count === 0;
  $("atom-title").textContent=selection.length?`已选 ${selection.length}`:'';
  if(!frameData)return;
  const atoms=displayedFrame().atoms;
  $("measurement").textContent=selection.length>4?StructureSelection.formula(atoms,selection):StructureSelection.measure(atoms,selection);
  $("atom-list").textContent=selection.length===1?(()=>{const i=selection[0],a=atoms[i];return `${a.elem} #${i+1}  (${a.x.toFixed(4)}, ${a.y.toFixed(4)}, ${a.z.toFixed(4)}) Å`;})():selection.length<=4?selection.map(i=>`${atoms[i].elem} #${i+1}`).join(' → '):'';
  $("clear-selection").disabled=!selection.length;
  $("selection-count").textContent=`选中原子 · ${selection.length}`;
  $("reset-selected-style").disabled = !count;
  for (const [field, control] of selectionControls) {
    control.disabled = !count;
    if (!$("display-dialog").open) continue;
    const valueAt = i => displayState.overrides.get(i)?.[field];
    const first = valueAt(selection[0]);
    const mixed = selection.some(i => valueAt(i) !== first);
    control.value = mixed ? "mixed" : first == null ? "" : field === "visible" ? (first ? "show" : "hide") : first;
  }
}
function selectionChanged() {
  stop();
  updateSelection();
  inspector?.update(frameData,frameIndex,selection,true);
  const ticket=++selectionTicket;
  afterPaint(()=>{if(ticket===selectionTicket)views?.updateSelection(selection);});
}
function chooseAtom(index, shortcut = false) {
  if(!shortcut&&views?.mode!=="select")return;
  selection=StructureSelection.toggleIndices(selection,[index]);selectionChanged();
}
function chooseBox(indices, toggle) {
  if(!indices.length)return;
  selection=toggle?StructureSelection.toggleIndices(selection,indices):indices;selectionChanged();
}
function resetDisplayState() {
  displayState = new StructureSelection.DisplayState(); selection = [];
  $("atom-panel").hidden = true;
}
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
$("display-settings").onclick=()=>{openPanel($("display-dialog"));populateElements();};
$("display-close").onclick=()=>$("display-dialog").close();
$("show-elements").onclick=()=>{displayState.showAll();populateElements();scheduleRender();};
const selectionControls = [
  ["style", $("selection-style")], ["palette", $("selection-palette")], ["visible", $("selection-visible")]
];
for (const [field, control] of selectionControls) {
  control.disabled = true;
  control.onchange = () => {
    if (!frameData || !selection.length || control.value === 'mixed') return;
    const value = control.value === "" ? null : field === "visible" ? control.value === "show" : control.value;
    displayState.apply(frameData, selection, {[field]: value});
    scheduleRender();
  };
}
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
function discardDocument() {
  doc?.dispose(); doc=null; activeRecord=null; navigationTarget=null; navigationTask=null;
  document.body.classList.remove("has-structure");
  $("drift-settings").disabled = true;
  inspector?.clear();
}
async function showDocument(store,generation) {
  if(generation!==readGeneration){store.dispose();return;}
  doc=store;store.setActive?.(viewVisible);store.concurrentIndex=concurrentIndex&&!pickedFile;
  const record=await store.get(0);
  if(generation!==readGeneration)return;
  activeRecord=record;
  document.body.classList.add("has-structure");$("drift-settings").disabled=false;
  frameIndex=0;streamComplete=store.complete;render(true,true);status('');loading=false;
  // Render the first frame before starting any background index batch.
  afterPaint(()=>store.scan(()=>{if(doc===store){streamComplete=store.complete;updateTimeline();}})
    .catch(error=>{if(doc===store){stop();streamComplete=true;updateTimeline();status(`加载停止：${error.message}（保留已加载的 ${store.count} 帧）`,true);}}));
}
async function loadFile(file, reload = false) {
  if (!file?.resourceUri || (!reload && (fileRef?.resourceUri === file.resourceUri || fileRef?.linkUri === file.resourceUri) && (doc || loading))) return;
  pickedFile=false; binaryTrajectory=/\.traj$/i.test(file.name); clearFollow(); resetDisplayState();
  const generation = ++readGeneration;
  stop(); loading = true; streamComplete = false;
  fileRef = file; discardDocument(); frameIndex = 0; selection = [];
  $("source-toggle").hidden = binaryTrajectory; $("source-panel").hidden = true;
  $("filename").removeAttribute("data-empty-title"); $("filename").textContent = file.name; $("import-note").textContent=""; status("正在读取第一帧…");
  try {
    const linkedTrajectory = /\.svtraj$/i.test(file.name);
    if (linkedTrajectory) {
      const reply = await request('tools/call', {name:'resolve_lammps_link', arguments:file.token?{token:file.token}:{}});
      if (generation!==readGeneration) return;
      if (!reply.structuredContent?.file) throw Error(reply.content?.[0]?.text || '无效的 Atom Lens 轨迹链接。');
      file = {...reply.structuredContent.file, linkUri:file.resourceUri};
      fileRef = file;
      $("filename").textContent = file.name;
    }
    if($("import-format").value!=="auto" || !/^(POSCAR|CONTCAR|XDATCAR)$|\.(xyz|extxyz|traj|vasp)$/i.test(file.name) || file.companions?.length) {
      const files=await Promise.all([file,...(file.companions||[])].map(StructureHostFiles.open));
      if(generation!==readGeneration)return;
      if(!files[0] && files.length===1) {
        const resource=await request('resources/read',{uri:file.resourceUri});
        const part=resource.contents?.[0];
        if (!part) throw Error('Codex 未返回文件内容');
        files[0]=new File([part.text ?? Uint8Array.from(atob(part.blob),c=>c.charCodeAt(0))],file.name);
      }
      const imported=await StructureImport.open(files,{format:linkedTrajectory ? "lammps-dump-text" : $("import-format").value});
      await showDocument(imported.store,generation);
      if(generation===readGeneration)showImportNote([file.discoveryNote,imported.note].filter(Boolean).join(' · '));
      return;
    }
    const call=async args=>{
      const result=await request('tools/call',{name:'read_trajectory_frames',arguments:{...(file.token?{token:file.token}:{}),...args}});
      if(result.isError)throw Error(result.content?.find(c=>c.text)?.text||'分段读取失败');
      return result.structuredContent;
    };
    const batch=await call({offset:0,frameLimit:1});
    if(generation!==readGeneration)return;
    if(batch?.supported===false)return loadFullFile(file);
    await showDocument(StructureTrajectory.host(file.name,call,batch),generation);
    if(generation===readGeneration && file.discoveryNote)showImportNote(file.discoveryNote);
    if(!file.token)request('resources/subscribe',{uri:file.resourceUri}).catch(()=>{});
  }catch(error){if(generation===readGeneration)status(`加载停止：${error.message}`,true);}
  finally{if(generation===readGeneration)loading=false;}
}
async function loadFullFile(file) {
  if (!file?.resourceUri) return;
  if (/\.traj$/i.test(file.name)) { status("当前宿主不支持轨迹分段读取，请使用“打开”选择本地 .traj 文件", true); return; }
  loading = true; const generation = ++readGeneration; stop();
  $("source-toggle").hidden=false;
  fileRef = file; $("filename").removeAttribute("data-empty-title"); $("filename").textContent = file.name; $("import-note").textContent=""; status("");
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
  if(message.method==='atomlens/language'&&desktopLanguage){StructureI18n.setLanguage(message.params?.language);return;}
  if(message.method==='atomlens/visibility'){
    if(viewVisible===Boolean(message.params?.visible))return;
    viewVisible=Boolean(message.params?.visible);doc?.setActive?.(viewVisible);
    if(!viewVisible){const playing=timer!==null||timelineSeek?.playing;stop();resumeWhenVisible=playing;}
    else if(resumeWhenVisible){resumeWhenVisible=false;startPlayback(false);}
    return;
  }
  if (pending.has(message.id)) {
    const p = pending.get(message.id); pending.delete(message.id); clearTimeout(p.timeout);
    message.error ? p.reject(Error(message.error.message || "宿主请求失败")) : p.resolve(message.result); return;
  }
  if (message.method === "ui/notifications/tool-input" && message.params?.arguments?.file) loadFile(message.params.arguments.file);
  if (message.method === "ui/notifications/tool-result") {
    const result=message.params?.structuredContent;
    if(result?.host){hostName=result.host;$("path-host").textContent=`${hostName} 上的完整路径`;}
    if(result?.file || result?.choices)openSelectionResult(result);
    else if(result?.browser&&!doc)$("path-dialog").showModal();
  }
  if (message.method === "notifications/resources/updated" && message.params?.uri === fileRef?.resourceUri) {
    // Keep this opening fixed. A growing source must not reset its index/camera.
    // Reopen explicitly to include newly written frames.
  }
  if (message.method === "ui/resource-teardown" && message.id !== undefined) {
    stop(); discardDocument(); window.parent.postMessage({ jsonrpc: "2.0", id: message.id, result: {} }, "*");
  }
});
function beginTimelineSeek() {
  if(timelineSeek)return;
  const playing=timer!==null;stop();
  timelineSeek={playing,document:doc,generation:readGeneration};doc?.setPlayback?.(frameIndex,true);displayPlayback(playing);
}
async function finishTimelineSeek() {
  const seek=timelineSeek;if(!seek)return;
  await go($("timeline").value);
  if(timelineSeek!==seek||seek.document!==doc||seek.generation!==readGeneration)return;
  timelineSeek=null;updateTimeline();
  if(seek.playing&&viewVisible)startPlayback(false);else {doc?.setPlayback?.(frameIndex,false);displayPlayback(false);}
}
$("timeline").addEventListener("pointerdown",beginTimelineSeek);
$("timeline").addEventListener("input",e=>{beginTimelineSeek();go(e.target.value);});
$("timeline").addEventListener("change",finishTimelineSeek);
window.addEventListener("pointerup",finishTimelineSeek);
window.addEventListener("pointercancel",finishTimelineSeek);
$("timeline").addEventListener("blur",finishTimelineSeek);
$("frame-number").addEventListener("change", e => { stop(); go(Number(e.target.value) - 1); });
$("frame-number").addEventListener("keydown", e => {if(e.key==='Enter'){e.preventDefault();stop();go(Number(e.target.value)-1);e.target.blur();}});
$("previous").onclick = () => { stop(); go(frameIndex - 1); };
$("next").onclick = () => { stop(); go(frameIndex + 1); };
function startPlayback(restart=true) {
  if (timer!==null||!viewVisible||!doc?.count || (doc.count < 2 && streamComplete)) return;
  if(restart&&frameIndex===doc.count-1 && streamComplete)go(0);
  displayPlayback(true);
  doc.setPlayback?.(frameIndex,true);doc.prefetch?.(frameIndex,playback.step);
  const run=++playbackGeneration;
  let previous=performance.now(), accumulator=0;
  const tick=async now=>{
    if(timer===null||run!==playbackGeneration)return;
    if(streamComplete&&doc.count===1){stop();return;}
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
      if(target!==frameIndex){await go(target);previous=performance.now();}
    }
    if(timer!==null&&run===playbackGeneration){doc.setPlayback?.(frameIndex,true);doc.prefetch?.(frameIndex,playback.step);timer=requestAnimationFrame(tick);}
  };
  timer=requestAnimationFrame(tick);
}
$("play").onclick=()=>{if(timer!==null||timelineSeek?.playing)return stop();startPlayback();};
function updatePlaybackSettings(){
  const fps=Number($("animation-fps").value),step=Number($("playback-step").value),speed=Number($("playback-speed").value);
  if(!Number.isInteger(fps)||fps<1||fps>120||!Number.isInteger(step)||step<1||step>10000||!Number.isFinite(speed)||speed<=0)return;
  playback={fps,speed,step,loop:$("playback-loop").checked};
}
for(const id of ['animation-fps','playback-speed','playback-step','playback-loop'])$(id).addEventListener('input',updatePlaybackSettings);
$("reset").onclick = () => views?.fit();
$("view-reset").onclick = () => views?.fit();
$("navigation-mode").onchange = event => views?.setMode(event.target.value);
$("orientation").onchange = event => views?.setOrientation(event.target.value);
$("layout").onchange = event => views?.setLayout(event.target.value);
$("expand").onclick = () => views?.toggleExpand();
for (const mode of ["rotate", "pan", "zoom", "select", "box"]) $(mode).onclick = () => views?.setMode(mode);
$("first").onclick = () => { stop(); go(0); };
$("last").onclick = () => { stop(); if (doc) go(doc.count - 1); };
// Display changes repaint the current scene without altering playback intent.
// The existing playback loop reads these same settings for subsequent frames.
for (const id of ["style", "palette", "radius-scale", "cell", "labels", "hbonds", "wrap"]) $(id).onchange = () => { status(""); scheduleRender(); };
function openPanel(panel) { if(!panel.open)panel.show(); }
for(const id of ['display-dialog','drift-dialog'])StructureControls.draggable($(id));
new ResizeObserver(updateTimeline).observe($("ticks"));
inspector=new StructureInspector.Panel(()=>views?.resizeToLayout(),index=>{selection=[index];selectionChanged();});
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
request("ui/initialize", { protocolVersion: "2026-01-26", appInfo: { name: "Atom Lens", version: "0.13.3" }, appCapabilities: {} })
  .then(result => {
    concurrentIndex=result?.hostCapabilities?.atomLensConcurrentIndex===true;
    desktopLanguage=['en','zh-CN'].includes(result?.hostContext?.atomLensLanguage);
    if(desktopLanguage)StructureI18n.setLanguage(result.hostContext.atomLensLanguage);
    send("ui/notifications/initialized", {});
  })
  .catch(error => status(`连接失败：${error.message}`, true));
document.addEventListener('atomlens-language-change',event=>{
  if(desktopLanguage)send('atomlens/language',{language:event.detail});
});

async function openStructure(files, format = $("import-format").value) {
  const file = files[0];
  pickedFile=true;fileRef=null;
  const generation = ++readGeneration;
  stop(); clearFollow(); resetDisplayState(); discardDocument();
  ++snapshotTicket; snapshotData = null;
  for (const id of ["snapshot-dialog", "drift-dialog", "display-dialog"]) $(id).close();
  frameIndex = 0; frameData = null; loading = true; streamComplete = false;
  if (views) {
    for (const pane of views.panes) {
      pane.ready = false;
      pane.viewer.removeAllModels(); pane.viewer.removeAllShapes(); pane.viewer.removeAllLabels();
      pane.viewer.render();
    }
  }
  $("atom-title").textContent = $("measurement").textContent = $("atom-list").textContent = "";
  $("frame-total").textContent = "—"; $("timeline").disabled = true;
  $("source-panel").hidden = true; $("source-toggle").hidden = /\.traj$/i.test(file.name);
  $("filename").removeAttribute("data-empty-title"); $("filename").textContent = file.name; $("import-note").textContent=""; status("");
  try {
    const imported = await StructureImport.open(files, {format});
    if (generation !== readGeneration) { imported.store.dispose(); return; }
    $("filename").textContent = imported.name;
    $("source-toggle").hidden = /\.traj$/i.test(imported.name);
    await showDocument(imported.store, generation);
    if (generation !== readGeneration) return;
    showImportNote(imported.note);
    return {name: imported.name};
  } catch (error) {
    if (generation !== readGeneration) return;
    discardDocument();
    status(error.message, true);
    return {name: file.name, error: error.message};
  } finally { if (generation === readGeneration) loading = false; }
}
$("open-empty").onclick = $("open-file").onclick = () => $("file-picker").click();
$("file-picker").onchange = () => {
  const files = Array.from($("file-picker").files); $("file-picker").value = "";
  if (files.length) openStructure(files);
};
document.addEventListener("dragover", event => event.preventDefault());
document.addEventListener("drop", event => {
  event.preventDefault(); const files = Array.from(event.dataTransfer.files);
  if (files.length) openStructure(files);
});
window.addEventListener("pagehide", () => { stop(); discardDocument(); });
function snapshotOptions(){return {dpi:Number($("snapshot-dpi").value),format:$("snapshot-format").value,transparent:$("snapshot-transparent").checked,crop:$("snapshot-crop").checked};}
function syncSnapshotButton() {
  const button=$("snapshot-save");
  button.disabled=snapshotSaving||!snapshotHost||!snapshotData;
  if(snapshotSaving)button.textContent='正在保存…';
  else if(!snapshotHost)button.textContent='保存快照';
  else if(!snapshotData&&!$("snapshot-result").textContent)button.textContent='正在生成预览…';
  else button.textContent=$("snapshot-destination").value==='server'?'保存到服务器':'保存到 Mac…';
}
function refreshSnapshot() {
  const ticket=++snapshotTicket;
  snapshotData=null;$("snapshot-result").textContent='';syncSnapshotButton();
  afterPaint(async()=>{
    if(ticket!==snapshotTicket||!$("snapshot-dialog").open||!snapshotHost)return;
    try {
      const result=await StructureSnapshot.capture(views,snapshotOptions());
      if(ticket!==snapshotTicket)return;
      snapshotData=result;$("snapshot-preview").src=result.preview;$("snapshot-preview").hidden=false;
    }catch(error){
      if(ticket!==snapshotTicket)return;
      $("snapshot-preview").hidden=true;$("snapshot-result").textContent=error.message;
    }
    syncSnapshotButton();
  });
}
$("snapshot").onclick=async()=>{
  if(!views||!doc)return;stop();$("snapshot-name").value=$("filename").textContent.replace(/\.[^.]+$/,'').replace(/[^\p{L}\p{N}_ .()\-]/gu,'_')+'-frame-'+(frameIndex+1);
  const ticket=++snapshotTicket;
  snapshotData=null;snapshotSaving=false;$("snapshot-controls").disabled=true;$("snapshot-preview").hidden=true;
  $("snapshot-dialog").showModal();snapshotHost=null;
  $("snapshot-result").textContent='';syncSnapshotButton();
  try {
    const response=await request('tools/call',{name:'snapshot_context',arguments:fileRef?.token?{token:fileRef.token}:{}});
    if(ticket!==snapshotTicket||!$("snapshot-dialog").open)return;
    if(response.isError||!response.structuredContent)throw Error('无法读取保存位置，请重新打开查看器');
    snapshotHost=response.structuredContent;
    const serverOption=$("snapshot-destination").querySelector('[value="server"]');
    serverOption.hidden=snapshotHost.nativePicker||pickedFile;
    serverOption.textContent='服务器 · '+snapshotHost.host;
    $("snapshot-destination").value=(!snapshotHost.nativePicker&&!pickedFile)?'server':'local';
    $("snapshot-directory").value=pickedFile?'':snapshotHost.directory;
    $("snapshot-controls").disabled=false;updateSnapshotDestination();refreshSnapshot();
  }catch(error){if(ticket===snapshotTicket)$("snapshot-result").textContent=error.message;}
};
for(const id of ["snapshot-format","snapshot-dpi","snapshot-transparent","snapshot-crop"])$(id).onchange=()=>{
  $("snapshot-transparent").disabled=$("snapshot-format").value!=='png';refreshSnapshot();
};
$("snapshot-close").onclick=()=>$("snapshot-dialog").close();
$("snapshot-dialog").addEventListener("cancel",event=>{if(snapshotSaving)event.preventDefault();});
$("snapshot-dialog").addEventListener("close",()=>{if(!$("snapshot-dialog").open)++snapshotTicket;});
function updateSnapshotDestination(){
  const server=$("snapshot-destination").value==='server';
  $("snapshot-directory-row").hidden=!server;
  syncSnapshotButton();
}
$("snapshot-destination").onchange=updateSnapshotDestination;
$("snapshot-save").onclick=async()=>{
  if(snapshotSaving||!snapshotData||!snapshotHost)return;
  const result=snapshotData,format=$("snapshot-format").value,name=$("snapshot-name").value+'.'+format;
  if(!/^[\p{L}\p{N}_ .()\-]{1,100}\.(png|jpeg|pdf)$/u.test(name)||name.startsWith('.')){$("snapshot-result").textContent='请使用字母、数字、中文、空格、下划线或短横线命名';return;}
  snapshotSaving=true;$("snapshot-controls").disabled=true;$("snapshot-close").disabled=true;syncSnapshotButton();
  let job;
  try {
    job=await mediaCall({action:'begin',kind:'image',name});
    await uploadMedia(job.id,result.bytes);
    await saveMedia(job.id,snapshotHost,'snapshot');
  }catch(error){$("snapshot-result").textContent=error.message;}
  finally{if(job)await mediaCall({action:'cancel',id:job.id}).catch(()=>{});snapshotSaving=false;$("snapshot-controls").disabled=false;$("snapshot-close").disabled=false;syncSnapshotButton();}
};

$("open-path").onclick=async()=>{
  stop();$("companion-paths").value='';$("structure-path").value=fileRef?.directory||fileRef?.path||'';$("path-error").textContent='';$("path-dialog").showModal();
  try {const r=await request('tools/call',{name:'open_structure_path',arguments:{}});if(r.structuredContent?.host){hostName=r.structuredContent.host;$("path-host").textContent=`${hostName} 上的完整路径`;}}catch(e){$("path-error").textContent=e.message;}
};
$("path-close").onclick=()=>$("path-dialog").close();
$("path-load").onclick=async()=>{
  const path=$("structure-path").value.trim();if(!path)return;
  $("path-load").disabled=true;$("path-error").textContent='';
  try {
    const result=await request('tools/call',{name:'open_structure_path',arguments:{path,companions:$("companion-paths").value.split(/\r?\n/).map(line=>line.trim()).filter(Boolean)}});
    if(result.isError)throw Error(result.content?.find(c=>c.text)?.text||'打开失败');
    if(!result.structuredContent?.file && !result.structuredContent?.choices)throw Error('未返回结构文件');
    $("path-dialog").close();await openSelectionResult(result.structuredContent);
  }catch(e){$("path-error").textContent=e.message;}finally{$("path-load").disabled=false;}
};
$("structure-path").onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();$("path-load").click();}};

let discoveredChoices=[];
async function openSelectionResult(result){
  if(result.file)return loadFile(result.file);
  discoveredChoices=result.choices||[];
  if(!discoveredChoices.length)return;
  $("discovery-path").textContent=result.directory||'';
  $("discovery-options").replaceChildren(...discoveredChoices.map((item,index)=>new Option(item.label,String(index))));
  $("discovery-dialog").showModal();
}
$("discovery-close").onclick=()=>$("discovery-dialog").close();
$("discovery-open").onclick=()=>{
  const choice=discoveredChoices[Number($("discovery-options").value)];
  if(choice){$("discovery-dialog").close();loadFile(choice.file);}
};

const headerMenus = [...document.querySelectorAll(".header-menu,.bottom-menu")];
for (const menu of headerMenus) {
  menu.addEventListener("toggle", () => {
    if(menu.open)for(const other of headerMenus)if(other!==menu)other.open=false;
  });
  menu.addEventListener("click", event => {
    // Leave selects and checkboxes open for repeated adjustments. An action
    // can open its own dialog; do not steal focus back from that dialog.
    if(event.target.closest("[data-close-menu]"))menu.open=false;
  });
}
document.addEventListener("pointerdown", event => {
  if(event.target.closest("#chem-choice-menu"))return;
  for(const menu of headerMenus)if(menu.open&&!menu.contains(event.target))menu.open=false;
});
window.addEventListener("keydown", event => {
  const preset=axisShortcut(event);
  if(preset && views?.panes[views.active].ready && !document.querySelector("dialog:modal")){
    event.preventDefault();
    views.setOrientation(preset);
  }
  if (event.key === "Escape" && !document.querySelector("#chem-choice-menu")) {
    const menu=headerMenus.find(menu=>menu.open);
    if(menu){menu.open=false;menu.querySelector("summary").focus();event.preventDefault();}
  }
});
const themeControls = {mode: $("theme-mode"), fontSize: $("theme-size")};
function syncThemeControls() {
  const settings = chemistryTheme.read();
  themeControls.mode.value = settings.mode;
  themeControls.fontSize.value = String(settings.fontSize);
}
for (const control of Object.values(themeControls)) control.onchange = () => {
  chemistryTheme.save({mode:themeControls.mode.value,fontSize:Number(themeControls.fontSize.value)});
};
syncThemeControls();
