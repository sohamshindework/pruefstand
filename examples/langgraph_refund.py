"""A real LangGraph execution with recorded tools, no LLM or API key required."""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from pruefstand import ChaosPlan, Fault, InjectedFault, Recorder, Store
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

    def refund_node(_state):
        inputs = {"action": "refund", "amount": 49.9, "idempotency_key": "refund-test-001"}
        try:
            result = tools["refund"](**inputs)
        except InjectedFault:
            result = tools["refund"](**inputs)
        return {"receipt": result}

    graph = StateGraph(State)
    graph.add_node("refund", refund_node)
    graph.add_edge(START, "refund")
    graph.add_edge("refund", END)
    result = graph.compile().invoke({})
    recorder.finish(success=len(ledger.actions) == 1, confidence=.95, output=result)
    print(f"Committed refunds: {len(ledger.actions)}; recorded calls: {len(recorder.run.events)}")


if __name__ == "__main__":
    main()
