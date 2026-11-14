/** Exercise the packaged VSIX in an isolated, real VS Code extension host. */
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { spawnSync } = require('node:child_process');
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
  const executable = process.env.CPPULSE_VSCODE_EXECUTABLE || await downloadAndUnzipVSCode({ version: manifest.engines.vscode });
  const work = await fs.mkdtemp(path.join(os.tmpdir(), 'cppulse-vsix-host-'));
  try {
    const extensions = path.join(work, 'extensions');
    const profile = path.join(work, 'profile');
    const [cli, ...prefix] = resolveCliArgsFromVSCodeExecutablePath(executable, { reuseMachineInstall: true });
    const install = spawnSync(cli, [...prefix, '--no-sandbox', '--user-data-dir', profile,
      '--extensions-dir', extensions, '--install-extension', path.join(root, 'artifacts/cppulse-0.2.0-preview.vsix'), '--force'],
    { encoding: 'utf8', timeout: 120000, shell: false });
    process.stdout.write(install.stdout || ''); process.stderr.write(install.stderr || '');
    if (install.error || install.status !== 0) { throw install.error || new Error(`VSIX installation exited ${install.status}`); }
    const installed = (await fs.readdir(extensions)).find(name => name === `${manifest.publisher}.${manifest.name}-${manifest.version}`);
    if (!installed) { throw new Error('Packaged extension was not installed in the isolated extension directory.'); }
    // A forwarding probe records calls while retaining the real installed CLI.
    const probe = path.join(work, 'cli-probe.cjs');
    const callLog = path.join(work, 'cli-calls.jsonl');
    await fs.writeFile(probe, `const fs=require('node:fs');const cp=require('node:child_process');
fs.appendFileSync(process.env.CPPULSE_HOST_CALL_LOG,JSON.stringify(process.argv.slice(2))+'\\n');
const result=cp.spawnSync(process.env.CPPULSE_HOST_CLI,process.argv.slice(2),{stdio:'inherit',shell:false});
if(result.error){console.error(result.error);process.exitCode=2;}else{process.exitCode=result.status??2;}`);
    await runTests({
      vscodeExecutablePath: executable,
      extensionDevelopmentPath: path.join(extensions, installed),
      extensionTestsPath: path.join(__dirname, 'host/index.cjs'),
      reuseMachineInstall: true,
      launchArgs: [process.env.CPPULSE_HOST_WORKSPACE, '--user-data-dir', profile, '--extensions-dir', extensions,
        '--disable-gpu', '--disable-telemetry', '--skip-welcome', '--skip-release-notes',
        ...(process.env.CPPULSE_HOST_VERBOSE === '1' ? ['--verbose', '--log', 'trace'] : [])],
      extensionTestsEnv: { CPPULSE_HOST_NODE: process.execPath, CPPULSE_HOST_PROBE: probe, CPPULSE_HOST_CALL_LOG: callLog,
        CPPULSE_HOST_EXPECTED_EXTENSION: path.join(extensions, installed) }
    });
  } finally {
    if (process.env.CPPULSE_HOST_ARTIFACTS) {
      const evidence = path.resolve(process.env.CPPULSE_HOST_ARTIFACTS);
      await fs.mkdir(evidence, { recursive: true });
      for (const name of ['profile/logs', 'cli-calls.jsonl']) {
        const source = path.join(work, name);
        try { await fs.cp(source, path.join(evidence, name), { recursive: true }); }
        catch (error) { if (error.code !== 'ENOENT') { throw error; } }
      }
      await fs.writeFile(path.join(evidence, 'host-inputs.json'), JSON.stringify({
        executable, vscodeVersion: manifest.engines.vscode, vsix: path.join(root, 'artifacts/cppulse-0.2.0-preview.vsix'),
        cli: process.env.CPPULSE_HOST_CLI, workspace: process.env.CPPULSE_HOST_WORKSPACE, store: process.env.CPPULSE_HOST_STORE
      }, null, 2));
    }
    await fs.rm(work, { recursive: true, force: true });
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
