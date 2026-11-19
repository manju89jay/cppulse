/** Finite public-contract validation; no policy, scorer or detector calculation. */
import { createHash } from 'node:crypto';
import path from 'node:path';

export const MAX_RESPONSE_BYTES = 16 * 1024 * 1024;
export const MAX_DIAGNOSTICS = 20_000;
export const MAX_SOURCE_BYTES = 16 * 1024 * 1024;
export interface ClientLimits { maxResponseBytes: number; maxSourceBytes: number; maxDiagnostics: number }
export function clientLimits(config: JsonObject = {}): ClientLimits {
  const bounded = (key: string, fallback: number, maximum: number): number => {
    const value = config[key] ?? fallback;
    if (!Number.isSafeInteger(value) || value < 1 || value > maximum) { throw new Error(`${key} must be a finite integer limit between 1 and ${maximum}.`); }
    return value;
  };
  return { maxResponseBytes: bounded('responseLimitMiB',16,64)*1024*1024,
    maxSourceBytes: bounded('sourceLimitMiB',16,64)*1024*1024, maxDiagnostics: bounded('diagnosticLimit',MAX_DIAGNOSTICS,100_000) };
}
export const DEFAULT_LIMITS = clientLimits();
const SHA = /^[a-f0-9]{64}$/;
const ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/;
const REQUIRED_COMMANDS = ['doctor', 'analyze', 'collect', 'check', 'report', 'explain', 'export-sarif'];

export type JsonObject = Record<string, any>;
export interface Pins { runId: string; manifestSha256: string }
export interface Capabilities {
  contract_version: string;
  tool_version: string;
  snapshot_view_versions: string[];
  sarif_versions: string[];
  sarif_column_kinds: string[];
  commands: string[];
  execution_on_open: boolean;
}

