const assert=require('node:assert/strict');
const references=require('./fixtures/xtc-reference.json').fixtures;
global.StructureParser=require('../plugin/web/parser.js');
global.StructureTrajectory=require('../plugin/web/trajectory-store.js');
global.StructureLammps=require('../plugin/web/lammps-metadata.js');
global.StructureMD=require('../plugin/web/md-stream.js');
global.StructureXtcDecoder=require('../plugin/web/vendor/xtc-decoder.js');
global.StructureXtc=require('../plugin/web/xtc.js');
global.StructurePaired=require('../plugin/web/paired.js');
const {open}=require('../plugin/web/import.js');
const bytes=frame=>Buffer.from(frame.data,'base64');
const near=(a,b)=>assert.ok(Math.abs(a-b)<4e-5,`${a} != ${b}`);

(async()=>{
  for(const fixture of references){
    const file=new File(fixture.frames.map(bytes),'test.xtc');
    const source=new StructureXtc.Source(file,Array(fixture.atoms).fill('C'),[true,true,false]);
    await source.advance(1);assert.equal(source.count,1);
    await source.advance();assert.equal(source.count,3);assert.ok(source.complete);
    for(const i of [2,0,1]){
      const frame=new StructureParser.StructureDocument('frame.extxyz',await source.read(i)).frame(0);
      const expected=Buffer.from(fixture.frames[i].positions,'base64');
      frame.atoms.forEach((atom,j)=>['x','y','z'].forEach((axis,k)=>near(atom[axis],expected.readFloatLE((j*3+k)*4)*10)));
      frame.cell.flat().forEach((value,k)=>near(value,fixture.frames[i].box.flat()[k]*10));
      assert.deepEqual(frame.pbc,[true,true,false]);assert.equal(Number(frame.info.step),fixture.frames[i].step);
    }
    await assert.rejects(new StructureXtc.Source(file,['C']).advance(),/count mismatch/);
    const tail=new File([bytes(fixture.frames[0]),bytes(fixture.frames[1]).subarray(0,-3)],'growing.xtc');
    await assert.rejects(new StructureXtc.Source(tail,source.symbols).advance(),/Truncated/);
    tail.frozen=true;
    const frozen=new StructureXtc.Source(tail,source.symbols);await frozen.advance();assert.equal(frozen.count,1);
  }
  const fixture=references[1],original=bytes(fixture.frames[0]);
  for(const [offset,value] of [[0,0],[4,1000001],[52,1],[88,-1]]){
    const bad=Buffer.from(original);bad.writeInt32BE(value,offset);
    await assert.rejects(new StructureXtc.Source(new File([bad],'bad.xtc'),Array(12).fill('C')).advance(),/Invalid|Unsupported/);
  }
  for(const [offset,value] of [[84,100],[56,0]]){
    const bad=Buffer.from(original);bad.writeInt32BE(value,offset);
    const source=new StructureXtc.Source(new File([bad],'bad.xtc'),Array(12).fill('C'));await source.advance();
    await assert.rejects(source.read(0),/Invalid/);
  }
  global.StructureHostFiles={call:async()=>({atoms:Array.from({length:12},()=>({number:6,type:'CT',mass:13,name:'C1',charge:.2,residue:'MOL'})),pbc:[true,true,true]})};
  const paired=await open([new File([original],'test.xtc'),new File(['tpr'],'test.tpr')]);
  assert.equal((await paired.store.get(0)).frame.atoms.length,12);
  const metadataAtom=(await paired.store.get(0)).frame.atoms[0];
  assert.equal(metadataAtom.type,'CT');assert.equal(metadataAtom.mass,13);assert.equal(metadataAtom.name,'C1');assert.equal(metadataAtom.charge,.2);
  const groLines=Array.from({length:12},(_,i)=>`${'1'.padStart(5)}${'MOL'.padEnd(5)}${'C'.padStart(5)}${String(i+1).padStart(5)}   0.000   0.000   0.000`);
  const gro=new File(['test\n12\n'+groLines.join('\n')+'\n2 3 4\n'],'test.gro');
  const fallback=await open([new File([original],'test.xtc'),gro]);
  assert.equal((await fallback.store.get(0)).frame.atoms.length,12);
  global.StructureHostFiles.call=async()=>({atoms:Array.from({length:12},()=>({name:'C',residue:'MOL',mass:12.011}))});
  const withTop=await open([new File([original],'test.xtc'),gro,new File(['topology'],'test.top')]);
  assert.ok((await withTop.store.get(0)).frame.atoms.every(atom=>atom.elem==='C'));
  // GRO's five-digit serial wraps, but row order remains the unique identity.
  const n=100001;
  const large=new File(['large\n'+n+'\n'+Array.from({length:n},(_,i)=>`${'1'.padStart(5)}${'MOL'.padEnd(5)}${'C'.padStart(5)}${String((i+1)%100000).padStart(5)}   0.100   0.200   0.300`).join('\n')+'\n2 3 4\n'],'large.gro');
  const loaded=await open(large);const atoms=(await loaded.store.get(0)).frame.atoms;
  assert.equal(atoms.length,n);assert.equal(atoms[99999].serial,100000);assert.equal(atoms[100000].serial,100001);
  assert.equal(atoms.at(-1).x,1);
  console.log('XTC: independent compressed/uncompressed references, random seeks, units, cell, corruption, frozen tail, pairing and >100k GRO passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
