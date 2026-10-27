/* Display-only periodic geometry. Original document coordinates remain untouched. */
(function(root) {
  'use strict';
  const point = a => [a.x,a.y,a.z];
  const dot = (a,b) => a.reduce((sum,x,i) => sum+x*b[i],0);
  const cross = (a,b) => [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
  const sub = (a,b) => a.map((x,i) => x-b[i]);
  function basis(cell) {
    if (!cell || cell.length !== 3) throw Error('结构没有晶胞，无法进行周期操作');
    const det = dot(cell[0],cross(cell[1],cell[2]));
    if (Math.abs(det)<1e-10) throw Error('晶胞体积为零，无法进行周期操作');
    const reciprocal = [cross(cell[1],cell[2]),cross(cell[2],cell[0]),cross(cell[0],cell[1])].map(v=>v.map(x=>x/det));
    return {fractional:p=>reciprocal.map(v=>dot(p,v)), cartesian:f=>[0,1,2].map(j=>dot(f,cell.map(v=>v[j]))), reciprocal};
  }
  function wrap(frame) {
    const b=basis(frame.cell), periodic=frame.pbc || [true,true,true];
    return {...frame,atoms:frame.atoms.map(atom=>{
      const f=b.fractional(point(atom)).map((x,i)=>periodic[i] ? x-Math.floor(x+1e-10) : x);
      const [x,y,z]=b.cartesian(f);return {...atom,x,y,z};
    })};
  }
  function minimumImage(delta, cell, pbc, cutoff) {
    if (!cell || !pbc?.some(Boolean)) return Math.hypot(...delta)<=cutoff ? delta : null;
    const b=basis(cell), f=b.fractional(delta);
    // Reciprocal-vector bounds include every lattice image within the cutoff,
    // including skewed cells where simply rounding fractional coordinates fails.
    const limits=f.map((x,i)=>pbc[i] ? [Math.ceil(x-cutoff*Math.hypot(...b.reciprocal[i])-1e-9),Math.floor(x+cutoff*Math.hypot(...b.reciprocal[i])+1e-9)] : [0,0]);
    if (limits.reduce((n,[a,z])=>n*Math.max(0,z-a+1),1)>4096) throw Error('晶胞过小或过度倾斜，氢键周期搜索范围过大');
    let best=null, length=cutoff*cutoff+1e-10;
    for(let i=limits[0][0];i<=limits[0][1];i++)for(let j=limits[1][0];j<=limits[1][1];j++)for(let k=limits[2][0];k<=limits[2][1];k++) {
      const v=sub(delta,b.cartesian([i,j,k])), d=dot(v,v);
      if(d<length){best=v;length=d;}
    }
    return best;
  }
  function hydrogenBonds(frame, options={}) {
    const maxDA=options.distance ?? 3.5, minAngle=options.angle ?? 150;
    const heavy=frame.atoms.map((a,i)=>({a,i})).filter(({a})=>['N','O','F'].includes(a.elem));
    const bonds=[];
    for (const [hi,h] of frame.atoms.entries()) {
      if(h.elem!=='H')continue;
      let donor=null, donorVector=null, nearest=1.3;
      for(const item of heavy){const v=minimumImage(sub(point(item.a),point(h)),frame.cell,frame.pbc,1.3);if(v&&Math.hypot(...v)<nearest&&Math.hypot(...v)>.2){donor=item;donorVector=v;nearest=Math.hypot(...v);}}
      if(!donor)continue;
      for(const {a,i} of heavy){
        if(i===donor.i)continue;
        const ha=minimumImage(sub(point(a),point(h)),frame.cell,frame.pbc,2.5);
        if(!ha||Math.hypot(...ha)<.3||Math.hypot(...sub(ha,donorVector))>maxDA)continue;
        const angle=Math.acos(Math.max(-1,Math.min(1,dot(donorVector,ha)/(nearest*Math.hypot(...ha)))))*180/Math.PI;
        if(angle>=minAngle)bonds.push({hydrogen:hi,acceptor:i,start:point(h),end:point(h).map((x,j)=>x+ha[j])});
      }
    }
    return bonds;
  }
  function followAtom(frame, anchor) {
    if(!anchor)return null;
    if(anchor.id!=null&&frame.atoms.filter(a=>a.id===anchor.id).length!==1)throw Error('跟随原子 ID 缺失或重复');
    const index=anchor.id!=null ? frame.atoms.findIndex(a=>a.id===anchor.id) : anchor.index;
    if(index<0||!frame.atoms[index]||frame.atoms[index].elem!==anchor.element||
      (anchor.id==null&&frame.atoms.map(a=>a.elem).join(',')!==anchor.signature)) throw Error('跟随原子在当前帧中无法对应；请重新指定原子');
    return frame.atoms[index];
  }
  const api={basis,wrap,minimumImage,hydrogenBonds,followAtom};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.StructureGeometry=api;
})(typeof window!=='undefined'?window:globalThis);
