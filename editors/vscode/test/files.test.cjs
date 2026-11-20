const test=require('node:test');
const assert=require('node:assert/strict');
const {mkdtemp,mkdir,writeFile,symlink,rm}=require('node:fs/promises');
const {tmpdir}=require('node:os');
const path=require('node:path');
const {readWithin,decodeText}=require('../dist/files.js');

test('bounded root mapping preserves names and rejects traversal, links and oversized input',async()=>{
 const root=await mkdtemp(path.join(tmpdir(),"cppulse editor's files "));
 try{
  await mkdir(path.join(root,'one'));await mkdir(path.join(root,'two'));
  await writeFile(path.join(root,'one','same.cpp'),'é😀 one');await writeFile(path.join(root,'two','same.cpp'),'two');
  assert.equal(decodeText((await readWithin(root,'one/same.cpp')).bytes),'é😀 one');
  assert.equal(decodeText((await readWithin(root,'two/same.cpp')).bytes),'two');
  await assert.rejects(()=>readWithin(root,'../a'),/Unsafe/);
  await assert.rejects(()=>readWithin(root,'one/same.cpp',2),/limit|finite/);
  if(process.platform!=='win32'){await symlink('/etc/passwd',path.join(root,'escape'));await assert.rejects(()=>readWithin(root,'escape'),/escapes/);}
 }finally{await rm(root,{recursive:true,force:true});}
});
