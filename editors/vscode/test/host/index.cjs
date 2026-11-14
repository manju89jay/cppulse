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
  const relative = "unicode/it's 😀.cpp";
  const absolute = path.join(root, relative);
  const prefix = '/* é 😀 */ ';
  const text = `${prefix}int value = 1;\n`;
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
    });
    await check('source hash mismatch cannot retain a current diagnostic', async () => {
      await fs.writeFile(absolute, `${text}// changed on disk\n`);
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
    await fs.rm(sarifPath, { force:true }); await fs.rm(absolute, { force:true });
  }
  if (process.env.CPPULSE_HOST_REPORT) {
    await fs.writeFile(process.env.CPPULSE_HOST_REPORT, JSON.stringify({
      hostVersion:vscode.version, platform:process.platform, extension:extension.packageJSON.version,
      runId:view.run.id, manifestSha256:view.run.manifest_sha256, cases, passed:cases.length,
      limitations:['Linux host only; Workspace Trust is enabled by the test harness.',
        'Installed native fixture results are legacy observations, not a verified production assessment.',
        'Does not qualify full platform, scale, cancellation UI, or all P2/P8 requirements.']
    }, null, 2));
  }
};