export function object(value: unknown, label: string): JsonObject {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${label} must be a JSON object.`);
  }
  return value as JsonObject;
}

function strings(value: unknown, label: string): string[] {
  if (!Array.isArray(value) || value.some(item => typeof item !== 'string')) {
    throw new Error(`${label} must be an array of strings.`);
  }
  return value;
}

export function sha256(value: string | Buffer): string {
  return createHash('sha256').update(value).digest('hex');
}

export function parseJson(text: string, label: string, maximum = MAX_RESPONSE_BYTES): JsonObject {
  if (!Number.isSafeInteger(maximum) || maximum < 1 || Buffer.byteLength(text, 'utf8') > maximum) {
    throw new Error(`${label} exceeds the ${maximum}-byte preview response limit; no truncated clean result is shown.`);
  }
  try {
    return object(JSON.parse(text), label);
  } catch (error) {
    throw new Error(`${label} is invalid: ${error instanceof Error ? error.message : String(error)}`);
  }
}

export function validateCapabilities(value: unknown): Capabilities {
  const caps = object(value, 'Client capabilities');
  if (caps.contract_version !== '1.0.0' || typeof caps.tool_version !== 'string' || !caps.tool_version) {
    throw new Error('Unsupported cppulse client capability version. Install a matching CLI candidate.');
  }
  if (!strings(caps.snapshot_view_versions, 'snapshot_view_versions').includes('2.0.0') ||
      !strings(caps.sarif_versions, 'sarif_versions').includes('2.1.0') ||
      !strings(caps.sarif_column_kinds, 'sarif_column_kinds').includes('unicodeCodePoints')) {
    throw new Error('The selected CLI does not provide the preview snapshot/SARIF contracts.');
  }
  const commands = strings(caps.commands, 'commands');
  if (new Set(commands).size !== commands.length || REQUIRED_COMMANDS.some(command => !commands.includes(command)) || caps.execution_on_open !== false) {
    throw new Error('Required public CLI capabilities are missing or incompatible.');
  }
  return caps as Capabilities;
}

export function validatePins(runId?: string, manifestSha256?: string): Pins | undefined {
  if (runId === undefined && manifestSha256 === undefined) { return undefined; }
  if (typeof runId !== 'string' || !ID.test(runId) || typeof manifestSha256 !== 'string' || !SHA.test(manifestSha256)) {
    throw new Error('Select both a valid run ID and its exact manifest SHA-256, or neither.');
  }
  return { runId, manifestSha256 };
}

/** A completed operation must identify its own publication, never a later latest. */
export function requireOperationPins(value: unknown): Pins {
  const result = object(value, 'Operation run pins');
  const pins = validatePins(result.run_id, result.manifest_sha256);
  if (!pins) { throw new Error('Operation returned no retained run pins; no unpinned follow-up read is permitted.'); }
  return pins;
}

export function safeRelativePath(value: unknown): string {
  if (typeof value !== 'string' || !value || value.includes('\\') || value.includes(':') || /[\u0000-\u001f\u007f]/u.test(value) ||
      path.posix.isAbsolute(value) || value.split('/').some(part => !part || part === '.' || part === '..')) {
    throw new Error(`Unsafe source/artifact path: ${String(value)}`);
  }
  if (Buffer.from(value, 'utf8').toString('utf8') !== value) { throw new Error('Path contains invalid Unicode.'); }
  return value;
}

export function decodeSourceUri(uri: unknown): string {
  if (typeof uri !== 'string') { throw new Error('SARIF source URI must be a string.'); }
  let decoded: string;
  try { decoded = decodeURIComponent(uri); } catch { throw new Error('SARIF URI has invalid escaping.'); }
  return safeRelativePath(decoded);
}

function checkWrapper(wrapper: JsonObject, artifacts: Map<string, JsonObject>): void {
  const descriptor = artifacts.get(wrapper.artifact_id);
  if (!descriptor || typeof wrapper.raw_json !== 'string' || !SHA.test(wrapper.sha256) ||
      descriptor.sha256 !== wrapper.sha256 || descriptor.size_bytes !== wrapper.size_bytes || sha256(wrapper.raw_json) !== wrapper.sha256 ||
      Buffer.byteLength(wrapper.raw_json, 'utf8') !== wrapper.size_bytes) {
    throw new Error('A retained view artifact does not match its exact descriptor/bytes.');
  }
}

export function parseSnapshot(text: string, limits = DEFAULT_LIMITS): JsonObject {
  const view = parseJson(text, 'Snapshot view', limits.maxResponseBytes);
  if (view.version !== '2.0.0' || typeof view.run_manifest_json !== 'string') { throw new Error('Unsupported snapshot_view version.'); }
  const run = object(view.run, 'Run');
  validatePins(run.id, run.manifest_sha256);
  if (sha256(view.run_manifest_json) !== run.manifest_sha256) { throw new Error('Run manifest bytes do not match the selected SHA-256.'); }
  const manifest = parseJson(view.run_manifest_json, 'Retained run manifest', limits.maxResponseBytes);
  const source = object(view.source, 'Source');
  if (manifest.version !== '2.0.0' || manifest.run_id !== run.id || manifest.status !== run.status ||
      !SHA.test(source.digest) || source.digest !== run.source_digest || manifest.source?.digest !== source.digest ||
      !['completed', 'partial', 'cancelled'].includes(run.status) || !['verified', 'unverified'].includes(run.input_verification)) {
    throw new Error('Snapshot run/source identity or status is inconsistent.');
  }
  if (!Array.isArray(source.files) || !Array.isArray(view.artifacts) || !Array.isArray(view.facts) ||
      !Array.isArray(view.contexts) || !Array.isArray(view.stages) || !Array.isArray(view.gaps) || !Array.isArray(view.limitations)) {
    throw new Error('Snapshot view is missing required finite inventories.');
  }
  const sourceNames = new Set<string>();
  for (const row of source.files) {
    const file = object(row, 'Source entry');
    const name = safeRelativePath(file.path);
    if (sourceNames.has(name) || !SHA.test(file.sha256) || !Number.isSafeInteger(file.size_bytes) || file.size_bytes < 0) {
      throw new Error('Source inventory has invalid or duplicated entries.');
    }
    sourceNames.add(name);
  }
  if (JSON.stringify(source.files) !== JSON.stringify(manifest.source.files)) { throw new Error('Snapshot source inventory differs from its retained manifest.'); }
  const artifacts = new Map<string, JsonObject>();
  for (const row of view.artifacts) {
    const artifact = object(row, 'Artifact');
    safeRelativePath(artifact.path);
    if (typeof artifact.id !== 'string' || artifacts.has(artifact.id) || !SHA.test(artifact.sha256) || !Number.isSafeInteger(artifact.size_bytes) || artifact.size_bytes < 0) {
      throw new Error('Artifact inventory has invalid or duplicated entries.');
    }
    artifacts.set(artifact.id, artifact);
  }
  if (JSON.stringify(view.artifacts) !== JSON.stringify(manifest.artifacts)) { throw new Error('Snapshot artifact inventory differs from its retained manifest.'); }
  for (const row of view.facts) { checkWrapper(object(row, 'Fact wrapper'), artifacts); }
  const legacy = object(view.legacy, 'Legacy slots');
  for (const key of ['findings', 'git_metrics', 'risk_scores', 'roadmap']) {
    if (legacy[key] !== null) { checkWrapper(object(legacy[key], 'Legacy wrapper'), artifacts); }
  }
  if (view.assessment !== null) {
    const assessment = object(view.assessment, 'Assessment');
    checkWrapper(assessment, artifacts);
    const display = object(assessment.display, 'Stored assessment display');
    if (!['passed', 'failed', 'insufficient_evidence'].includes(display.gate) || !Array.isArray(display.controls)) {
      throw new Error('Invalid stored assessment display.');
    }
    for (const value of Object.values(object(display.scores, 'Stored scores'))) {
      if (value !== null && typeof value !== 'string') { throw new Error('Stored score display tokens must not be converted to JavaScript numbers.'); }
    }
  }
  return view;
}

export function parseSarif(text: string, view?: JsonObject, limits = DEFAULT_LIMITS): JsonObject {
  const sarif = parseJson(text, 'SARIF', limits.maxResponseBytes);
  if (sarif.version !== '2.1.0' || !Array.isArray(sarif.runs) || !sarif.runs.length) { throw new Error('Expected SARIF 2.1.0 runs.'); }
  let count = 0;
  for (const row of sarif.runs) {
    const run = object(row, 'SARIF run');
    if (!['unicodeCodePoints', 'utf16CodeUnits'].includes(run.columnKind) || run.tool?.driver?.name !== 'cppulse' || !Array.isArray(run.results)) {
      throw new Error('Unsupported cppulse SARIF tool, column kind or results.');
    }
    if (view) {
      const properties = object(run.properties, 'SARIF identity');
      if (properties.cppulseOwningRunId !== view.run.id || properties.cppulseInputRunId !== view.run.id ||
          properties.cppulseInputManifestSha256 !== view.run.manifest_sha256 || properties.cppulseSourceDigest !== view.source.digest) {
        throw new Error('SARIF belongs to a different selected run, manifest or source.');
      }
    }
    for (const rawResult of run.results) {
      const result = object(rawResult, 'SARIF result');
      if (typeof result.ruleId !== 'string' || typeof result.message?.text !== 'string' || !['error', 'warning', 'note', 'none'].includes(result.level)) {
        throw new Error('Malformed SARIF finding.');
      }
      if (!Array.isArray(result.locations) || !result.locations.length) { throw new Error('SARIF finding has no supported source location.'); }
      count += result.locations.length;
      if (count > limits.maxDiagnostics) { throw new Error(`This preview accepts at most ${limits.maxDiagnostics} diagnostic occurrences; none were silently truncated.`); }
      for (const location of result.locations) {
        const physical = object(location.physicalLocation, 'SARIF physical location');
        decodeSourceUri(physical.artifactLocation?.uri);
        const region = object(physical.region, 'SARIF source region');
        if (!Number.isSafeInteger(region.startLine) || region.startLine < 1 ||
            (region.startColumn !== undefined && (!Number.isSafeInteger(region.startColumn) || region.startColumn < 1))) {
          throw new Error('Invalid SARIF source location.');
        }
      }
    }
  }
  return sarif;
}

/** Translate declared one-based columns to zero-based VS Code UTF-16 units. */
export function columnToUtf16(line: string, column: number, kind: string): number {
  if (!Number.isSafeInteger(column) || column < 1) { throw new Error('Invalid source column.'); }
  const offset = column - 1;
  if (kind === 'unicodeCodePoints') {
    const points = Array.from(line);
    if (offset > points.length) { throw new Error('Source column exceeds retained line.'); }
    return points.slice(0, offset).join('').length;
  }
  if (kind === 'utf16CodeUnits') {
    if (offset > line.length) { throw new Error('UTF-16 column exceeds retained line.'); }
    return offset;
  }
  if (kind === 'utf8Bytes') {
    const bytes = Buffer.from(line, 'utf8');
    if (offset > bytes.length) { throw new Error('Native byte column exceeds retained line.'); }
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes.subarray(0, offset)).length;
  }
  throw new Error('Unsupported source column kind.');
}

/** A superseded asynchronous result cannot replace a newer editor selection. */
export class Generation {
  private epoch = 0;
  begin(): number { return ++this.epoch; }
  current(value: number): boolean { return value === this.epoch; }
  invalidate(): void { ++this.epoch; }
}

/** Match libclang source lines: CRLF is one terminator, LFCR is two. */
export function splitSourceLines(text: string): string[] {
  return text.split(/\r\n|\r|\n/);
}
