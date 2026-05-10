from __future__ import annotations

import argparse
import json
import uuid

from .streaming import extract_response_text, iter_objects


def invoke_agent(runtime_arn: str, region: str, prompt: str) -> str:
    import boto3

    client = boto3.client("bedrock-agentcore", region_name=region)
    response = client.invoke_agent_runtime(
        payload=json.dumps({"prompt": prompt}).encode("utf-8"),
        runtimeSessionId=f"testuser___{uuid.uuid4()}",
        agentRuntimeArn=runtime_arn,
    )
    body = response.get("response") or response.get("body") or response.get("payload") or response
    return extract_response_text(iter_objects(body))


def main() -> None:
    parser = argparse.ArgumentParser(description="Invoke a deployed Bedrock AgentCore runtime.")
    parser.add_argument("--runtime-arn", required=True)
    parser.add_argument("--region", default="us-west-2")
    parser.add_argument(
        "--prompt",
        default="health",
        help="Use the default health prompt for a deterministic low-cost runtime check.",
    )
    args = parser.parse_args()

    text = invoke_agent(args.runtime_arn, args.region, args.prompt)
    print(text)
    if not text:
        raise SystemExit("Agent returned an empty response")


if __name__ == "__main__":
    main()
