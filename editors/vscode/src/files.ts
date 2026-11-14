/** Bounded local reads rooted in the explicitly selected workspace or run. */
import { constants } from 'node:fs';
import { open, realpath } from 'node:fs/promises';
import path from 'node:path';
import { MAX_SOURCE_BYTES, safeRelativePath, sha256 } from './protocol';

export interface CheckedFile { path: string; bytes: Buffer; sha256: string }

export async function readWithin(root: string, relative: string, maximum = MAX_SOURCE_BYTES): Promise<CheckedFile> {
  safeRelativePath(relative);
  const parent = await realpath(root);
  const candidate = await realpath(path.join(parent, ...relative.split('/')));
  const difference = path.relative(parent, candidate);
  if (!difference || difference.startsWith(`..${path.sep}`) || difference === '..' || path.isAbsolute(difference)) {
    throw new Error('Source/artifact path escapes its explicitly selected root.');
  }
  const stream = await open(candidate, constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0) | (constants.O_NONBLOCK ?? 0));
  try {
    const before = await stream.stat({ bigint: true });
    if (!before.isFile() || before.size > BigInt(maximum)) { throw new Error('Selected source/artifact is not a finite regular file within preview limits.'); }
    const bytes = Buffer.alloc(Number(before.size) + 1);
    let offset = 0;
    while (offset < bytes.length) {
      const result = await stream.read(bytes, offset, bytes.length - offset, null);
      if (!result.bytesRead) { break; }
      offset += result.bytesRead;
    }
    const after = await stream.stat({ bigint: true });
    if (offset !== Number(before.size) || before.dev !== after.dev || before.ino !== after.ino || before.size !== after.size || before.mtimeNs !== after.mtimeNs || before.ctimeNs !== after.ctimeNs) {
      throw new Error('Selected source/artifact changed during the bounded read.');
    }
    const selected = bytes.subarray(0, offset);
    return { path: candidate, bytes: selected, sha256: sha256(selected) };
  } finally { await stream.close(); }
}

export function decodeText(bytes: Buffer): string {
  return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
}
