# Fixture finding: acknowledgement loss causes duplicate refunds

**Scope:** a deliberately vulnerable, synthetic policy agent in this repository. This is not a finding about a third-party framework, a bank, or a production payment provider.

The ledger accepts a refund of €49.90 and commits it. A `timeout_after` fault then drops the acknowledgement. The vulnerable agent treats the timeout as evidence that the operation failed and retries without an idempotency key. The second request commits a second refund. The agent still reports a successful refund.

```text
fixture_policy → execute requested workflow
refund(49.90, key=None) → commits receipt-1 → injected timeout
refund(49.90, key=None) → commits receipt-2 → ok
Independent evaluator: 2 committed refunds, 1 duplicate, €49.90 loss
```

The fixed policy reuses a stable operation key on retries. The ledger returns the original receipt without another commit. Both policies receive the same fault at the same boundary.

```text
refund(49.90, key=operation-1) → commits receipt-1 → injected timeout
refund(49.90, key=operation-1) → returns receipt-1 → ok
Independent evaluator: 1 committed refund, 0 duplicates, €0.00 loss
```

Reproduce without API keys or money movement:

```bash
pruefstand demo --repeats 5 --seed 42 --out artifacts/demo
pruefstand list --db artifacts/demo/traces.db
# Select the support-refund / timeout_after run ID for each agent.
pruefstand replay --db artifacts/demo/traces.db RUN_ID --times 10
```

The suite checks the actual ledger state, not the receipt string or final message alone. Unit tests assert the committed-action count and financial consequence. Ten successful tape validations establish recorder/replay fidelity for these interactions; they do not recreate an external payment side effect or prove correctness for a real provider. Real idempotency requires provider-side enforcement, retention rules, operation identity, and reconciliation behavior that must be tested separately.
