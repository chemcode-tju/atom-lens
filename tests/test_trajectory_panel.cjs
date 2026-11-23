'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('plugin/web/app.js','utf8'),elements=new Map();
const element=id=>{
 if(!elements.has(id)){const classes=new Set();elements.set(id,{value:0,clientWidth:0,
  classList:{contains:name=>classes.has(name),toggle(name,on){if(on)classes.add(name);else classes.delete(name);}},
  closest:()=>({style:{setProperty(){}}})});}return elements.get(id);
};
let resizes=0;
const context=vm.createContext({$:element,doc:{count:1},frameIndex:0,streamComplete:true,timelineSeek:null,
 views:{resizeToLayout(){resizes++;}},document:{activeElement:null}});
vm.runInContext(source.slice(source.indexOf('function updateTimeline()'),source.indexOf('function render(')),context);
context.updateTimeline();assert(element('trajectory-tools').classList.contains('single-frame'));assert.equal(resizes,1);
context.doc.count=2;context.updateTimeline();assert(!element('trajectory-tools').classList.contains('single-frame'));assert.equal(resizes,2);
context.doc.count=100;context.updateTimeline();assert.equal(resizes,2,'Index progress does not resize the canvas');
context.doc.count=1;context.streamComplete=false;context.updateTimeline();assert(!element('trajectory-tools').classList.contains('single-frame'),'A growing first frame is not a confirmed static structure');
context.streamComplete=true;context.updateTimeline();assert(element('trajectory-tools').classList.contains('single-frame'));
assert.equal(element('play').disabled,true);assert.equal(element('frame-number').readOnly,true);
console.log('Single-frame transport hides only after indexing completes; multiframe controls and hidden ruler updates remain valid.');
