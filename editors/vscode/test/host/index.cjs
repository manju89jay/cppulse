/** Installed-host acceptance checks; CLI results come from a real retained run. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { spawnSync } = require('node:child_process');
const vscode = require('vscode');

exports.run = async function run() {
  const cases = [];
  const root = process.env.CPPULSE_HOST_WORKSPACE;
  const store = process.env.CPPULSE_HOST_STORE;
  const relative = "unicode/it's 😀.cpp";
  // Register before the initial async installed-backend scenarios. Recreating
  // a watcher immediately before each write races watcher-process startup.
  const sourceWatcher = vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(root, relative));
  const callLog = process.env.CPPULSE_HOST_CALL_LOG;
  const command = (name, args) => vscode.commands.executeCommand(`cppulse.${name}`, args);
  const diagnostics = () => vscode.languages.getDiagnostics().filter(([, rows]) => rows.some(row => row.source?.startsWith('cppulse')));
  const check = async (name, body) => { await body(); cases.push(name); console.log(`PASS ${name}`); };
  const calls = async () => { try { return (await fs.readFile(callLog, 'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse); } catch (error) { if (error.code === 'ENOENT') { return []; } throw error; } };
  const expected = spawnSync(process.env.CPPULSE_HOST_CLI, ['explain', '--store', store], { encoding:'utf8', shell:false, timeout:30000 });
  assert.equal(expected.status, 0, expected.stderr);
  const view = JSON.parse(expected.stdout);
  const extension = vscode.extensions.getExtension('cppulse.cppulse');
  assert.ok(extension, 'The installed package must be discoverable.');
  assert.equal(extension.extensionPath, process.env.CPPULSE_HOST_EXPECTED_EXTENSION);
  const config = vscode.workspace.getConfiguration('cppulse');
  await config.update('executable', process.env.CPPULSE_HOST_NODE, vscode.ConfigurationTarget.Global);
  await config.update('arguments', [process.env.CPPULSE_HOST_PROBE], vscode.ConfigurationTarget.Global);
  await config.update('openReports', false, vscode.ConfigurationTarget.Global);

  await check('installed extension activation executes no configured CLI', async () => {
    await extension.activate();
    assert.deepEqual(await calls(), []);
    assert.equal((await command('showStatus')).diagnosticCount, 0);
  });
  await check('editor reads the exact installed CLI run and exports SARIF with matching pins', async () => {
    const result = await command('readRun', { workspaceRoot:root, store });
    assert.equal(result.runId, view.run.id);
    assert.equal(result.manifestSha256, view.run.manifest_sha256);
    assert.equal(result.storedGate, view.assessment?.display.gate);
    assert.ok(result.diagnosticCount > 0, 'Use a real finding fixture.');
    const exportCall = (await calls()).find(args => args[0] === 'export-sarif');
    assert.equal(exportCall[exportCall.indexOf('--run-id') + 1], view.run.id);
    assert.equal(exportCall[exportCall.indexOf('--manifest-sha256') + 1], view.run.manifest_sha256);
    const paths = diagnostics().map(([uri]) => path.relative(root, uri.fsPath).split(path.sep).join('/'));
    assert.ok(paths.includes('one/same.cpp') && paths.includes('two/same.cpp'), JSON.stringify(paths));
  });
  await check('unsaved source clears diagnostics while preserving historical run pins', async () => {
    const document = await vscode.workspace.openTextDocument(vscode.Uri.file(path.join(root, 'one/same.cpp')));
    const edit = new vscode.WorkspaceEdit(); edit.insert(document.uri, new vscode.Position(0,0), '// unsaved edit\n');
    await vscode.workspace.applyEdit(edit);
    const result = await command('showStatus');
    assert.equal(result.stale, true); assert.equal(result.diagnosticCount, 0);
    assert.equal(result.runId, view.run.id); assert.equal(diagnostics().length, 0);
    await vscode.window.showTextDocument(document);
    await vscode.commands.executeCommand('workbench.action.files.revert');
  });
  const absolute = path.join(root, relative);
  const prefix = '/* é 😀 */ ';
  const text = `${prefix}int value = 1;\n`;
  // Await the actual filesystem notification before beginning the next read.
  // A delayed notification for a previous write can correctly invalidate a
  // newer selection while its asynchronous source digest read is in progress.
  const writeSource = async (text) => {
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => { change.dispose(); reject(new Error('Source-change notification timed out')); }, 15000);
      const change = sourceWatcher.onDidChange(() => { clearTimeout(timer); change.dispose(); resolve(); });
      fs.writeFile(absolute, text).catch(error => { clearTimeout(timer); change.dispose(); reject(error); });
    });
  };
  const sarifPath = path.join(root, 'editor-unicode.sarif');
  await fs.mkdir(path.dirname(absolute), { recursive:true }); await fs.writeFile(absolute, text);
  const uri = relative.split('/').map(encodeURIComponent).join('/');
  const sarif = { version:'2.1.0', runs:[{ columnKind:'unicodeCodePoints', tool:{driver:{name:'cppulse'}},
    artifacts:[{location:{uri},hashes:{'sha-256':createHash('sha256').update(text).digest('hex')}}],
    results:[0,1].map(index => ({ ruleId:'CPP-CX-001', level:'warning', message:{text:`Unicode occurrence ${index}`},
      locations:[{physicalLocation:{artifactLocation:{uri},region:{startLine:1,startColumn:Array.from(prefix).length+1}}}] })) }] };
  await fs.writeFile(sarifPath, JSON.stringify(sarif));
  try {
    await check('imported SARIF preserves duplicates and maps non-BMP columns without invoking CLI', async () => {
      const before = (await calls()).length;
      const result = await command('openSarif', { workspaceRoot:root, request:sarifPath });
      assert.equal(result.diagnosticCount, 2); assert.equal((await calls()).length, before);
      const rows = vscode.languages.getDiagnostics(vscode.Uri.file(absolute));
      assert.equal(rows.length, 2); assert.equal(rows[0].range.start.character, prefix.length);
      await vscode.window.showTextDocument(await vscode.workspace.openTextDocument(vscode.Uri.file(absolute)), { selection:rows[0].range });
      assert.equal(vscode.window.activeTextEditor.document.uri.fsPath, absolute);
      // Subsequent disk fixtures should not race an open document's async reload.
      await vscode.commands.executeCommand('workbench.action.closeActiveEditor');
    });
    for (const [name, separator, targetLine] of [['CR','\r',2],['LF','\n',2],['CRLF','\r\n',2],['LFCR','\n\r',3]]) {
      await check(`${name} source navigation agrees with native line coordinates`, async () => {
        const lineText = `// first${separator}int value = 1;`;
        await writeSource(lineText);
        const lineSarif = structuredClone(sarif);
        lineSarif.runs[0].artifacts[0].hashes['sha-256'] = createHash('sha256').update(lineText).digest('hex');
        lineSarif.runs[0].results = [lineSarif.runs[0].results[0]];
        lineSarif.runs[0].results[0].locations[0].physicalLocation.region = {startLine:targetLine,startColumn:1};
        await fs.writeFile(sarifPath, JSON.stringify(lineSarif));
        const result = await command('openSarif', {workspaceRoot:root,request:sarifPath});
        assert.equal(result.diagnosticCount, 1, JSON.stringify(result));
        const rows = vscode.languages.getDiagnostics(vscode.Uri.file(absolute));
        assert.equal(rows[0].range.start.line, targetLine-1);
        assert.equal(rows[0].range.start.character, 0);
      });
    }
    await fs.writeFile(sarifPath, JSON.stringify(sarif));
    await check('source hash mismatch cannot retain a current diagnostic', async () => {
      await writeSource(`${text}// changed on disk\n`);
      const result = await command('openSarif', { workspaceRoot:root, request:sarifPath });
      assert.equal(result.diagnosticCount, 0);
      assert.ok(result.gaps.some(gap => gap.includes('differ from retained source')));
    });
    await check('clear discards findings and selected pins', async () => {
      await command('clear'); const result = await command('showStatus');
      assert.equal(result.runId, undefined); assert.equal(result.diagnosticCount, 0);
      assert.equal(diagnostics().length, 0);
    });
  } finally {
    sourceWatcher.dispose();
    await fs.rm(sarifPath, { force:true }); await fs.rm(absolute, { force:true });
  }
  if(process.platform!=='win32'){
    await check('the first immediate canonical source write invalidates a newly imported alias-only SARIF',async()=>{
      const isolated=path.join(process.env.CPPULSE_HOST_OUTSIDE_WORKSPACE,'immediate-alias');
      await fs.mkdir(isolated,{recursive:true});
      const target=path.join(isolated,'canonical.cpp'),alias=path.join(isolated,'alias.cpp');
      const source='int alias_value = 1;\n';await fs.writeFile(target,source);await fs.symlink('canonical.cpp',alias);
      const document=structuredClone(sarif);
      document.runs[0].artifacts=[{location:{uri:'alias.cpp'},hashes:{'sha-256':createHash('sha256').update(source).digest('hex')}}];
      document.runs[0].results=[document.runs[0].results[0]];
      document.runs[0].results[0].locations[0].physicalLocation={artifactLocation:{uri:'alias.cpp'},region:{startLine:1,startColumn:1}};
      const request=path.join(isolated,'alias.sarif');await fs.writeFile(request,JSON.stringify(document));
      await command('clear');
      const before=(await calls()).length;
      const selected=await command('openSarif',{workspaceRoot:isolated,request});
      assert.equal(selected.diagnosticCount,1);assert.equal(selected.stale,false);
      // No readiness sleep, extra CLI roundtrip or repeated write is allowed.
      await fs.appendFile(target,'// first immediate actual source change\n');
      const deadline=Date.now()+15000;let state;
      while(Date.now()<deadline){state=await command('showStatus');if(state.stale){break;}await new Promise(resolve=>setTimeout(resolve,25));}
      assert.equal(state.stale,true);assert.equal(state.diagnosticCount,0);
      assert.equal((await calls()).length,before);
      await command('clear');
    });
  }
  if (process.env.CPPULSE_HOST_HEALTH_CASES) {
    let artifactLimitChecked=false;
    for (const scenario of JSON.parse(await fs.readFile(process.env.CPPULSE_HOST_HEALTH_CASES, 'utf8'))) {
      await check(`stored measured health agrees with installed backend: ${scenario.scenario}`, async () => {
        const result = spawnSync(process.env.CPPULSE_HOST_CLI, ['explain','--store',scenario.store,'--run-id',scenario.run_id,
          '--manifest-sha256',scenario.manifest_sha256], {encoding:'utf8',shell:false,timeout:30000});
        assert.equal(result.status,0,result.stderr);
        const selected = JSON.parse(result.stdout);
        const wrapper = selected.facts.find(row => row.kind === 'maintenance_health');
        assert.ok(wrapper,'The actual backend run must contain retained health.');
        const raw = JSON.parse(wrapper.raw_json);
        const state = await command('readRun', {workspaceRoot:scenario.workspace,store:scenario.store,
          runId:scenario.run_id,manifestSha256:scenario.manifest_sha256});
        assert.equal(state.runId,scenario.run_id);
        assert.equal(state.manifestSha256,scenario.manifest_sha256);
        assert.equal(state.measuredHealth.length,1);
        const health = state.measuredHealth[0];
        assert.equal(health.artifactId,wrapper.artifact_id);
        assert.equal(health.sha256,wrapper.sha256);
        assert.equal(health.scorerId,raw.scorer.id);
        assert.equal(health.configurationDigest,raw.scorer.configuration_digest);
        assert.equal(health.availability,raw.aggregate.availability);
        // A token is compared with the original retained JSON lexeme; the host
        // never computes a score or rounds it through Number for display.
        if (health.overall !== null) {
          assert.match(health.overall,/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$/);
          assert.equal(Number(health.overall),raw.aggregate.overall);
          assert.ok(wrapper.raw_json.includes('"overall": '+health.overall) || wrapper.raw_json.includes('"overall":'+health.overall));
        } else { assert.equal(raw.aggregate.overall,null); }
        assert.match(health.bufferVerification,raw.scorer.id.endsWith('v4') ? /does not waive/ : /Legacy v3/);
        const opened = await command('openArtifact',health.artifactId);
        assert.equal(opened.sha256,wrapper.sha256);
        assert.equal(opened.bytes,wrapper.size_bytes);
        await vscode.commands.executeCommand('workbench.action.closeActiveEditor');
      });
      if(!artifactLimitChecked){
        await check('configured source and evidence read limit rejects an actual oversized retained artifact',async()=>{
          await config.update('sourceLimitMiB',1,vscode.ConfigurationTarget.Global);
          try{
            const result=spawnSync(process.env.CPPULSE_HOST_CLI,['explain','--store',scenario.store,'--run-id',scenario.run_id,
              '--manifest-sha256',scenario.manifest_sha256],{encoding:'utf8',shell:false,timeout:30000});
            assert.equal(result.status,0,result.stderr);
            const selected=JSON.parse(result.stdout);
            const large=selected.artifacts.find(artifact=>artifact.size_bytes>1024*1024 && artifact.size_bytes<16*1024*1024);
            assert.ok(large,'Use actual retained bytes larger than the configured 1 MiB artifact read bound.');
            await command('readRun',{workspaceRoot:scenario.workspace,store:scenario.store,runId:scenario.run_id,manifestSha256:scenario.manifest_sha256});
            await assert.rejects(()=>command('openArtifact',large.id),/limit/i);
            artifactLimitChecked=true;
          }finally{await config.update('sourceLimitMiB',16,vscode.ConfigurationTarget.Global);}
        });
      }
    }
  }

  // Failure injection drives actual extension commands/processes. Successful
  // capabilities and restored reads still come from the installed backend.
  const faultPath = path.join(root,'editor-host-fault.cjs');
  const marker = path.join(root,'editor-host-fault-started.json');
  await fs.writeFile(faultPath, `const fs=require('node:fs'),cp=require('node:child_process');
const [mode,marker,...args]=process.argv.slice(2);
if(args[0]==='capabilities'){const r=cp.spawnSync(process.env.CPPULSE_HOST_CLI,args,{stdio:'inherit',shell:false});process.exit(r.status??2);}
if(mode==='hold-export' && args[0]!=='export-sarif'){const r=cp.spawnSync(process.env.CPPULSE_HOST_CLI,args,{stdio:'inherit',shell:false});process.exit(r.status??2);}
if(mode==='malformed'){process.stdout.write('{malformed');}
else if(mode==='oversize'){process.stdout.write('x'.repeat(2*1024*1024));}
else{fs.writeFileSync(marker,JSON.stringify({pid:process.pid,args}));setInterval(()=>{},1000);}`);
  const restore = async () => {
    await config.update('executable',process.env.CPPULSE_HOST_NODE,vscode.ConfigurationTarget.Global);
    await config.update('arguments',[process.env.CPPULSE_HOST_PROBE],vscode.ConfigurationTarget.Global);
    await config.update('timeoutSeconds',300,vscode.ConfigurationTarget.Global);
    await config.update('responseLimitMiB',16,vscode.ConfigurationTarget.Global);
  };
  const fault = async mode => {
    await fs.rm(marker,{force:true});
    await config.update('arguments',[faultPath,mode,marker],vscode.ConfigurationTarget.Global);
  };
  const started = async () => {
    const deadline=Date.now()+10000;
    while(Date.now()<deadline){
      try{return JSON.parse(await fs.readFile(marker,'utf8'));}catch(error){if(error.code!=='ENOENT'){throw error;}}
      await new Promise(resolve=>setTimeout(resolve,25));
    }
    throw new Error('The actual delayed CLI did not start.');
  };
  try {
    await restore();
    await command('readRun',{workspaceRoot:root,store});
    await check('missing executable retains historical pins and clears current diagnostics',async()=>{
      await config.update('executable',path.join(root,'no-such-installed-cppulse'),vscode.ConfigurationTarget.Global);
      await assert.rejects(()=>command('readRun',{workspaceRoot:root,store}),/start|ENOENT/i);
      const state=await command('showStatus');
      assert.equal(state.runId,view.run.id);assert.equal(state.stale,true);assert.equal(state.diagnosticCount,0);
      await restore();
    });
    await check('malformed CLI JSON cannot replace a retained run',async()=>{
      await fault('malformed');
      await assert.rejects(()=>command('readRun',{workspaceRoot:root,store}),/JSON|json/);
      const state=await command('showStatus');
      assert.equal(state.runId,view.run.id);assert.equal(state.stale,true);assert.equal(state.diagnosticCount,0);
      await restore();
    });
    await check('configured response overflow fails explicitly without a truncated clean view',async()=>{
      await fault('oversize');await config.update('responseLimitMiB',1,vscode.ConfigurationTarget.Global);
      await assert.rejects(()=>command('readRun',{workspaceRoot:root,store}),/capture limit/);
      assert.equal((await command('showStatus')).diagnosticCount,0);
      await restore();
    });
    await check('configured wall timeout terminates the real delayed CLI',async()=>{
      await fault('delayed');await config.update('timeoutSeconds',1,vscode.ConfigurationTarget.Global);
      const pending=command('readRun',{workspaceRoot:root,store});
      const observed=await started();
      await assert.rejects(()=>pending,/wall-time/);
      assert.throws(()=>process.kill(observed.pid,0),{code:'ESRCH'});
      assert.equal((await command('showStatus')).stale,true);
      await restore();
    });
    await check('clear cancels an actual CLI process and discards selected pins',async()=>{
      await fault('delayed');
      const pending=command('readRun',{workspaceRoot:root,store});
      const observed=await started();
      await command('clear');await assert.rejects(()=>pending,/cancel/i);
      assert.throws(()=>process.kill(observed.pid,0),{code:'ESRCH'});
      const state=await command('showStatus');
      assert.equal(state.runId,undefined);assert.equal(state.diagnosticCount,0);
      await restore();
    });
    await check('a delayed older action cannot overwrite a newer installed-backend selection',async()=>{
      await fault('delayed');
      const pending=command('readRun',{workspaceRoot:root,store});
      await started();await restore();
      const rejected=assert.rejects(()=>pending,/cancel/i);
      const selected=await command('readRun',{workspaceRoot:root,store});
      await rejected;
      assert.equal(selected.runId,view.run.id);assert.equal(selected.stale,false);
      assert.ok(selected.diagnosticCount>0);
      assert.equal((await command('showStatus')).manifestSha256,view.run.manifest_sha256);
    });
    await check('multi-root selection uses per-folder settings and maps duplicate basenames under the selected root',async()=>{
      const second=process.env.CPPULSE_HOST_SECOND_WORKSPACE;
      assert.ok(second,'The runner must open an actual multi-root workspace.');
      assert.ok(vscode.workspace.workspaceFolders.some(folder=>folder.uri.fsPath===second));
      await fs.mkdir(second,{recursive:true});
      for(const file of view.source.files){
        const target=path.join(second,file.path);
        await fs.mkdir(path.dirname(target),{recursive:true});await fs.copyFile(path.join(root,file.path),target);
      }
      const folder=vscode.workspace.getConfiguration('cppulse',vscode.Uri.file(second));
      await folder.update('executable',process.env.CPPULSE_HOST_NODE,vscode.ConfigurationTarget.WorkspaceFolder);
      await folder.update('arguments',[process.env.CPPULSE_HOST_PROBE],vscode.ConfigurationTarget.WorkspaceFolder);
      await folder.update('storeDirectory',store,vscode.ConfigurationTarget.WorkspaceFolder);
      await config.update('storeDirectory',path.join(root,'missing-global-store'),vscode.ConfigurationTarget.Global);
      try{
        const selected=await command('readRun',{workspaceRoot:second});
        assert.equal(selected.runId,view.run.id);assert.ok(selected.diagnosticCount>0);
        const paths=diagnostics().map(([uri])=>uri.fsPath);
        assert.ok(paths.includes(path.join(second,'one/same.cpp')));
        assert.ok(paths.includes(path.join(second,'two/same.cpp')));
        assert.ok(paths.every(file=>file.startsWith(second+path.sep)),JSON.stringify(paths));
      }finally{await config.update('storeDirectory',undefined,vscode.ConfigurationTarget.Global);}
      // This is an owned disposable fixture, not a source checkout or artifact.
      // Keep it for reproducible host diagnostics rather than deleting inputs.
    });
    const outside=process.env.CPPULSE_HOST_OUTSIDE_WORKSPACE;
    assert.ok(outside,'The runner must provide an unopened source root.');
    for(const file of view.source.files){
      const target=path.join(outside,file.path);
      await fs.mkdir(path.dirname(target),{recursive:true});await fs.copyFile(path.join(root,file.path),target);
    }
    const outsideFile=path.join(outside,'one/same.cpp');
    const originalOutside=await fs.readFile(outsideFile);
    const awaitStale=async()=>{
      const deadline=Date.now()+15000;
      while(Date.now()<deadline){
        const state=await command('showStatus');
        if(state.stale){return state;}
        await new Promise(resolve=>setTimeout(resolve,25));
      }
      assert.fail('A selected source change was not observed by the actual extension.');
    };
    await check('an explicitly selected unopened root observes real on-disk source changes',async()=>{
      assert.equal(vscode.workspace.getWorkspaceFolder(vscode.Uri.file(outside)),undefined);
      const selected=await command('readRun',{workspaceRoot:outside,store});
      assert.ok(selected.diagnosticCount>0);
      try{
        await fs.appendFile(outsideFile,'\n// actual unopened-root source change\n');
        const state=await awaitStale();
        assert.equal(state.runId,view.run.id);assert.equal(state.diagnosticCount,0);
        assert.match(state.message,/changed on disk/);
      }finally{await command('clear');await fs.writeFile(outsideFile,originalOutside);}
    });
    await check('a source change during the first pending selection cannot publish current diagnostics',async()=>{
      await command('clear');await fault('hold-export');
      const pending=command('readRun',{workspaceRoot:outside,store});
      const rejected=assert.rejects(()=>pending,/cancel|changed/i);
      const observed=await started();
      try{
        assert.equal(observed.args[0],'export-sarif');
        await fs.appendFile(outsideFile,'\n// actual source change during pending export\n');
        const state=await awaitStale();await rejected;
        assert.equal(state.runId,view.run.id);assert.equal(state.diagnosticCount,0);
        assert.throws(()=>process.kill(observed.pid,0),{code:'ESRCH'});
      }finally{await command('clear');await restore();await fs.writeFile(outsideFile,originalOutside);}
    });
    if(process.platform!=='win32'){
      await check('a selected symlink-root alias still invalidates canonical source diagnostics',async()=>{
        const alias=outside+'-alias';
        await fs.symlink(outside,alias,'dir');
        try{
          const selected=await command('readRun',{workspaceRoot:alias,store});
          assert.ok(selected.diagnosticCount>0);
          await fs.appendFile(outsideFile,'\n// actual canonical source change through alias selection\n');
          const state=await awaitStale();
          assert.equal(state.runId,view.run.id);assert.equal(state.diagnosticCount,0);
        }finally{await command('clear');await fs.writeFile(outsideFile,originalOutside);await fs.unlink(alias);}
      });
      await check('unsaved edits opened through a selected root alias clear canonical diagnostics',async()=>{
        const alias=outside+'-dirty-alias';
        await fs.symlink(outside,alias,'dir');
        try{
          const selected=await command('readRun',{workspaceRoot:alias,store});
          assert.ok(selected.diagnosticCount>0);
          const document=await vscode.workspace.openTextDocument(vscode.Uri.file(path.join(alias,'one/same.cpp')));
          assert.equal(document.uri.fsPath,path.join(alias,'one/same.cpp'));
          const edit=new vscode.WorkspaceEdit();edit.insert(document.uri,new vscode.Position(0,0),'// actual unsaved alias edit\n');
          await vscode.workspace.applyEdit(edit);
          const state=await awaitStale();
          assert.equal(state.runId,view.run.id);assert.equal(state.diagnosticCount,0);
          assert.match(state.message,/unsaved changes/);
          await vscode.window.showTextDocument(document);
          await vscode.commands.executeCommand('workbench.action.files.revert');
          await vscode.commands.executeCommand('workbench.action.closeActiveEditor');
        }finally{await command('clear');await fs.writeFile(outsideFile,originalOutside);await fs.unlink(alias);}
      });
    }
  } finally {
    await restore();await fs.rm(faultPath,{force:true});await fs.rm(marker,{force:true});
  }
  if (process.env.CPPULSE_HOST_REPORT) {
    await fs.writeFile(process.env.CPPULSE_HOST_REPORT, JSON.stringify({
      hostVersion:vscode.version, platform:process.platform, extension:extension.packageJSON.version,
      runId:view.run.id, manifestSha256:view.run.manifest_sha256, cases, passed:cases.length,
      limitations:['Linux host only; Workspace Trust is enabled by the test harness.',
        'Installed native fixture results are legacy observations, not a verified production assessment.',
        'Cancellation is driven by the registered clear action; the notification Cancel button is not separately qualified.',
        'Does not qualify the full platform, indexed scale, Restricted Mode, or all P2/P8 requirements.']
    }, null, 2));
  }
};
