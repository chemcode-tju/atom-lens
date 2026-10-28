/* Display rules and ordered measurements; never modify structure coordinates. */
(function(root) {
  'use strict';
  const sub=(a,b)=>['x','y','z'].map(k=>a[k]-b[k]);
  const dot=(a,b)=>a.reduce((n,x,i)=>n+x*b[i],0);
  const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
  const scale=(v,s)=>v.map(x=>x*s);
  function measure(atoms,indices) {
    if(indices.length<2||indices.length>4)return '';
    const [a,b,c,d]=indices.map(i=>atoms[i]);
    if(!a||!b)return '';
    if(indices.length===2)return `距离 1–2：${Math.hypot(...sub(a,b)).toFixed(4)} Å`;
    const u=sub(a,b),v=sub(c,b),length=Math.hypot(...u)*Math.hypot(...v);
    if(length<1e-12)return '角度未定义（原子重合）';
    if(indices.length===3)return `夹角 1–2–3：${(Math.acos(Math.max(-1,Math.min(1,dot(u,v)/length)))*180/Math.PI).toFixed(3)}°`;
    const axis=scale(v,1/Math.hypot(...v)),w=sub(d,c);
    const p=u.map((x,i)=>x-dot(u,axis)*axis[i]),q=w.map((x,i)=>x-dot(w,axis)*axis[i]);
    if(Math.hypot(...p)*Math.hypot(...q)<1e-12)return '二面角未定义（相邻三原子共线）';
    return `二面角 1–2–3–4：${(Math.atan2(dot(cross(axis,p),q),dot(p,q))*180/Math.PI).toFixed(3)}°`;
  }
  function validIds(frame) {
    const ids=frame.atoms.map(a=>a.id);
    return ids.every(id=>id!=null)&&new Set(ids).size===ids.length;
  }
  function compatible(a,b) {return a.atoms.length===b.atoms.length&&a.atoms.every((atom,i)=>atom.elem===b.atoms[i].elem);}
  function remap(a,b,indices) {
    if(validIds(a)&&validIds(b)) {
      const lookup=new Map(b.atoms.map((atom,i)=>[atom.id,i]));
      return indices.map(i=>lookup.get(a.atoms[i]?.id)).filter(i=>i!==undefined);
    }
    return compatible(a,b)?indices.filter(i=>i<b.atoms.length):[];
  }
  class DisplayState {
    constructor(){this.hiddenElements=new Set();this.overrides=new Map();}
    apply(frame,indices,patch){for(const i of indices)this.overrides.set(i,{...this.overrides.get(i),...patch});}
    reset(frame,indices){for(const i of indices)this.overrides.delete(i);}
    transition(a,b){
      const next=new Map();
      for(const [i,rule] of this.overrides){const mapped=remap(a,b,[i]);if(mapped.length)next.set(mapped[0],rule);}
      this.overrides=next;
    }
    resolve(atom,index,defaults){
      const rule=this.overrides.get(index)||{};
      return {...defaults,...rule,visible:!this.hiddenElements.has(atom.elem)&&rule.visible!==false};
    }
  }
  function inRectangle(points,start,end) {
    const minX=Math.min(start.x,end.x),maxX=Math.max(start.x,end.x),minY=Math.min(start.y,end.y),maxY=Math.max(start.y,end.y);
    return points.filter(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)&&p.x>=minX&&p.x<=maxX&&p.y>=minY&&p.y<=maxY).map(p=>p.index);
  }
  function surfaceMarker(center,radius,segments=64) {
    // Three narrow great-circle bands follow the atom's surface in world space.
    // Ordinary opaque mesh depth testing lets foreground atoms occlude them.
    const vertexArr=[],normalArr=[],faceArr=[],r=radius*1.012,halfWidth=.045;
    const addFace=(a,b,c)=>{
      const u=sub(vertexArr[b],vertexArr[a]),v=sub(vertexArr[c],vertexArr[a]);
      const normal=normalArr[a];
      if(dot(cross(u,v),[normal.x,normal.y,normal.z])<0)faceArr.push(a,c,b);else faceArr.push(a,b,c);
    };
    for(let axis=0;axis<3;axis++) {
      const start=vertexArr.length;
      for(let step=0;step<=segments;step++)for(const side of [-1,1]) {
        const theta=step*2*Math.PI/segments,n=[0,0,0];
        n[axis]=Math.sin(side*halfWidth);
        n[(axis+1)%3]=Math.cos(theta)*Math.cos(halfWidth);
        n[(axis+2)%3]=Math.sin(theta)*Math.cos(halfWidth);
        normalArr.push({x:n[0],y:n[1],z:n[2]});
        vertexArr.push({x:center.x+r*n[0],y:center.y+r*n[1],z:center.z+r*n[2]});
      }
      for(let step=0;step<segments;step++) {const i=start+step*2;addFace(i,i+1,i+2);addFace(i+1,i+3,i+2);}
    }
    return {vertexArr,normalArr,faceArr,color:0xffce25,opacity:1};
  }
  const api={measure,remap,DisplayState,inRectangle,surfaceMarker};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.StructureSelection=api;
})(typeof window!=='undefined'?window:globalThis);
