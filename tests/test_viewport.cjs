const assert = require('node:assert/strict');
const {projectToView, viewQuaternions} = require('../plugin/web/viewport.js');
const {radius, palette, vesta} = require('../plugin/web/appearance.js');
function close(actual, expected) { actual.forEach((n,i) => assert.ok(Math.abs(n-expected[i]) < 1e-10)); }
close(projectToView([1,0,0], viewQuaternions.xz), [1,0,0]);
close(projectToView([0,0,1], viewQuaternions.xz), [0,1,0]);
close(projectToView([0,1,0], viewQuaternions.yz), [-1,0,0]);
close(projectToView([0,0,1], viewQuaternions.yz), [0,1,0]);
const frame = [10,10,45];
close(projectToView(frame, viewQuaternions.yz), [-10,45,-10]);
assert.equal(radius('H'), .46);
assert.equal(radius('Cu'), 1.28);
assert.equal(radius('O'), .74);
assert.equal(radius('unknown'), 1.2);
assert.ok(Number.isInteger(vesta.Cu));
assert.deepEqual(palette('rasmol', {Jmol:{H:1,Cu:2,Og:3}, rasmol:{H:4}}), {H:4,Cu:2,Og:3});
console.log('View geometry: XZ/YZ axes and tall-cell projection; OVITO display radii and palette fallback passed.');

// Selection must preserve the existing model/camera; mock only the renderer boundary.
const {StructureViews}=require('../plugin/web/viewport.js');
global.StructureSelection=require('../plugin/web/selection.js');
global.StructureAppearance=require('../plugin/web/appearance.js');
const model={},camera=[1,2,3,4,0,0,0,1],removed=[];
const viewer={getView:()=>camera.slice(),removeShape:s=>removed.push(s.shapePosition),addLine:s=>({...s,shapePosition:9}),render:()=>{},model};
const pane={element:{hidden:false},viewer,markerShapes:[{shapePosition:3}],measureShapes:[{shapePosition:2}]};
const views=Object.create(StructureViews.prototype);
const atoms=[{elem:'H',x:0,y:0,z:0},{elem:'O',x:1,y:0,z:0}];
Object.assign(views,{latest:[{atoms},{scale:1},[]],panes:[pane],visibleIndices:[0,1],rules:[{style:'sphere'},{style:'sphere'}]});
views.updateSelection([0,1]);
assert.deepEqual(removed,[3,2]);assert.equal(pane.markers.length,2);assert.equal(pane.measureShapes.length,1);
assert.equal(viewer.model,model);assert.deepEqual(viewer.getView(),camera);
views.updateSelection([]);assert.equal(pane.markers.length,0);assert.equal(pane.measureShapes.length,0);
console.log('Selection updates preserve the atom model and camera, including clear selection.');

// Exercise actual pointer handlers and ResizeObserver without a GPU.
{
 const handlers={},translations=[];
 const canvas={clientWidth:400,clientHeight:600};
 const layer={querySelector:()=>({hidden:true,style:{}}),addEventListener:()=>{}};
 const title={};
 const element={hidden:false,querySelector:selector=>selector==='.view-canvas'?canvas:selector==='.pointer-layer'?layer:title,
   addEventListener:(name,fn)=>{(handlers[name]??=[]).push(fn);},setPointerCapture:()=>{}};
 let resizeCallback;
 const fakeViewer={setViewChangeCallback:()=>{},resize:()=>{},render:()=>{},translateScene:(dx,dy)=>translations.push([dx,dy])};
 global.document={createElement:tag=>tag==='section'?element:{}};
 global.$3Dmol={createViewer:()=>fakeViewer};
 global.ResizeObserver=class {constructor(callback){resizeCallback=callback;}observe(){}};
 const interaction=Object.create(StructureViews.prototype);
 Object.assign(interaction,{container:{append:()=>{}},panes:[],activate:()=>{},fit:()=>{throw Error('Unexpected refit');}});
 interaction.createPane('xz',0);
 const emit=(name,properties)=>{const event={target:{closest:()=>null},preventDefault(){},stopImmediatePropagation(){this.stopped=true;},...properties};for(const handler of handlers[name]){handler(event);if(event.stopped)break;}};
 emit('pointerdown',{button:0,pointerId:1,clientX:10,clientY:20});
 emit('pointermove',{pointerId:1,clientX:30,clientY:40});assert.deepEqual(translations,[]);
 emit('pointerdown',{button:2,pointerId:2,clientX:10,clientY:20});
 emit('pointermove',{pointerId:2,clientX:30,clientY:15});assert.deepEqual(translations,[[20,-5]]);
 emit('pointerup',{pointerId:2});emit('pointermove',{pointerId:2,clientX:40,clientY:20});assert.equal(translations.length,1);
 resizeCallback();
 console.log('Right drag pans; left drag remains available to rotation; resize does not refit.');
}
