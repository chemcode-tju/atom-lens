const assert=require('node:assert/strict');
global.StructureParser=require('../plugin/web/parser.js');
global.StructureTrajectory=require('../plugin/web/trajectory-store.js');
global.StructureLammps=require('../plugin/web/lammps-metadata.js');
global.StructureMD=require('../plugin/web/md-stream.js');
global.StructurePaired=require('../plugin/web/paired.js');
const {open}=require('../plugin/web/import.js');

function trrFrame(step,width,{coords=true,n=1}={}){
  const data=Buffer.alloc(76+2*width+(9+(coords?3*n:0))*width);
  [1993,13,12].forEach((v,i)=>data.writeInt32BE(v,4*i));data.write('GMX_trn_file',12);
  data.writeInt32BE(9*width,32);data.writeInt32BE(coords?3*n*width:0,52);
  data.writeInt32BE(n,64);data.writeInt32BE(step,68);
  const values=[2,0,0,.1,3,0,0,0,4,...Array.from({length:coords?3*n:0},(_,i)=>i+step)];
  values.forEach((v,i)=>data[width===8?'writeDoubleBE':'writeFloatBE'](v,76+(2+i)*width));
  return data;
}

(async()=>{
  const xyz=new File(['1\n i = 28, time = 0\nC 1 2 3\n1\n i = 30, time = 1\nC 4 5 6\n'],'pos.xyz');
  const row=(step,len)=>step+' 0 '+[len,0,0,0,3,0,0,.2,4].join(' ')+' 12\n';
  const cell=s=>new File([s],'sim.cell');
  const r=await open([cell(row(30,5)+row(29,8)+row(28,2)),xyz]);
  await r.store.scan(()=>{});
  assert.deepEqual((await r.store.get(0)).frame.cell,[[2,0,0],[0,3,0],[0,.2,4]]);
  assert.equal((await r.store.get(1)).frame.cell[0][0],5);
  await assert.rejects(open([xyz,cell(row(29,2))]),/No CELL row.*28/);
  await assert.rejects(open([xyz,cell(row(28,2)+row(28,3))]),/Duplicate/);

  global.StructureHostFiles={call:async()=>({atoms:[{number:6,mass:13,type:'0',typeName:'CT',name:'C1',residue:'MOL',resid:2,charge:.25}],pbc:[true,true,false]})};
  const tpr=new File(['metadata tested independently with gmx dump'],'top.tpr');
  const trr=(...parts)=>new File(parts,'sim.trr');
  const b=await open([tpr,trr(trrFrame(5,4),trrFrame(6,8,{coords:false}),trrFrame(7,8))]);
  await b.store.scan(()=>{});
  assert.equal(b.store.count,2);
  const frame=(await b.store.get(1)).frame;
  assert.equal(frame.atoms[0].elem,'C');assert.equal(frame.atoms[0].x,70);
  assert.equal(frame.atoms[0].type,'0');assert.equal(frame.atoms[0].typeName,'CT');assert.equal(frame.atoms[0].mass,13);
  assert.equal(frame.atoms[0].residue,'MOL');assert.equal(frame.atoms[0].charge,.25);
  assert.deepEqual(frame.cell,[[20,0,0],[1,30,0],[0,0,40]]);
  assert.deepEqual(frame.pbc,[true,true,false]);
  await assert.rejects(open([tpr,trr(trrFrame(1,4,{n:2}))]),/atom count mismatch/);
  await assert.rejects(open([tpr,trr(trrFrame(1,4).subarray(0,-3))]),/Truncated/);
  for(const tail of [trrFrame(2,8).subarray(0,30),trrFrame(2,8).subarray(0,-3)]) {
    const growing=trr(trrFrame(1,4),tail);growing.frozen=true;
    const opened=await open([tpr,growing]);await opened.store.scan(()=>{});
    assert.equal(opened.store.count,1);assert.equal(opened.store.complete,true);
    assert.equal((await opened.store.get(0)).frame.atoms[0].x,10);
  }
  console.log('Paired imports: step alignment, missing/duplicate CELL rows, mixed TRR precision, frame skipping, PBC and invalid data passed.');
})().catch(e=>{console.error(e);process.exitCode=1});
