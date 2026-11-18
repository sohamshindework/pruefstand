"""Explicit live call: configure your own test endpoint/model and cost bound."""
import argparse
import os

from pruefstand import Recorder, Store
from pruefstand.adapters import OpenAICompatible


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default=os.environ.get("MODEL_BASE_URL", "http://localhost:11434/v1"))
    parser.add_argument("--max-cost-eur", required=True, type=float)
    args = parser.parse_args()
    with Recorder("live-model-probe", "greeting-de", store=Store("artifacts/live-model.db"), budget_eur=args.max_cost_eur) as recorder:
        client = OpenAICompatible(recorder, base_url=args.base_url, api_key=os.environ.get("MODEL_API_KEY"))
        result = client.complete(model=args.model, messages=[{"role": "user", "content": "Bitte antworten Sie nur mit: Guten Tag!"}], max_cost_eur=args.max_cost_eur)
        answer = result["choices"][0]["message"]["content"]
        recorder.finish(success=answer.strip() == "Guten Tag!", output=answer)
        print(answer)


if __name__ == "__main__":
    main()
