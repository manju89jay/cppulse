/** Exercise the packaged VSIX in an isolated, real VS Code extension host. */
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { spawnSync } = require('node:child_process');
const { createHash } = require('node:crypto');
const { isDeepStrictEqual } = require('node:util');
const { readZip } = require('@vscode/vsce/out/zip');
const { downloadAndUnzipVSCode, resolveCliArgsFromVSCodeExecutablePath, runTests } = require('@vscode/test-electron');

async function main() {
  const root = path.resolve(__dirname, '..');
  const manifest = require('../package.json');
  for (const key of ['CPPULSE_HOST_CLI', 'CPPULSE_HOST_WORKSPACE', 'CPPULSE_HOST_STORE']) {
    if (!process.env[key] || !path.isAbsolute(process.env[key])) {
      throw new Error(`${key} must name an absolute installed CLI, disposable fixture workspace, or retained store. See README.md.`);
    }
    await fs.access(process.env[key]);
  }
  // Never leave a previous success receipt behind when this attempt fails.
  if (process.env.CPPULSE_HOST_REPORT) { await fs.rm(path.resolve(process.env.CPPULSE_HOST_REPORT), { force: true }); }
  const executable = process.env.CPPULSE_VSCODE_EXECUTABLE || await downloadAndUnzipVSCode({ version: manifest.engines.vscode });
  if (process.env.CPPULSE_HOST_VSIX && !path.isAbsolute(process.env.CPPULSE_HOST_VSIX)) {
    throw new Error('CPPULSE_HOST_VSIX must name an absolute retained archive path.');
  }
  const vsix = process.env.CPPULSE_HOST_VSIX || path.join(root, 'artifacts/cppulse-0.2.0-preview.vsix');
  const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
  const vsixSha256 = sha256(await fs.readFile(vsix));
  // readZip belongs to the exact locked vsce version used to package this test
  // artifact. Compare installed code with the archive, not checkout dist.
  const packagedCode = await readZip(vsix, name => /^extension\/(?:dist\/[^/]+|package\.json)$/.test(name));
  if (!packagedCode.has('extension/dist/extension.js')) { throw new Error('VSIX lacks the extension entry point.'); }
  const installedCode = [];
  const work = await fs.mkdtemp(path.join(os.tmpdir(), 'cppulse-vsix-host-'));
  try {
    const extensions = path.join(work, 'extensions');
    const profile = path.join(work, 'profile');
    const [cli, ...prefix] = resolveCliArgsFromVSCodeExecutablePath(executable, { reuseMachineInstall: true });
    const install = spawnSync(cli, [...prefix, '--no-sandbox', '--user-data-dir', profile,
      '--extensions-dir', extensions, '--install-extension', vsix, '--force'],
    { encoding: 'utf8', timeout: 120000, shell: false, env: { ...process.env, NODE_PATH: '', PYTHONPATH: '' } });
    process.stdout.write(install.stdout || ''); process.stderr.write(install.stderr || '');
    if (install.error || install.status !== 0) { throw install.error || new Error(`VSIX installation exited ${install.status}`); }
    const installed = (await fs.readdir(extensions)).find(name => name === `${manifest.publisher}.${manifest.name}-${manifest.version}`);
    if (!installed) { throw new Error('Packaged extension was not installed in the isolated extension directory.'); }
    for (const [entry, bytes] of packagedCode) {
      const relative = entry.slice('extension/'.length);
      const target = path.join(extensions, installed, relative);
      if (!(await fs.lstat(target)).isFile()) { throw new Error(`Installed VSIX entry is not a regular file: ${relative}`); }
      const actual = await fs.readFile(target);
      let comparison='exact bytes';
      if (relative === 'package.json') {
        const original=JSON.parse(bytes.toString('utf8')),installedManifest=JSON.parse(actual.toString('utf8'));
        // VS Code adds installation bookkeeping to this manifest. No other
        // packaged field, including main/version/capabilities, may differ.
        if (!Object.prototype.hasOwnProperty.call(original,'__metadata')) { delete installedManifest.__metadata; }
        if (!isDeepStrictEqual(original,installedManifest)) { throw new Error('Installed VSIX manifest fields differ from the selected archive.'); }
        comparison='all manifest fields equal, excluding installer-added __metadata';
      } else if (!actual.equals(bytes)) { throw new Error(`Installed VSIX bytes differ from the selected archive: ${relative}`); }
      installedCode.push({path:relative,sha256:sha256(actual),size_bytes:actual.length,archiveSha256:sha256(bytes),comparison});
    }
    // A forwarding probe records calls while retaining the real installed CLI.
    const probe = path.join(work, 'cli-probe.cjs');
    const callLog = path.join(work, 'cli-calls.jsonl');
    // Starting with two folders avoids VS Code restarting the extension host
    // when a folder workspace is converted into a multi-root workspace.
    const secondWorkspace = path.join(work, 'second-source');
    const outsideWorkspace = path.join(work, 'outside-source');
    const workspaceFile = path.join(work, 'fixture.code-workspace');
    await fs.mkdir(secondWorkspace);
    await fs.mkdir(outsideWorkspace);
    await fs.writeFile(workspaceFile,JSON.stringify({folders:[{path:process.env.CPPULSE_HOST_WORKSPACE},{path:secondWorkspace}]}));
    await fs.writeFile(probe, `const fs=require('node:fs');const cp=require('node:child_process');
fs.appendFileSync(process.env.CPPULSE_HOST_CALL_LOG,JSON.stringify(process.argv.slice(2))+'\\n');
const result=cp.spawnSync(process.env.CPPULSE_HOST_CLI,process.argv.slice(2),{stdio:'inherit',shell:false});
if(result.error){console.error(result.error);process.exitCode=2;}else{process.exitCode=result.status??2;}`);
    await runTests({
      vscodeExecutablePath: executable,
      extensionDevelopmentPath: path.join(extensions, installed),
      extensionTestsPath: path.join(__dirname, 'host/index.cjs'),
      reuseMachineInstall: true,
      launchArgs: [workspaceFile, '--user-data-dir', profile, '--extensions-dir', extensions,
        '--disable-gpu', '--disable-telemetry', '--skip-welcome', '--skip-release-notes',
        ...(process.env.CPPULSE_HOST_VERBOSE === '1' ? ['--verbose', '--log', 'trace'] : [])],
      // Global Node module paths can shadow Electron's original-fs loader.
      extensionTestsEnv: { NODE_PATH: '', PYTHONPATH: '', CPPULSE_HOST_NODE: process.execPath, CPPULSE_HOST_PROBE: probe, CPPULSE_HOST_CALL_LOG: callLog,
        CPPULSE_HOST_EXPECTED_EXTENSION: path.join(extensions, installed), CPPULSE_HOST_SECOND_WORKSPACE:secondWorkspace,
        CPPULSE_HOST_OUTSIDE_WORKSPACE:outsideWorkspace }
    });
    if (sha256(await fs.readFile(vsix)) !== vsixSha256) {
      if (process.env.CPPULSE_HOST_REPORT) { await fs.rm(path.resolve(process.env.CPPULSE_HOST_REPORT),{force:true}); }
      throw new Error('VSIX changed during the installed-host check.');
    }
  } finally {
    if (process.env.CPPULSE_HOST_ARTIFACTS) {
      const evidence = path.resolve(process.env.CPPULSE_HOST_ARTIFACTS);
      await fs.mkdir(evidence, { recursive: true });
      for (const name of ['profile/logs', 'cli-calls.jsonl', 'second-source', 'outside-source', 'fixture.code-workspace']) {
        const source = path.join(work, name);
        try { await fs.cp(source, path.join(evidence, name), { recursive: true, verbatimSymlinks:true }); }
        catch (error) { if (error.code !== 'ENOENT') { throw error; } }
      }
      await fs.writeFile(path.join(evidence, 'host-inputs.json'), JSON.stringify({
        executable, vscodeVersion: manifest.engines.vscode, vsix, vsixSha256, installedCode,
        cli: process.env.CPPULSE_HOST_CLI, workspace: process.env.CPPULSE_HOST_WORKSPACE, store: process.env.CPPULSE_HOST_STORE,
        importOverrides: { NODE_PATH:'', PYTHONPATH:'' }
      }, null, 2));
    }
    await fs.rm(work, { recursive: true, force: true });
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
