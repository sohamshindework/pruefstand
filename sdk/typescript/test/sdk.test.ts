import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Recorder, Replay } from '../src/index.ts';

test('redacts records, returns raw tool data, and replays ten times', async () => {
  const recorder = new Recorder('typescript-agent', 'task');
  const raw = await recorder.call('lookup', async input => ({email: input.email, status: 'ok'}), {email: 'person@example.test'});
  assert.equal(raw.email, 'person@example.test');
  const run = recorder.finish({success: true, confidence: .9});
  assert.ok(!recorder.jsonl().includes('person@example.test'));
  for (let n = 0; n < 10; n++) {
    const replay = new Replay(run);
    assert.equal((replay.call('lookup', {email: 'person@example.test'}) as {status: string}).status, 'ok'); replay.assertConsumed();
  }
});
test('budget checks happen before the tool executes', async () => {
  let dispatched = false;
  const recorder = new Recorder('a', 't', {budgetEur: .01});
  await assert.rejects(recorder.call('paid', () => {dispatched = true; return null;}, {}, {maxCostEur: .02}));
  assert.equal(dispatched, false);
});
test('replay rejects argument drift and records errors', async () => {
  const recorder = new Recorder('a', 't');
  await assert.rejects(recorder.call('bad', () => {throw new Error('test failure');}, {id: 1}));
  const replay = new Replay(recorder.finish({success: false}));
  assert.throws(() => replay.call('bad', {id: 2}), /divergence/);
  assert.throws(() => replay.call('bad', {id: 1}), /test failure/); replay.assertConsumed();
});
