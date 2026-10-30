const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
global.StructureParser=require('../plugin/web/parser.js');
global.StructureSelection=require('../plugin/web/selection.js');
global.StructureGeometry=require('../plugin/web/geometry.js');
const Scene=require('../plugin/web/scene.js');
const {FrameStore}=require('../plugin/web/trajectory-store.js');
const text=i=>`1\nProperties=species:S:1:pos:R:3:id:I:1\nH ${i} 0 0 1\n`;
async function main(){
  let inFlight=0,maxFlight=0;
  const store=new FrameStore('test.xyz',{count:10,complete:true,async read(i){maxFlight=Math.max(maxFlight,++inFlight);await new Promise(r=>setTimeout(r,3));inFlight--;return text(i);}}, {maxFrames:2});
  const initial=await store.get(7),display=new StructureSelection.DisplayState();display.apply(initial.frame,[0],{style:'stick'});
  const painted=[];
  const context=vm.createContext({doc:store,frameData:initial.frame,activeRecord:initial,frameIndex:7,
    navigationTarget:null,navigationTask:null,readGeneration:1,selection:[0],displayState:display,drift:null,
    StructureSelection,status:()=>{},stop:()=>{},render:()=>painted.push(context.frameIndex)});
  const app=fs.readFileSync('plugin/web/app.js','utf8');
  vm.runInContext(app.slice(app.indexOf('async function go('),app.indexOf('function discardDocument(')),context);
  await Promise.all([context.go(2),context.go(4),context.go(9)]);
  assert.deepEqual(painted,[9]);assert.equal(maxFlight,1);assert.equal(context.frameData.atoms[0].x,9);
  const stale=context.go(3);context.readGeneration++;context.doc={};await stale;
  assert.deepEqual(painted,[9]);
  const elements=new Map(),values={'animation-start':'1','animation-end':'5','animation-stride':'1','animation-rate':'30','animation-speed':'1','animation-format':'mp4','animation-name':'test'};
  const element=id=>{if(!elements.has(id))elements.set(id,{value:values[id]||'',addEventListener(){}});return elements.get(id);};
  const settings=Scene.settings(initial.frame,{display,scale:1,style:'sphere',wrap:false});
  const frames=[],camera=[1,2,3,4],savedSelection=[0];
  const animation=vm.createContext({console,setTimeout,$:element,doc:store,readGeneration:1,frameIndex:7,selection:savedSelection,displayState:display,
    sceneSettings:()=>settings,StructureScene:Scene,
    views:{captureScene:()=>({width:600,height:400,view:camera.slice()})},
    StructureSnapshot:{async capture(_views,_options,capture){frames.push(capture.scene.frame.atoms[0].x);assert.equal(capture.scene.options.display.resolve(capture.scene.frame.atoms[0],0,{}).style,'stick');assert.deepEqual(capture.view,[1,2,3,4]);return {bytes:new Uint8Array([0])};}},
    render(){throw Error('Export changed the interactive preview');}});
  vm.runInContext(fs.readFileSync('plugin/web/animation.js','utf8'),animation);
  animation.mediaCall=async args=>args.action==='begin'?{id:'test'}:{state:'ready'};
  animation.uploadMedia=async()=>{camera[0]=100;display.reset(initial.frame,[0]);};
  animation.saveMedia=async()=>{};
  vm.runInContext('animationHost={};',animation);
  await element('animation-save').onclick();
  assert.deepEqual(frames,[0,1,2,3,4]);assert.equal(store.cache.size,2);
  assert.equal(animation.frameIndex,7);assert.equal(animation.selection,savedSelection);
  console.log('Async navigation: latest target wins, one read in flight, stale file results ignored. Animation: evicted frames load on demand; camera/style frozen; interactive state unchanged.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
