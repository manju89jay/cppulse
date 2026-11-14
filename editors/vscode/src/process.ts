/** Literal argv execution with finite capture and cooperative process-tree stop. */
import { spawn, ChildProcess } from 'node:child_process';
import { MAX_RESPONSE_BYTES } from './protocol';

export interface ProcessOptions {
  cwd: string;
  timeoutMs?: number;
  maxBytes?: number;
  signal?: AbortSignal;
  log?: (channel: 'stdout' | 'stderr', chunk: string) => void;
}
export interface ProcessResult { exitCode: number | null; signal: NodeJS.Signals | null; stdout: string; stderr: string }

export async function runProcess(executable: string, argv: readonly string[], options: ProcessOptions): Promise<ProcessResult> {
  if (!executable || executable.includes('\0') || argv.some(value => typeof value !== 'string' || value.includes('\0'))) {
    throw new Error('CLI executable/arguments must be literal strings without NUL.');
  }
  if (options.signal?.aborted) { throw new Error('cppulse action cancelled before execution.'); }
  const maxBytes = options.maxBytes ?? MAX_RESPONSE_BYTES;
  const timeoutMs = options.timeoutMs ?? 300_000;
  if (!Number.isSafeInteger(maxBytes) || maxBytes < 1 || !Number.isSafeInteger(timeoutMs) || timeoutMs < 1) {
    throw new Error('Process capture and time limits must be positive integers.');
  }
  return new Promise((resolve, reject) => {
    let child: ChildProcess;
    const chunks: Record<'stdout' | 'stderr', Buffer[]> = { stdout: [], stderr: [] };
    const sizes = { stdout: 0, stderr: 0 };
    let failure: Error | undefined;
    let settled = false;
    let escalation: NodeJS.Timeout | undefined;
    let killTimer: NodeJS.Timeout | undefined;
    const signal = (selected: NodeJS.Signals): void => {
      if (!child.pid) { return; }
      try {
        if (process.platform === 'win32') { child.kill(selected); }
        else { process.kill(-child.pid, selected); }
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== 'ESRCH') { options.log?.('stderr', `Cannot signal CLI process: ${String(error)}\n`); }
      }
    };
    const stop = (error: Error): void => {
      if (failure || settled) { return; }
      failure = error;
      signal('SIGINT');
      escalation = setTimeout(() => signal('SIGTERM'), 1200);
      killTimer = setTimeout(() => signal('SIGKILL'), 2400);
    };
    const cancel = (): void => stop(new Error('cppulse action cancelled; previous retained data remains historical.'));
    const timeout = setTimeout(() => stop(new Error('cppulse action exceeded its wall-time limit.')), timeoutMs);
    const clean = (): void => {
      clearTimeout(timeout);
      if (escalation) { clearTimeout(escalation); }
      if (killTimer) { clearTimeout(killTimer); }
      options.signal?.removeEventListener('abort', cancel);
    };
    try {
      child = spawn(executable, [...argv], {
        cwd: options.cwd,
        shell: false,
        windowsHide: true,
        detached: process.platform !== 'win32',
        stdio: ['ignore', 'pipe', 'pipe'],
      });
    } catch (error) {
      clean(); reject(new Error(`Cannot start cppulse: ${String(error)}`)); return;
    }
    options.signal?.addEventListener('abort', cancel, { once: true });
    if (options.signal?.aborted) { cancel(); }
    const capture = (channel: 'stdout' | 'stderr', chunk: Buffer): void => {
      sizes[channel] += chunk.length;
      if (sizes[channel] > maxBytes) { stop(new Error(`cppulse ${channel} exceeded the ${maxBytes}-byte preview capture limit.`)); return; }
      chunks[channel].push(chunk);
      options.log?.(channel, chunk.toString('utf8'));
    };
    child.stdout?.on('data', (chunk: Buffer) => capture('stdout', chunk));
    child.stderr?.on('data', (chunk: Buffer) => capture('stderr', chunk));
    child.on('error', error => {
      if (settled) { return; }
      settled = true; clean(); reject(new Error(`Cannot start cppulse: ${error.message}`));
    });
    child.on('close', (exitCode, exitSignal) => {
      if (settled) { return; }
      settled = true; clean();
      if (failure) {
        // The parent can exit cooperatively while a child ignores SIGINT.
        // Finish stopping this owned process group before reporting cancellation.
        signal('SIGTERM');
        setTimeout(() => { signal('SIGKILL'); reject(failure); }, 120);
        return;
      }
      try {
        const decode = (channel: 'stdout' | 'stderr'): string => new TextDecoder('utf-8', { fatal: true }).decode(Buffer.concat(chunks[channel]));
        resolve({ exitCode, signal: exitSignal, stdout: decode('stdout'), stderr: decode('stderr') });
      } catch { reject(new Error('cppulse output is not valid UTF-8.')); }
    });
  });
}
