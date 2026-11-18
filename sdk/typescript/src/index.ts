import { randomUUID } from 'node:crypto';

export type Json = null | boolean | number | string | Json[] | {[key: string]: Json};
export type Kind = 'tool' | 'model' | 'agent' | 'oversight';
export interface TraceEvent {
  sequence: number; kind: Kind; name: string; inputs: Json; output: Json;
  error: {type: string; message: string; status_code: null; fault: null} | null;
  fault: null; started_at: string; duration_ms: number; cost_eur: number;
  input_tokens: number; output_tokens: number; attributes: Record<string, Json>;
  privacy_findings: {category: string; path: string; count: number}[];
}
export interface TraceRun {
  schema_version: 1; agent: string; task_id: string; condition: string; seed: number;
  run_id: string; started_at: string; finished_at: string | null; success: boolean | null;
  confidence: number | null; harmful_actions: number; loss_eur: number;
  output: Json; metadata: Record<string, Json>; events: TraceEvent[];
}
const patterns: Record<string, RegExp> = {
  iban: /\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b/g,
  email: /\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g,
  steuer_id_candidate: /(?<!\d)\d{11}(?!\d)/g,
  german_address_candidate: /\b[\wÄÖÜäöüß.-]*(?:straße|strasse|str\.|weg|platz)\s+\d+[a-z]?\b/gi,
  health_data_candidate: /\b(?:Diagnose|diagnosis|HIV|Diabetes|Krebs|depression|patient)\b/gi,
  api_key: /\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{15,}|Bearer\s+[A-Za-z0-9._~+/-]{12,})/g,
};
const secrets = new Set(['authorization', 'api_key', 'apikey', 'password', 'secret', 'token', 'access_token', 'cookie', 'set_cookie']);
export function scrub(value: Json, path = '$'): [Json, TraceEvent['privacy_findings']] {
  const findings: TraceEvent['privacy_findings'] = [];
  if (typeof value === 'string') {
    for (const [category, pattern] of Object.entries(patterns)) {
      const matches = [...value.matchAll(new RegExp(pattern))];
      if (matches.length) { findings.push({category, path, count: matches.length}); value = value.replace(new RegExp(pattern), `[REDACTED:${category}]`); }
    }
  } else if (Array.isArray(value)) {
    value = value.map((v, i) => {const [safe, found] = scrub(v, `${path}[${i}]`); findings.push(...found); return safe;});
  } else if (value !== null && typeof value === 'object') {
    const copy: Record<string, Json> = {};
    for (const [key, item] of Object.entries(value)) {
      if (secrets.has(key.toLowerCase().replaceAll('-', '_'))) { copy[key] = '[REDACTED:secret]'; findings.push({category: 'secret', path: `${path}.${key}`, count: 1}); }
      else {const [safe, found] = scrub(item, `${path}.${key}`); copy[key] = safe; findings.push(...found);}
    }
    value = copy;
  }
  return [value, findings];
}
function canonical(value: Json): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonical(value[k])}`).join(',')}}`;
  return JSON.stringify(value);
}
function nonnegative(value: number, name: string) { if (!Number.isFinite(value) || value < 0) throw Error(`${name} must be finite and nonnegative`); }

export class Recorder {
  run: TraceRun; maxCalls: number; budgetEur: number; private reserved = 0; private active = 0;
  constructor(agent: string, taskId: string, options: {seed?: number; maxCalls?: number; budgetEur?: number; metadata?: Record<string, Json>} = {}) {
    if (!agent || !taskId) throw Error('agent and taskId are required');
    this.maxCalls = options.maxCalls ?? 100; this.budgetEur = options.budgetEur ?? 1;
    nonnegative(this.budgetEur, 'budgetEur');
    if (!Number.isInteger(this.maxCalls) || this.maxCalls < 1) throw Error('maxCalls must be a positive integer');
    this.run = {schema_version: 1, agent, task_id: taskId, condition: 'baseline', seed: options.seed ?? 42,
      run_id: randomUUID().replaceAll('-', ''), started_at: new Date().toISOString(), finished_at: null,
      success: null, confidence: null, harmful_actions: 0, loss_eur: 0, output: null,
      metadata: scrub(options.metadata ?? {})[0] as Record<string, Json>, events: []};
  }
  async call<T extends Json>(name: string, fn: (inputs: Record<string, Json>) => T | Promise<T>, inputs: Record<string, Json> = {}, options: {kind?: Kind; maxCostEur?: number} = {}): Promise<T> {
    const cost = options.maxCostEur ?? 0; nonnegative(cost, 'maxCostEur');
    if (this.run.finished_at) throw Error('Run already finished');
    if (this.run.events.length >= this.maxCalls || this.run.events.reduce((n, e) => n + e.cost_eur, 0) + this.reserved + cost > this.budgetEur + 1e-12) throw Error('Budget exceeded before dispatch');
    this.reserved += cost; this.active++;
    const [safe, findings] = scrub(inputs);
    const event: TraceEvent = {sequence: this.run.events.length, kind: options.kind ?? 'tool', name, inputs: safe,
      output: null, error: null, fault: null, started_at: new Date().toISOString(), duration_ms: 0, cost_eur: 0,
      input_tokens: 0, output_tokens: 0, attributes: {}, privacy_findings: findings};
    this.run.events.push(event); const started = performance.now();
    try {
      const output = await fn(inputs), [safeOutput, found] = scrub(output);
      event.output = safeOutput; event.privacy_findings.push(...found); return output;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      event.error = {type: error instanceof Error ? error.name : 'Error', message: String(scrub(message)[0]), status_code: null, fault: null};
      throw error;
    } finally { event.duration_ms = performance.now() - started; event.cost_eur = cost; this.reserved -= cost; this.active--; }
  }
  finish(outcome: {success: boolean; confidence?: number; harmfulActions?: number; lossEur?: number; output?: Json}): TraceRun {
    if (this.active) throw Error('Await all calls before finishing');
    if (typeof outcome.success !== 'boolean') throw Error('success must be boolean');
    if (outcome.confidence !== undefined && (!Number.isFinite(outcome.confidence) || outcome.confidence < 0 || outcome.confidence > 1)) throw Error('confidence must be in [0,1]');
    nonnegative(outcome.harmfulActions ?? 0, 'harmfulActions'); nonnegative(outcome.lossEur ?? 0, 'lossEur');
    Object.assign(this.run, {success: outcome.success, confidence: outcome.confidence ?? null, harmful_actions: outcome.harmfulActions ?? 0,
      loss_eur: outcome.lossEur ?? 0, output: scrub(outcome.output ?? null)[0], finished_at: new Date().toISOString()});
    return structuredClone(this.run);
  }
  jsonl(): string { return JSON.stringify(this.run) + '\n'; }
}
export class Replay {
  run: TraceRun; position = 0;
  constructor(run: TraceRun) { if (run.schema_version !== 1) throw Error('Unsupported schema'); this.run = structuredClone(run); }
  call(name: string, inputs: Record<string, Json> = {}, kind: Kind = 'tool'): Json {
    const event = this.run.events[this.position];
    if (!event || event.name !== name || event.kind !== kind || canonical(event.inputs) !== canonical(scrub(inputs)[0])) throw Error(`Replay divergence at event ${this.position}`);
    this.position++;
    if (event.error) { const error = new Error(event.error.message); error.name = event.error.type; throw error; }
    return structuredClone(event.output);
  }
  assertConsumed(): void { if (this.position !== this.run.events.length) throw Error('Unconsumed replay events'); }
}
