'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

class Element {
  constructor(){this.value='';this.children=[];this.checked=false;this.disabled=false;this.textContent='';this.style={setProperty(){}};this.dataset={};this.attributes={};this.contentWindow={postMessage(){}};this.isConnected=false;}
  append(...items){this.children.push(...items);}
  before(item){item.isConnected=true;}
  replaceChildren(...items){this.children=items;if(items[0]?.value)this.value=items[0].value;}
  querySelector(){return null;}
  setAttribute(name,value){this.attributes[name]=value;}
  addEventListener(){}
  remove(){this.isConnected=false;}
  showModal(){}
  close(){}
  focus(){}
}
const elements=new Map();
const element=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
const initialProfiles=[
  {id:'first',host:'nd3',name:'实验室',config:'/tmp/ssh-config',python:'/env/a/python3',codex:true},
  {id:'second',host:'nd2',name:'备用服务器',config:'/tmp/ssh-config',python:'/env/b/python3',codex:false}
];
let profiles=structuredClone(initialProfiles),failConnection=false;
const calls=[],listeners={};
const notifications=[];
const localState={host:'本地 Mac',remote:false,session:'local',profile:null};
let connections=[localState],current=localState;
const state=()=>({...current,connections});
const context=vm.createContext({
  document:{getElementById:element,createElement:()=>new Element(),createElementNS:()=>new Element(),body:new Element(),addEventListener(){}},
  window:{addEventListener(name,handler){listeners[name]=handler;}},
  location:{href:'http://127.0.0.1:1234/private/',origin:'http://127.0.0.1:1234'},URL,
  Option:function(text,value){this.text=text;this.value=value;this.setAttribute=()=>{};},
  StructureI18n:{language:'zh-CN',setLanguage(language){this.language=language;},translate(text,language){return language==='en'&&text==='当前查看'?'Viewing':text;}},
  fetch:async(url,options)=>{
    const route=url.pathname.split('/').at(-1),body=JSON.parse(options.body);calls.push({route,body});
    let result,ok=true;
    if(route==='state'||route==='startup')result=state();
    else if(route==='local-codex')result={installed:null};
    else if(route==='hosts')result={hosts:['nd2','nd3','new-host'],config:'/tmp/ssh-config'};
    else if(route==='profiles'){
      if(body.action==='save'){
        const saved={...body.profile,id:body.profile.id||'new-profile'};
        profiles=profiles.some(p=>p.id===saved.id)?profiles.map(p=>p.id===saved.id?saved:p):[...profiles,saved];
        result={saved,profiles};
      }else result={profiles};
    }else if(route==='connect'){
      if(failConnection){ok=false;result={error:'SSH unavailable'};}
      else{const profile=body.profile;current=profile?(connections.find(item=>item.host===profile.host)||{host:profile.host,remote:true,session:profile.host,profile}):localState;if(!connections.includes(current))connections.push(current);result=state();}
    }else if(route==='activate'){current=connections.find(item=>item.session===body.session);result=state();}
    else if(route==='disconnect'){connections=connections.filter(item=>item.session!==body.session);if(current.session===body.session)current=localState;result=state();}
    else if(route==='rpc'&&body.params?.name==='open_structure_path'){
      const filename=body.params.arguments.path;
      result={content:[],structuredContent:{file:{name:path.basename(filename),path:filename,resourceUri:filename}}};
    }
    else if(route==='rpc')result={content:[],structuredContent:{}};
    else throw Error('Unexpected API call: '+route);
    return {ok,json:async()=>structuredClone(result)};
  }
});
const source=fs.readFileSync(path.join(__dirname,'../native/desktop.html'),'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
vm.runInContext(source,context);
const run=code=>vm.runInContext(code,context);
const settle=()=>new Promise(resolve=>setImmediate(resolve));

(async()=>{
  await settle();element('ssh-config').value='/tmp/ssh-config';
  await run('loadServers()');
  assert.equal(element('server-list').value,'','Opening the list must not preselect a host');
  assert.equal(calls.filter(c=>c.route==='connect'||c.route==='bootstrap').length,0);
  element('server-list').value='saved:first';element('server-list').onchange();await settle();
  assert.equal(element('ssh-python').value,'/env/a/python3');assert.equal(element('remote-codex').checked,true);
  await run("serverAction('connect')");
  assert.match(element('connection-status').textContent,/nd3/);
  assert.equal(element('server-status').textContent,'','Do not retain a connecting status after success');
  const connectionCalls=calls.filter(c=>c.route==='connect').length;
  element('server-list').value='saved:second';element('server-list').onchange();await settle();
  assert.equal(element('ssh-python').value,'/env/b/python3');assert.equal(element('remote-codex').checked,false);
  assert.equal(calls.filter(c=>c.route==='connect').length,connectionCalls,'Selecting must not reconnect');
  assert.match(element('connection-status').textContent,/nd3/,'Selection must not change the current connection label');
  failConnection=true;await run("serverAction('connect')");
  assert.match(element('connection-status').textContent,/nd3/,'Failed connections keep the previous session');
  assert.match(element('server-status').textContent,/SSH unavailable/);
  failConnection=false;await run("serverAction('connect')");
  assert.match(element('connection-status').textContent,/nd2/);
  const remoteView=run('activeViewer()');
  remoteView.frame.contentWindow.postMessage=value=>notifications.push(value);
  const message=(method,params={},id)=>listeners.message({source:remoteView.frame.contentWindow,origin:context.location.origin,data:{jsonrpc:'2.0',method,params,id}});
  await message('ui/initialize',{},10);
  assert.equal(notifications.at(-1).result.hostContext.atomLensLanguage,'zh-CN');
  await message('ui/notifications/initialized');
  await message('atomlens/language',{language:'en'});
  assert.equal(notifications.at(-1).method,'atomlens/language');
  assert.equal(context.StructureI18n.language,'en');
  await context.window.atomLensOpenPaths([]);
  assert.equal(run('state.host'),'nd2','Cancelled native picker must leave the server active');
  await context.window.atomLensOpenPaths(['/tmp/water.xyz']);
  assert.equal(run('currentConnection().host'),'本地 Mac');
  assert.equal(run('viewers.size'),3,'Local plus both remote views stay alive');
  await run("activate('nd2')");
  assert.equal(run('activeViewer()'),remoteView,'Returning to a server preserves its iframe and frame/camera state');
  await run("activate('local')");
  await message('atomlens/language',{language:'zh-CN'});
  assert.equal(context.StructureI18n.language,'en','An inactive viewer cannot change the desktop language');
  await listeners.message({source:remoteView.frame.contentWindow,origin:context.location.origin,data:{jsonrpc:'2.0',id:99,method:'ping'}});
  assert.equal(calls.at(-1).body.session,'nd2','An inactive iframe must still route to its own worker');
  await run("activate('nd2')");
  await element('disconnect').onclick();
  assert.equal(run("[...viewers.values()].some(viewer=>viewer.session==='nd2')"),false);
  assert.equal(run('state.host'),'本地 Mac');
  await run("activate('nd3')");
  run('newProfile()');assert.equal(element('ssh-host').value,'');assert.equal(element('ssh-python').value,'python3');
  element('server-name').value='第三台';element('ssh-host').value='user@third';await element('server-save').onclick();
  assert.equal(profiles.length,3);assert.match(element('connection-status').textContent,/nd3/);
  await run("openPaths(['/run/remote.xyz'],'nd3')");
  const remote=run('activeViewer()');
  await context.window.atomLensOpenPaths(['/tmp/before.xyz','/tmp/after.xyz']);
  await element('separate-open').onclick();
  const after=run('activeViewer()');
  assert.equal(after.label,'after.xyz');
  assert.equal(run('[...viewers.values()].filter(viewer=>viewer.label).length'),4);
  element('compare-tab').value=remote.id;
  element('split-side').onclick();
  assert.deepEqual(Array.from(run('shown')),[after.id,remote.id]);
  assert.equal(remote.visible,true);
  assert.equal(calls.filter(call=>call.route==='rpc'&&call.body.params?.arguments?.path==='/run/remote.xyz').at(-1).body.session,'nd3');
  element('split-swap').onclick();
  assert.deepEqual(Array.from(run('shown')),[remote.id,after.id]);
  run('closeViewer(activeViewer())');
  assert.equal(run('activeViewer()'),remote);
  assert.deepEqual(Array.from(run('shown')),[remote.id]);
  console.log('Desktop: independent server connections, grouped file selection, separate tabs, cross-host comparison and closing a pane passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
