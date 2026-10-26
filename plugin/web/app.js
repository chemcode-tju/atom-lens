"use strict";
const $ = id => document.getElementById(id);
const pending = new Map();
let nextId = 1, fileRef, resourceMeta = {}, doc, frameIndex = 0, frameData, viewer;
let dirty = false, sourceDirty = false, selection = [], timer = null, loading = false, readGeneration = 0;
let saveInProgress = false, editRevision = 0;
function send(method, params) { window.parent.postMessage({ jsonrpc: "2.0", method, params }, "*"); }
function request(method, params) {
  const id = nextId++;
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => { pending.delete(id); reject(Error(`请求超时：${method}`)); }, 60000);
    pending.set(id, { resolve, reject, timeout });
    window.parent.postMessage({ jsonrpc: "2.0", id, method, params }, "*");
  });
}
function status(text, error = false) { $("status").textContent = text; $("status").classList.toggle("error", error); }
function changed(value = true) {
  dirty = value;
  $("modified").textContent = dirty || sourceDirty ? "● 未保存" : "已保存";
  $("modified").classList.toggle("dirty", dirty || sourceDirty);
  $("save").disabled = !(dirty || sourceDirty) || !resourceMeta.writable || saveInProgress;
}
function stop() { clearInterval(timer); timer = null; $("play").textContent = "▶"; $("play").setAttribute("aria-label", "播放轨迹"); }
function point(coords) { return { x: coords[0], y: coords[1], z: coords[2] }; }
function drawCell(cell) {
  if (!cell || !$("cell").checked) return;
  const vertex = mask => point([0, 1, 2].map(j => cell.reduce((sum, v, k) => sum + ((mask >> k) & 1) * v[j], 0)));
  for (let mask = 0; mask < 8; mask++) for (let k = 0; k < 3; k++) if (!(mask & (1 << k))) {
    viewer.addLine({ start: vertex(mask), end: vertex(mask | (1 << k)), color: ["#bc6e66", "#4cae98", "#729bdd"][k], linewidth: 1.4 });
  }
}
function ensureViewer() {
  if (viewer) return;
  const background = getComputedStyle(document.documentElement).getPropertyValue("--canvas").trim();
  viewer = $3Dmol.createViewer($("viewer"), { backgroundColor: background, antialias: true });
  new ResizeObserver(() => { viewer.resize(); viewer.render(); }).observe($("viewer"));
}
function render(reset = false) {
  if (!doc) return;
  try {
    frameData = doc.frame(frameIndex);
    ensureViewer();
    const previousView = viewer.getView();
    viewer.removeAllModels(); viewer.removeAllShapes(); viewer.removeAllLabels();
    let style = $("style").value;
    if (frameData.atoms.length > 3000 && style !== "sphere") { style = "sphere"; $("style").value = style; status("大结构已切换为原子球显示"); }
    const xyz = `${frameData.atoms.length}\n\n${frameData.atoms.map(a => `${a.elem} ${a.x} ${a.y} ${a.z}`).join("\n")}\n`;
    const model = viewer.addModel(xyz, "xyz", { assignBonds: style !== "sphere" });
    viewer.setStyle({}, style === "sphere" ? { sphere: { scale: 0.34 } } : style === "stick" ? { stick: { radius: 0.16 } } : { sphere: { scale: 0.23 }, stick: { radius: 0.10 } });
    model.setClickable({}, true, atom => chooseAtom(atom.index));
    drawCell(frameData.cell);
    if ($("labels").checked && frameData.atoms.length <= 1000) frameData.atoms.forEach((a, i) => viewer.addLabel(`${a.elem}${i + 1}`, { position: a, fontSize: 10, backgroundOpacity: 0.5, showBackground: true }));
    selection = selection.filter(i => i < frameData.atoms.length);
    selection.forEach(i => viewer.addLabel(`${frameData.atoms[i].elem} #${i + 1}`, { position: frameData.atoms[i], fontSize: 12, backgroundColor: "#087f8c", backgroundOpacity: 0.9 }));
    if (reset) { viewer.zoomTo(); viewer.rotate(-20, "x"); viewer.rotate(20, "y"); } else viewer.setView(previousView);
    viewer.render();
    $("empty").hidden = true;
    $("timeline").max = doc.count - 1; $("timeline").value = frameIndex; $("timeline").disabled = doc.count < 2;
    $("frame-number").max = doc.count; $("frame-number").value = frameIndex + 1;
    $("frame-count").textContent = `/ ${doc.count}`;
    $("summary").textContent = `${frameData.atoms.length} 原子 · ${[...new Set(frameData.atoms.map(a => a.elem))].join(" / ")}`;
    $("badges").replaceChildren();
    const flags = frameData.pbc.map(v => v ? "T" : "F").join(" ");
    for (const text of [`PBC ${flags}`, `${doc.count} 帧`]) { const badge = document.createElement("span"); badge.textContent = text; $("badges").append(badge); }
    if (!sourceDirty) $("source").value = doc.frameText(frameIndex);
    $("source-title").textContent = doc.xyz ? `第 ${frameIndex + 1} 帧源码` : "VASP 文件源码";
    updateSelection();
  } catch (error) { stop(); status(error.message, true); }
}
function updateSelection() {
  $("atom-panel").hidden = selection.length === 0;
  if (!selection.length) return;
  const index = selection[selection.length - 1], atom = frameData.atoms[index];
  $("atom-title").textContent = `${atom.elem} · 原子 ${index + 1}`;
  ["x", "y", "z"].forEach(key => { $("coord-" + key).value = atom[key].toFixed(6); $("coord-" + key).disabled = !doc.xyz; });
  $("apply-atom").disabled = !doc.xyz;
  $("distance").textContent = selection.length === 2 ? `直接距离 ${Math.hypot(...["x", "y", "z"].map(k => frameData.atoms[selection[0]][k] - atom[k])).toFixed(4)} Å` : "";
}
function chooseAtom(index) {
  stop(); selection = selection.includes(index) ? selection.filter(i => i !== index) : [...selection.slice(-1), index]; render();
}
function applySource() {
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
  frameIndex = Math.max(0, Math.min(doc.count - 1, Number(index) || 0)); selection = []; render();
}
async function loadFile(file, reload = false) {
  if (!file?.resourceUri || loading || (!reload && fileRef?.resourceUri === file.resourceUri && doc)) return;
  loading = true; const generation = ++readGeneration; stop();
  fileRef = file; $("filename").textContent = file.name; status("正在读取结构与轨迹索引…");
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
    frameIndex = Math.min(frameIndex, doc.count - 1); selection = []; sourceDirty = false; changed(false); render(true);
    status(`${doc.count} 帧已加载 · ${resourceMeta.writable ? "可以编辑保存" : "宿主只读"} · ${$("style").value === "sphere" ? "原子球显示" : "连线按距离推断"}`);
    request("resources/subscribe", { uri: file.resourceUri }).catch(() => {});
  } catch (error) { status(`打开失败：${error.message}`, true); }
  finally { loading = false; }
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
  $("play").textContent = "Ⅱ"; $("play").setAttribute("aria-label", "暂停轨迹");
  timer = setInterval(() => go((frameIndex + 1) % doc.count), 1000 / Number($("speed").value));
};
$("speed").onchange = () => { if (timer) { stop(); $("play").click(); } };
$("reset").onclick = () => render(true);
for (const id of ["style", "cell", "labels"]) $(id).onchange = () => { render(); if (id === "style") status($(id).value === "sphere" ? "原子球显示" : "连线按距离推断；未绘制跨周期边界的键。"); };
$("source-toggle").onclick = () => { stop(); $("source-panel").hidden = !$("source-panel").hidden; };
$("source").oninput = () => { sourceDirty = true; editRevision++; changed(dirty); };
$("apply-source").onclick = applySource;
$("apply-atom").onclick = () => {
  if (!doc || !selection.length || !applySource()) return;
  try { doc.updateAtom(frameIndex, selection[selection.length - 1], ["x", "y", "z"].map(key => $("coord-" + key).value)); editRevision++; changed(); render(); status("坐标已修改；已有能量和力未重算。点击保存写回文件。"); }
  catch (error) { status(error.message, true); }
};
$("save").onclick = save;
document.addEventListener("keydown", e => { if ((e.metaKey || e.ctrlKey) && e.key === "s") { e.preventDefault(); save(); } });
window.addEventListener("beforeunload", e => { if (dirty || sourceDirty) { e.preventDefault(); e.returnValue = ""; } });
request("ui/initialize", { protocolVersion: "2026-01-26", appInfo: { name: "Structure Viewer", version: "0.1.0" }, appCapabilities: {} })
  .then(() => { send("ui/notifications/initialized", {}); status("已连接，等待文件…"); })
  .catch(error => status(`连接失败：${error.message}`, true));
