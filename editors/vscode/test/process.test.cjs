const test=require('node:test');
const assert=require('node:assert/strict');
const {mkdtemp,readFile,rm}=require('node:fs/promises');
const {tmpdir}=require('node:os');
const path=require('node:path');
const {runProcess}=require('../dist/process.js');

test('passes spaces/quotes/metacharacters as literal argv without a shell',async()=>{
 const values=['two words',"it's.cpp",'$(touch never-execute)', '`echo no`'];
 const result=await runProcess(process.execPath,['-e','process.stdout.write(JSON.stringify(process.argv.slice(1)))',...values],{cwd:process.cwd()});
 assert.equal(result.exitCode,0);assert.deepEqual(JSON.parse(result.stdout),values);
});

test('preserves successful/failed/incomplete process exits and separate stderr',async()=>{
 for(const exitCode of [0,1,2,3,130]){
  const result=await runProcess(process.execPath,['-e',`process.stdout.write('{"status":"recorded"}');process.stderr.write('producer log');process.exitCode=${exitCode}`],{cwd:process.cwd()});
  assert.equal(result.exitCode,exitCode);assert.equal(result.stderr,'producer log');assert.equal(JSON.parse(result.stdout).status,'recorded');
 }
});

test('reports missing executable and refuses oversize stdout rather than truncate',async()=>{
 await assert.rejects(()=>runProcess('/cppulse-test/missing-binary',[],{cwd:process.cwd()}),/start|ENOENT/i);
 await assert.rejects(()=>runProcess(process.execPath,['-e',"process.stdout.write('x'.repeat(4096))"],{cwd:process.cwd(),maxBytes:1024}),/limit/i);
});

test('cancellation and wall timeout terminate a live process without accepting old output',async()=>{
 const controller=new AbortController();const pending=runProcess(process.execPath,['-e',"process.stdout.write('partial');setInterval(()=>{},1000)"],{cwd:process.cwd(),signal:controller.signal});
 setTimeout(()=>controller.abort(),80);await assert.rejects(()=>pending,/cancel/i);
 await assert.rejects(()=>runProcess(process.execPath,['-e','setInterval(()=>{},1000)'],{cwd:process.cwd(),timeoutMs:80}),/time/i);
});

test('POSIX cancellation also stops a detached command child', {skip:process.platform==='win32'},async()=>{
 const directory=await mkdtemp(path.join(tmpdir(),'cppulse-editor-cancel-'));const marker=path.join(directory,'orphan.txt');
 try{
  const controller=new AbortController();const childCode=`process.on('SIGINT',()=>{});setTimeout(()=>require('node:fs').writeFileSync(${JSON.stringify(marker)},'orphan'),700)`;
  const code=`require('node:child_process').spawn(process.execPath,['-e',${JSON.stringify(childCode)}],{stdio:'ignore'});setInterval(()=>{},1000)`;
  const pending=runProcess(process.execPath,['-e',code],{cwd:process.cwd(),signal:controller.signal});setTimeout(()=>controller.abort(),120);await assert.rejects(()=>pending,/cancel/i);
  await new Promise(resolve=>setTimeout(resolve,800));await assert.rejects(()=>readFile(marker),{code:'ENOENT'});
 }finally{await rm(directory,{recursive:true,force:true});}
});
