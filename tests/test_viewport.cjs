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
 const handlers={},translations=[],resizes=[],paints=[];
 const queued=[];global.requestAnimationFrame=callback=>{queued.push(callback);return queued.length;};
 const flush=()=>{const batch=queued.splice(0);batch.forEach(fn=>fn());};
 const canvas={clientWidth:400,clientHeight:600};
 const layer={querySelector:()=>({hidden:true,style:{}}),addEventListener:()=>{}};
 const title={};
 const element={hidden:false,querySelector:selector=>selector==='.view-canvas'?canvas:selector==='.pointer-layer'?layer:title,
   addEventListener:(name,fn)=>{(handlers[name]??=[]).push(fn);},setPointerCapture:()=>{}};
 let resizeCallback;
 const fakeViewer={setViewChangeCallback:()=>{},resize:()=>resizes.push([canvas.clientWidth,canvas.clientHeight]),render:()=>paints.push(1),translateScene:(dx,dy)=>translations.push([dx,dy])};
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
 resizeCallback();resizeCallback();resizeCallback();assert.equal(queued.length,1);flush();
 assert.deepEqual(resizes,[[400,600]]);assert.equal(paints.length,0);
 resizeCallback();flush();assert.equal(resizes.length,1);
 canvas.clientWidth=300;resizeCallback();flush();assert.deepEqual(resizes[1],[300,600]);
 element.hidden=true;canvas.clientWidth=0;resizeCallback();flush();assert.equal(resizes.length,2);
 element.hidden=false;canvas.clientWidth=450;resizeCallback();flush();assert.deepEqual(resizes[2],[450,600]);
 console.log('Right drag pans; left drag remains available to rotation; resize does not refit.');
}

// Shift bypasses rotation/zoom, ray-picks the front atom, and toggles a dragged
// rectangle without changing the persistent tool or losing selection order.
{
 const handlers={},rectangle={hidden:true,style:{}},picks=[],boxes=[];
 const element={querySelector:()=>rectangle,setPointerCapture:()=>{},addEventListener:(name,fn)=>{(handlers[name]??=[]).push(fn);}};
 const view=Object.create(StructureViews.prototype);
 let hits=[{clickable:{index:1}}];
 const canvas={getBoundingClientRect:()=>({left:20,top:40,width:400,height:600})};
 const viewer={targetedObjects:(x,y)=>{assert.equal(x,0);assert.equal(y,0);return hits;},modelToScreen:a=>({x:a.x,y:a.y})};
 Object.assign(view,{mode:'rotate',visibleIndices:[0,2],latest:[{atoms:[{x:80,y:80},{x:85,y:85},{x:100,y:100}]}],onAtom:(...args)=>picks.push(args),onBox:(...args)=>boxes.push(args)});
 global.scrollX=global.scrollY=0;
 view.bindShiftSelection({element,canvas,viewer});
 const emit=(name,props={})=>{const e={button:0,shiftKey:true,pointerId:1,clientX:220,clientY:340,target:{closest:()=>null},preventDefault(){this.prevented=true;},stopImmediatePropagation(){this.stopped=true;},...props};for(const handler of handlers[name]||[])handler(e);return e;};
 assert.equal(emit('pointerdown').stopped,true);assert.equal(emit('mousedown').stopped,true);
 emit('pointerup');assert.deepEqual(picks,[[2,true]]);assert.equal(view.mode,'rotate');
 emit('pointerdown');emit('pointermove',{clientX:222,clientY:341});emit('pointerup');assert.equal(picks.length,2);assert.equal(boxes.length,0);
 emit('pointerdown',{clientX:150,clientY:150});emit('pointermove',{clientX:50,clientY:50});assert.equal(rectangle.hidden,false);
 emit('pointerup',{clientX:50,clientY:50,shiftKey:false});assert.deepEqual(boxes,[[[0,2],true]]);assert.equal(rectangle.hidden,true);
 emit('pointerdown');emit('pointercancel');emit('pointerup');assert.equal(picks.length,2);
 hits=[];emit('pointerdown');emit('pointerup');assert.equal(picks.length,2);
 assert.equal(emit('pointerdown',{shiftKey:false}).stopped,undefined);
 assert.equal(emit('pointerdown',{button:2}).stopped,undefined);
 console.log('Shift click/front-atom picking, drag toggle, hidden-atom exclusion, jitter and cancellation passed.');
}
