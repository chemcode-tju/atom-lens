"use strict";
const $ = id => document.getElementById(id);
const pending = new Map();
let nextId = 1, fileRef, resourceMeta = {}, doc, frameIndex = 0, frameData, views;
let dirty = false, sourceDirty = false, selection = [], timer = null, loading = false, readGeneration = 0;
let saveInProgress = false, editRevision = 0;
let previewOnly = false, streamComplete = true, binaryTrajectory = false, pickedFile = false;
let anchor = null, paintTicket = 0, snapshotTicket = 0, snapshotData = null;
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
function request(method, params) {
  const id = nextId++;
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => { pending.delete(id); reject(Error(`请求超时：${method}`)); }, 60000);
    pending.set(id, { resolve, reject, timeout });
    window.parent.postMessage({ jsonrpc: "2.0", id, method, params }, "*");
  });
}
function status(text, error = false) { $("status").textContent = error ? text : ""; $("status").hidden = !error; }
function changed(value = true) {
  dirty = value;
  $("save").textContent = dirty || sourceDirty ? "保存 *" : "保存";
  $("save").disabled = !(dirty || sourceDirty) || !resourceMeta.writable || saveInProgress;
}
function stop() { cancelAnimationFrame(timer); timer = null; $("play").textContent = "▶"; $("play").setAttribute("aria-label", "播放轨迹"); }
function editingMode(preview) {
  previewOnly = preview;
  $("enable-edit").hidden = !preview;
  $("source").readOnly = preview;
  $("apply-source").disabled = preview;
}
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
    if (!views) views = new StructureViews($("viewports"), chooseAtom);
    selection = selection.filter(i => i < frameData.atoms.length);
    const displayed = $("wrap").checked ? StructureGeometry.wrap(frameData) : frameData;
    const follow = $("follow").checked ? StructureGeometry.followAtom(displayed, anchor) : null;
    views.render(displayed, {style: $("style").value, palette: $("palette").value,
      scale: Number($("radius-scale").value), cell: $("cell").checked, labels: $("labels").checked, hbonds: $("hbonds").checked, lighting: true, follow}, selection, reset);
    updateTimeline();
    if (!sourceDirty && !$("source-panel").hidden) $("source").value = doc.frameText(frameIndex);
    $("source-title").textContent = doc.xyz ? `第 ${frameIndex + 1} 帧源码` : "VASP 文件源码";
    updateSelection();
  } catch (error) { stop(); status(error.message, true); }
}
function updateSelection() {
  $("atom-panel").hidden = selection.length === 0;
  if (!selection.length) return;
  const index = selection[selection.length - 1], atom = frameData.atoms[index];
  $("atom-title").textContent = `${atom.elem} · 原子 ${index + 1}`;
  ["x", "y", "z"].forEach(key => { $("coord-" + key).value = atom[key].toFixed(6); $("coord-" + key).disabled = !doc.xyz || previewOnly; });
  $("apply-atom").disabled = !doc.xyz || previewOnly;
  $("distance").textContent = selection.length === 2 ? `直接距离 ${Math.hypot(...["x", "y", "z"].map(k => frameData.atoms[selection[0]][k] - atom[k])).toFixed(4)} Å` : "";
}
function chooseAtom(index) {
  stop(); selection = selection.includes(index) ? selection.filter(i => i !== index) : [...selection.slice(-1), index]; render();
}
function applySource() {
  if (previewOnly) return !sourceDirty;
  if (!sourceDirty) return true;
  try {
    const replacement = doc.replaceFrame(frameIndex, $("source").value);
    replacement.frame(Math.min(frameIndex, replacement.count - 1));
    doc = replacement; frameIndex = Math.min(frameIndex, doc.count - 1);
    sourceDirty = false; editRevision++; changed(); render();
    status("源码已应用到预览；点击保存写回文件。已有计算属性未重算。");
    return true;
  } catch (error) { status(`源码未应用：${error.message}`, true); return false; }
}
function go(index) {
  if (!doc || !applySource()) return;
  const target = Math.max(0, Math.min(doc.count - 1, Number(index) || 0));
  try { if($("follow").checked)StructureGeometry.followAtom(doc.frame(target),anchor); }
  catch(error){stop();status(error.message,true);return;}
  frameIndex=target;selection=[];status("");render();
}
async function loadFile(file, reload = false) {
  if (!file?.resourceUri || (!reload && fileRef?.resourceUri === file.resourceUri && (doc || loading))) return;
  pickedFile=false; binaryTrajectory=/\.traj$/i.test(file.name); clearFollow();
  if (!/\.(extxyz|xyz|traj)$/i.test(file.name)) { frameIndex=0; return loadFullFile(file); }
  const generation = ++readGeneration;
  stop(); loading = true; streamComplete = false;
  fileRef = file; doc = null; resourceMeta = {}; frameIndex = 0; selection = []; sourceDirty = false;
  editingMode(true); $("enable-edit").hidden = binaryTrajectory; $("source-toggle").hidden = binaryTrajectory; $("source-panel").hidden = true; changed(false);
  $("filename").textContent = file.name; status("正在读取第一帧…");
  let offset = 0, version;
  try {
    while (generation === readGeneration) {
      const result = await request("tools/call", { name: "read_trajectory_frames", arguments: {
        offset, frameLimit: offset === 0 ? 1 : 32, ...(version ? { version } : {})
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
      if (first) { doc.frame(0); render(true); request("resources/subscribe", { uri: file.resourceUri }).catch(() => {}); }
      else updateTimeline();
      const percent = batch.totalBytes ? Math.floor(offset / batch.totalBytes * 100) : 100;
      status(streamComplete ? `${doc.count} 帧已加载 · 点击“启用编辑”可修改文件` : `已加载 ${doc.count} 帧 · ${percent}% · 可拖动已加载部分`);
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
  fileRef = file; $("filename").textContent = file.name; status("正在读取完整文件与保存版本，请稍候…");
  $("enable-edit").disabled = true;
  try {
    const result = await request("resources/read", { uri: file.resourceUri, _meta: { "openai/resource": { representation: "text" } } });
    if (generation !== readGeneration) return;
    const content = result.contents?.find(c => c.uri === file.resourceUri) || result.contents?.[0];
    if (!content) throw Error("Codex 未返回文件内容");
    let text = content.text;
    if (text === undefined && content.blob) text = new TextDecoder().decode(Uint8Array.from(atob(content.blob), c => c.charCodeAt(0)));
    if (typeof text !== "string") throw Error("文件超过宿主读取限制或不是文本文件");
    const parsed = new StructureParser.StructureDocument(file.name, text); parsed.frame(0);
    doc = parsed; resourceMeta = content._meta?.["openai/resource"] || {};
    streamComplete = true; editingMode(false);
    frameIndex = Math.min(frameIndex, doc.count - 1); selection = []; sourceDirty = false; changed(false); render(true);
    status(`${doc.count} 帧已加载 · ${resourceMeta.writable ? "可以编辑保存" : "宿主只读"} · ${$("style").value === "sphere" ? "原子球显示" : "连线按距离推断"}`);
    request("resources/subscribe", { uri: file.resourceUri }).catch(() => {});
  } catch (error) { if (generation === readGeneration) status(`完整读取失败：${error.message}`, true); }
  finally { if (generation === readGeneration) { loading = false; $("enable-edit").disabled = false; } }
}
async function save() {
  if (!doc || !resourceMeta.writable || saveInProgress || !applySource()) return;
  saveInProgress = true; const revision = editRevision; changed(dirty); status("正在保存…");
  try {
    const result = await request("openai/resources/write", { uri: fileRef.resourceUri, text: doc.serialize(), ...(resourceMeta.etag ? { ifMatch: resourceMeta.etag } : {}) });
    if (result.outcome === "conflict") throw Error("文件已被其他程序修改，本次未覆盖；请复制当前源码后重新打开文件。");
    if (result.outcome === "too-large") throw Error(`文件超过宿主保存上限 ${(result.maxBytes / 1048576).toFixed(1)} MiB`);
    if (result.outcome !== "saved") throw Error("宿主未确认保存成功");
    resourceMeta.etag = result.etag; if (revision === editRevision) changed(false); status("已保存到原文件。");
  } catch (error) { status(`保存失败：${error.message}`, true); }
  finally { saveInProgress = false; changed(dirty); }
}
window.addEventListener("message", event => {
  if (event.source !== window.parent || event.data?.jsonrpc !== "2.0") return;
  const message = event.data;
  if (pending.has(message.id)) {
    const p = pending.get(message.id); pending.delete(message.id); clearTimeout(p.timeout);
    message.error ? p.reject(Error(message.error.message || "宿主请求失败")) : p.resolve(message.result); return;
  }
  if (message.method === "ui/notifications/tool-input") loadFile(message.params?.arguments?.file);
  if (message.method === "ui/notifications/tool-result") loadFile(message.params?.structuredContent?.file);
  if (message.method === "notifications/resources/updated" && message.params?.uri === fileRef?.resourceUri) {
    if (dirty || sourceDirty || saveInProgress) status("检测到文件更新；保留当前编辑，保存时会检查版本。");
    else loadFile(fileRef, true);
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
  if (!doc || doc.count < 2 || !applySource()) return;
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
for (const mode of ["rotate", "pan", "zoom"]) $(mode).onclick = () => views?.setMode(mode);
$("first").onclick = () => { stop(); go(0); };
$("last").onclick = () => { stop(); if (doc) go(doc.count - 1); };
for (const id of ["style", "palette", "radius-scale", "cell", "labels", "hbonds", "wrap"]) $(id).onchange = () => { stop(); status(""); scheduleRender(id==="wrap"); };
$("follow").onchange=()=>{stop();if($("follow").checked)setFollow(Number($("follow-number").value)-1);else {anchor=null;render();}};
$("follow-apply").onclick=()=>{stop();setFollow(Number($("follow-number").value)-1);};
$("follow-selected").onclick=()=>setFollow(selection[selection.length-1]);
$("source-toggle").onclick = () => { stop(); $("source-panel").hidden = !$("source-panel").hidden; if(doc&&!sourceDirty)$("source").value=doc.frameText(frameIndex); };
$("source").oninput = () => { sourceDirty = true; editRevision++; changed(dirty); };
$("apply-source").onclick = applySource;
$("apply-atom").onclick = () => {
  if (!doc || previewOnly || !selection.length || !applySource()) return;
  try { doc.updateAtom(frameIndex, selection[selection.length - 1], ["x", "y", "z"].map(key => $("coord-" + key).value)); editRevision++; changed(); render(); status("坐标已修改；已有能量和力未重算。点击保存写回文件。"); }
  catch (error) { status(error.message, true); }
};
$("save").onclick = save;
$("enable-edit").onclick = () => loadFullFile(fileRef);
document.addEventListener("keydown", e => { if ((e.metaKey || e.ctrlKey) && e.key === "s") { e.preventDefault(); save(); } });
window.addEventListener("beforeunload", e => { if (dirty || sourceDirty) { e.preventDefault(); e.returnValue = ""; } });
request("ui/initialize", { protocolVersion: "2026-01-26", appInfo: { name: "Structure Viewer", version: "0.4.0" }, appCapabilities: {} })
  .then(() => { send("ui/notifications/initialized", {}); status("已连接，等待文件…"); })
  .catch(error => status(`连接失败：${error.message}`, true));

$("open-file").onclick=()=>$("file-picker").click();
$("file-picker").onchange=async()=>{
  const file=$("file-picker").files[0];if(!file)return;
  if((dirty||sourceDirty)&&!confirm("放弃尚未保存的修改并打开文件？"))return;
  const generation=++readGeneration;stop();clearFollow();pickedFile=true;fileRef=null;resourceMeta={};frameIndex=0;selection=[];sourceDirty=false;doc=null;
  binaryTrajectory=/\.traj$/i.test(file.name);editingMode(true);$("enable-edit").hidden=true;$("source-toggle").hidden=binaryTrajectory;$("source-panel").hidden=true;changed(false);status("");$("filename").textContent=file.name;
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
$("snapshot").onclick=()=>{
  if(!views||!doc)return;stop();$("snapshot-name").value=$("filename").textContent.replace(/\.[^.]+$/,'').replace(/[^\p{L}\p{N}_ .()\-]/gu,'_')+'-frame-'+(frameIndex+1);
  snapshotData=null;$("snapshot-save").disabled=true;$("snapshot-preview").hidden=true;
  $("snapshot-dialog").showModal();afterPaint(refreshSnapshot);
};
for(const id of ["snapshot-format","snapshot-dpi","snapshot-transparent","snapshot-crop"])$(id).onchange=()=>{
  snapshotData=null;$("snapshot-save").disabled=true;
  $("snapshot-transparent").disabled=$("snapshot-format").value!=='png';afterPaint(refreshSnapshot);
};
$("snapshot-close").onclick=()=>{$("snapshot-dialog").close();++snapshotTicket;};
$("snapshot-save").onclick=async()=>{
  if(!snapshotData)return;
  const result=snapshotData,format=$("snapshot-format").value,name=$("snapshot-name").value+'.'+format;
  if(!/^[\p{L}\p{N}_ .()\-]{1,100}\.(png|jpeg|pdf)$/u.test(name)||name.startsWith('.')){$("snapshot-result").textContent='请使用字母、数字、中文、空格、下划线或短横线命名';return;}
  $("snapshot-save").disabled=true;
  try {
    if(pickedFile){
      const url=URL.createObjectURL(new Blob([result.bytes],{type:result.mime})),link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),60000);$("snapshot-result").textContent='已请求下载 '+name;
    }else{
      let binary='';for(let i=0;i<result.bytes.length;i+=32768)binary+=String.fromCharCode(...result.bytes.subarray(i,i+32768));
      const saved=await request('tools/call',{name:'save_structure_snapshot',arguments:{name,data:btoa(binary)}});
      if(saved.isError)throw Error(saved.content?.find(c=>c.text)?.text||'保存失败');
      if(!saved.structuredContent?.path)throw Error('宿主未确认保存路径');$("snapshot-result").textContent='已保存：'+saved.structuredContent.path;
    }
  }catch(error){$("snapshot-result").textContent=error.message;}finally{$("snapshot-save").disabled=false;}
};
