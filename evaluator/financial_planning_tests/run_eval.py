from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .ping_agent import invoke_agent


def load_dataset(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if not rows:
        raise ValueError(f"No evaluation items found in {path}")
    return rows


def judge_response(region: str, judge_model: str, question: str, expected: str, actual: str) -> int:
    import boto3

    if expected.lower() in actual.lower():
        return 1

    client = boto3.client("bedrock-runtime", region_name=region)
    prompt = (
        "Return only JSON with keys score and reason. Score is 1 if the actual answer is "
        "factually accurate against the expected answer, otherwise 0.\n\n"
        f"Question: {question}\nExpected: {expected}\nActual: {actual}"
    )
    response = client.converse(
        modelId=judge_model,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 256, "temperature": 0.0},
    )
    text = "".join(
        block.get("text", "")
        for block in response.get("output", {}).get("message", {}).get("content", [])
    )
    try:
        parsed = json.loads(text.strip().removeprefix("```json").removeprefix("```").removesuffix("```"))
        return 1 if int(parsed.get("score", 0)) == 1 else 0
    except Exception:
        return 0


def run_eval(
    *,
    runtime_arn: str,
    region: str,
    judge_model: str,
    dataset: Path,
    min_score: float,
) -> bool:
    rows = load_dataset(dataset)
    correct = 0
    for row in rows:
        question = str(row["question"])
        expected = str(row["expected"])
        actual = invoke_agent(runtime_arn, region, question)
        score = judge_response(region, judge_model, question, expected, actual)
        correct += score
        print(json.dumps({"question": question, "expected": expected, "actual": actual, "score": score}))
    accuracy = correct / len(rows)
    print(json.dumps({"accuracy": accuracy, "min_score": min_score, "passed": accuracy >= min_score}))
    return accuracy >= min_score


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a small public evaluation against AgentCore.")
    parser.add_argument("--runtime-arn", required=True)
    parser.add_argument("--region", default="us-west-2")
    parser.add_argument("--judge-model", default="us.amazon.nova-2-lite-v1:0")
    parser.add_argument("--dataset", default="test-data/sample_eval.jsonl")
    parser.add_argument("--min-score", type=float, default=0.5)
    args = parser.parse_args()

    passed = run_eval(
        runtime_arn=args.runtime_arn,
        region=args.region,
        judge_model=args.judge_model,
        dataset=Path(args.dataset),
        min_score=args.min_score,
    )
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
