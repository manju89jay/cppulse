const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const os=require('node:os');
const path=require('node:path');
const {preserveVsix}=require('./preserve-vsix.cjs');

test('local packaging preserves the prior artifact exactly and refuses corrupt history',async()=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'cppulse-vsix-preserve-'));
  try{
    assert.equal(await preserveVsix(root),undefined);
    const original=Buffer.from('owned prior test artifact');
    const source=path.join(root,'artifacts/cppulse-0.2.0-preview.vsix');
    await fs.writeFile(source,original);
    const saved=await preserveVsix(root);
    assert.deepEqual(await fs.readFile(saved.path),original);
    assert.deepEqual(await fs.readFile(source),original);
    assert.deepEqual(await preserveVsix(root),saved);
    await fs.writeFile(saved.path,'corrupt');
    await assert.rejects(()=>preserveVsix(root),/do not match/);
    assert.deepEqual(await fs.readFile(source),original);
  }finally{await fs.rm(root,{recursive:true,force:true});}
});
