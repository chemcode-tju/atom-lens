"use strict";
const viewQuaternions = {xy: [0, 0, 0, 1], xz: [-Math.SQRT1_2, 0, 0, Math.SQRT1_2], yz: [-0.5, 0.5, 0.5, 0.5], perspective: [-Math.SQRT1_2, 0, 0, Math.SQRT1_2]};
function projectToView([a,b,c], [x,y,z,w]) {
  // Match the renderer's model matrix (3Dmol Vector3.applyQuaternion uses its inverse).
  return [(1-2*(y*y+z*z))*a + 2*(x*y-z*w)*b + 2*(x*z+y*w)*c,
    2*(x*y+z*w)*a + (1-2*(x*x+z*z))*b + 2*(y*z-x*w)*c,
    2*(x*z-y*w)*a + 2*(y*z+x*w)*b + (1-2*(x*x+y*y))*c];
}
class StructureViews {
  constructor(container, onAtom) {
    this.container = container;
    this.onAtom = onAtom;
    this.panes = [];
    this.active = 1;
    this.layout = "single";
    this.previousLayout = "quad";
    this.mode = "rotate";
    ["xy", "xz", "yz", "perspective"].forEach((preset, index) => this.createPane(preset, index));
    this.setLayout("single");
  }
  createPane(preset, index) {
    const element = document.createElement("section");
    element.className = "viewport";
    element.innerHTML = '<button class="view-title" type="button"></button><div class="view-canvas"></div><div class="pointer-layer"></div><svg class="axis-gizmo" viewBox="0 0 78 78" aria-label="坐标轴"></svg>';
    this.container.append(element);
    const canvas = element.querySelector(".view-canvas");
    const viewer = $3Dmol.createViewer(canvas, {backgroundColor: "#ffffff", antialias: true, orthographic: true, disableFog: true});
    const pane = {element, canvas, viewer, preset, ready: false};
    this.panes.push(pane);
    element.querySelector(".view-title").textContent = this.title(preset);
    element.querySelector(".view-title").onclick = () => this.activate(index);
    element.querySelector(".view-title").ondblclick = () => { this.activate(index); this.toggleExpand(); };
    element.addEventListener("pointerdown", () => this.activate(index), true);
    element.addEventListener("mousedown", () => this.activate(index), true);
    viewer.setViewChangeCallback(() => this.drawAxes(pane));
    new ResizeObserver(() => { if (!element.hidden) { viewer.resize(); if (pane.ready) this.fit(pane); else viewer.render(); } }).observe(canvas);
    const layer = element.querySelector(".pointer-layer");
    let pointer = null;
    layer.onpointerdown = event => {
      if (event.button !== 0) return;
      pointer = {id: event.pointerId, x: event.clientX, y: event.clientY};
      layer.setPointerCapture(event.pointerId); event.preventDefault();
    };
    layer.onpointermove = event => {
      if (!pointer || pointer.id !== event.pointerId) return;
      const dx = event.clientX - pointer.x, dy = event.clientY - pointer.y;
      if (this.mode === "pan") viewer.translateScene(dx, dy);
      else viewer.zoom(Math.exp(-dy * 0.012));
      pointer.x = event.clientX; pointer.y = event.clientY;
    };
    layer.onpointerup = layer.onpointercancel = () => { pointer = null; };
    layer.addEventListener("wheel", event => { event.preventDefault(); viewer.zoom(Math.exp(-event.deltaY * 0.001)); }, {passive: false});
  }
  title(preset) { return {xy: "Top · XY", xz: "Front · XZ", yz: "Left · YZ", perspective: "Perspective"}[preset]; }
  activate(index) {
    this.active = index;
    this.panes.forEach((pane, i) => pane.element.classList.toggle("active", i === index));
    document.getElementById("orientation").value = this.panes[index].preset;
  }
  setLayout(layout) {
    this.layout = layout;
    this.container.dataset.layout = layout;
    const visible = layout === "single" ? [this.active] : layout === "dual" ? [0, 1] : [0, 1, 2, 3];
    if (!visible.includes(this.active)) this.activate(1);
    this.panes.forEach((pane, index) => { pane.element.hidden = !visible.includes(index); });
    this.activate(this.active);
    document.getElementById("layout").value = layout;
    requestAnimationFrame(() => this.panes.forEach(pane => {
      if (!pane.element.hidden) {
        pane.viewer.resize();
        if (pane.ready) this.fit(pane);
        pane.viewer.render();
      }
    }));
  }
  toggleExpand() {
    if (this.layout === "single") this.setLayout(this.previousLayout);
    else { this.previousLayout = this.layout; this.setLayout("single"); }
  }
  setMode(mode) {
    this.mode = mode;
    this.container.dataset.mode = mode;
    document.querySelectorAll("[data-mode-button]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.modeButton === mode)));
  }
  orient(pane, preset) {
    pane.preset = preset;
    const q = viewQuaternions[preset];
    const view = pane.viewer.getView();
    view.splice(4, 4, ...q);
    pane.viewer.setView(view);
    pane.viewer.setProjection(preset === "perspective" ? "perspective" : "orthographic");
    if (preset === "perspective") { pane.viewer.rotate(18, "x"); pane.viewer.rotate(-25, "y"); }
    pane.element.querySelector(".view-title").textContent = this.title(preset);
    this.fit(pane);
  }
  setOrientation(preset) { this.orient(this.panes[this.active], preset); }
  fit(pane = this.panes[this.active]) {
    if (!pane.ready || pane.element.hidden || !this.bounds) return;
    const {min, max} = this.bounds;
    const center = min.map((n, i) => (n + max[i]) / 2);
    const view = pane.viewer.getView();
    const projected = Array.from({length:8}, (_,mask) => projectToView(min.map((n,i) => ((mask>>i)&1 ? max[i] : n) - center[i]), view.slice(4,8)));
    const halfX = Math.max(...projected.map(v => Math.abs(v[0]))), halfY = Math.max(...projected.map(v => Math.abs(v[1]))), halfZ = Math.max(...projected.map(v => Math.abs(v[2])));
    const aspect = pane.canvas.clientWidth / Math.max(1, pane.canvas.clientHeight);
    const distance = pane.preset === "perspective" ? Math.max(halfY, halfX/aspect)/Math.tan(Math.PI/18) + halfZ : Math.max(halfX, halfY*aspect)/Math.tan(Math.PI/9);
    view.splice(0, 4, ...center.map(n => -n), 150 - Math.max(5, distance)*1.15);
    pane.viewer.setSlab(-Math.hypot(...max.map((n,i) => n-min[i]))*2, Math.hypot(...max.map((n,i) => n-min[i]))*2);
    pane.viewer.setView(view); pane.viewer.render();
  }
  drawAxes(pane) {
    const q = pane.viewer.getView().slice(4, 8), [x, y, z, w] = q;
    const axes = [[1-2*(y*y+z*z), 2*(x*y+z*w)], [2*(x*y-z*w), 1-2*(x*x+z*z)], [2*(x*z+y*w), 2*(y*z-x*w)]];
    pane.element.querySelector(".axis-gizmo").innerHTML = axes.map(([dx, dy], index) => {
      const endX = 31 + 26*dx, endY = 46 - 26*dy, color = ["#db3434", "#259942", "#4964e9"][index];
      return `<line x1="31" y1="46" x2="${endX}" y2="${endY}" stroke="${color}" stroke-width="1.5"/><text x="${endX+3}" y="${endY-3}" fill="${color}">${["x", "y", "z"][index]}</text>`;
    }).join("");
  }
  render(frame, options, selected, reset) {
    const colors = StructureAppearance.palette(options.palette, $3Dmol.elementColors);
    const vertices = options.cell && frame.cell ? Array.from({length:8}, (_,mask) => Object.fromEntries(["x","y","z"].map((axis,j) => [axis, frame.cell.reduce((sum,v,k) => sum + ((mask>>k)&1)*v[j], 0)]))) : [];
    this.bounds = {min:[Infinity,Infinity,Infinity], max:[-Infinity,-Infinity,-Infinity]};
    for (const atom of [...frame.atoms, ...vertices]) {
      const radius = atom.elem ? StructureAppearance.radius(atom.elem)*options.scale : 0;
      ["x","y","z"].forEach((axis,i) => { this.bounds.min[i] = Math.min(this.bounds.min[i], atom[axis]-radius); this.bounds.max[i] = Math.max(this.bounds.max[i], atom[axis]+radius); });
    }
    for (const pane of this.panes) {
      const viewer = pane.viewer, previous = viewer.getView();
      viewer.removeAllModels(); viewer.removeAllShapes(); viewer.removeAllLabels();
      const xyz = `${frame.atoms.length}\n\n${frame.atoms.map(a => `${a.elem} ${a.x} ${a.y} ${a.z}`).join("\n")}\n`;
      const model = viewer.addModel(xyz, "xyz", {assignBonds: options.style !== "sphere"});
      for (const element of new Set(frame.atoms.map(a => a.elem))) {
        const color = colors[element] ?? 0xff1493;
        const radius = StructureAppearance.radius(element) * options.scale;
        const style = options.style === "sphere" ? {sphere: {radius, color}} : options.style === "stick" ? {stick: {radius: 0.16, color}} : {sphere: {radius: radius * 0.45, color}, stick: {radius: 0.10, color}};
        viewer.setStyle({elem: element}, style);
      }
      model.setClickable({}, true, atom => this.onAtom(atom.index));
      if (options.cell && frame.cell) {
        for (let mask=0; mask<8; mask++) for (let k=0; k<3; k++) if (!(mask & (1<<k))) viewer.addLine({start:vertices[mask], end:vertices[mask | (1<<k)], color:"#333333", linewidth:1});
      }
      if (options.labels && frame.atoms.length <= 1000) frame.atoms.forEach((atom, i) => viewer.addLabel(`${atom.elem}${i+1}`, {position:atom, fontSize:11, fontColor:"#222222", showBackground:false}));
      selected.forEach(i => viewer.addLabel(`${frame.atoms[i].elem} #${i+1}`, {position:frame.atoms[i], fontSize:12, backgroundColor:"#2361a9", backgroundOpacity:0.9}));
      pane.ready = true;
      if (reset) this.orient(pane, pane.preset); else viewer.setView(previous);
      if (!pane.element.hidden) viewer.render();
    }
  }
}
if (typeof module !== "undefined" && module.exports) module.exports = {projectToView, viewQuaternions};
