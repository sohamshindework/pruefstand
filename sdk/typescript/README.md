# TypeScript recorder

Node.js 22.18+ can execute this typed source directly. This companion implements the v1 trace contract, sensitive-pattern screening, call/cost budget admission, and strict offline replay. The complete fault engine and statistics live in Python. No npm dependencies are required; it is not published to npm.

```typescript
import { writeFile } from 'node:fs/promises';
import { Recorder } from './src/index.ts';

const recorder = new Recorder('my-agent', 'refund-1');
await recorder.call('refund', async ({amount}) => ({status: 'ok', amount}), {amount: 49.9});
recorder.finish({success: true, confidence: 0.9}); // use an independent task evaluator
await writeFile('trace.jsonl', recorder.jsonl());
```

Import a resulting JSONL file using `pruefstand import trace.jsonl --db artifacts/typescript.db`. Run `npm test` in this directory. As with Python, pattern screening is heuristic; raw tool values stay inside the application and the serialized trace is screened.
