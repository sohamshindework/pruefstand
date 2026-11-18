"""A real LangGraph execution with recorded tools, no LLM or API key required."""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from pruefstand import ChaosPlan, Fault, InjectedFault, Recorder, Replay, Store
from pruefstand.adapters.langgraph import recorded_tools
from pruefstand.scenarios import Ledger, load_tasks


class State(TypedDict):
    receipt: dict


def main():
    task = load_tasks()[0]
    ledger = Ledger(task)
    recorder = Recorder("langgraph-idempotent-example", task["id"], store=Store("artifacts/langgraph.db"),
                        chaos=ChaosPlan([Fault("timeout_after", at_call=1)]), metadata={"synthetic": True})
    tools = recorded_tools(recorder, {"refund": ledger.execute})

    def build_graph(refund):
        def refund_node(_state):
            inputs = {"action": "refund", "amount": 49.9, "idempotency_key": "refund-test-001"}
            try:
                result = refund(**inputs)
            except InjectedFault:
                result = refund(**inputs)
            return {"receipt": result}
        graph = StateGraph(State)
        graph.add_node("refund", refund_node)
        graph.add_edge(START, "refund")
        graph.add_edge("refund", END)
        return graph.compile()

    result = build_graph(tools["refund"]).invoke({})
    recorder.finish(success=len(ledger.actions) == 1, confidence=.95, output=result)
    for _ in range(10):
        replay = Replay(recorder.run)
        assert build_graph(lambda _replay=replay, **kwargs: _replay.call("refund", kwargs)).invoke({}) == result
        replay.assert_consumed()
    assert len(ledger.actions) == 1  # Replays never touch the ledger.
    print(f"Committed refunds: {len(ledger.actions)}; recorded calls: {len(recorder.run.events)}; agent replays: 10/10")


if __name__ == "__main__":
    main()
