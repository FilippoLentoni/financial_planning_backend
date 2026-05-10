"""
Runtime REST Proxy Lambda

Proxies runtime invocation requests to AgentCore Runtime via boto3.
Flow: Browser → API Gateway (SigV4) → This Lambda → AgentCore Runtime (boto3).

Security:
- Only allowlisted runtime name patterns are allowed (ALLOWED_RUNTIME_PATTERN)
- Lambda uses its own execution role credentials via boto3
- API Gateway enforces IAM authentication on the caller
"""
import json
import os
import logging
import re
import uuid

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Compile allowed runtime name pattern from environment variable
ALLOWED_RUNTIME_PATTERN = re.compile(
    os.environ.get("ALLOWED_RUNTIME_PATTERN", r"^financial_planning_")
)

# Reuse client across invocations
agentcore_client = boto3.client("bedrock-agentcore")

# Default actor ID when caller identity cannot be determined
_DEFAULT_ACTOR_ID = "anonymous"

# Resolve the current account ID and region for ARN construction.
# When the client sends an ARN with a dummy/wrong account (e.g. 000000000000),
# we rebuild it using the Lambda's own identity so IAM policies match.
_ACCOUNT_ID = None
_REGION = os.environ.get("AWS_REGION", "us-east-1")


def _get_account_id():
    """Lazily resolve the AWS account ID from STS (cached across invocations)."""
    global _ACCOUNT_ID
    if _ACCOUNT_ID is None:
        try:
            _ACCOUNT_ID = boto3.client("sts").get_caller_identity()["Account"]
        except Exception:
            logger.warning("Could not resolve account ID from STS")
            _ACCOUNT_ID = ""
    return _ACCOUNT_ID


def _get_cors_origin(event):
    """Return the Access-Control-Allow-Origin value based on the request Origin header."""
    allowed_raw = os.environ.get("CORS_ALLOWED_ORIGINS", "")
    allowed_origins = [o.strip() for o in allowed_raw.split(",") if o.strip()]

    headers = event.get("headers") or {}
    request_origin = None
    for key, value in headers.items():
        if key.lower() == "origin":
            request_origin = value
            break

    if "*" in allowed_origins:
        return "*"

    if request_origin and request_origin in allowed_origins:
        return request_origin

    return allowed_origins[0] if allowed_origins else "*"


def _safe_session_component(value, default_prefix):
    """Return a session-safe component for AgentCore runtimeSessionId."""
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]", "-", str(value or "").strip())
    if len(cleaned) < 16:
        cleaned = f"{default_prefix}-{uuid.uuid4()}"
    return cleaned[:120]


def handler(event, context):
    """Proxy runtime invocation requests to AgentCore Runtime."""
    logger.info(f'Runtime proxy request: method={event.get("httpMethod")}')

    allowed_origin = _get_cors_origin(event)
    cors_headers = {
        "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token,X-Amz-Content-Sha256",
        "Access-Control-Allow-Methods": "POST,OPTIONS",
    }
    if allowed_origin:
        cors_headers["Access-Control-Allow-Origin"] = allowed_origin

    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": cors_headers, "body": ""}

    try:
        body = json.loads(event.get("body", "{}"))
        runtime_arn = body.get("runtimeArn", "")
        payload = body.get("payload", {})
        session_id = body.get("sessionId", "")

        # Extract caller identity for the runtime session ID
        identity = event.get("requestContext", {}).get("identity", {})
        user_arn = identity.get("userArn", "")
        if user_arn:
            actor_id = user_arn.rsplit("/", 1)[-1] or user_arn.rsplit(":", 1)[-1] or _DEFAULT_ACTOR_ID
        else:
            actor_id = _DEFAULT_ACTOR_ID
        actor_id = _safe_session_component(actor_id, "actor")

        if not runtime_arn:
            return {
                "statusCode": 400,
                "headers": cors_headers,
                "body": json.dumps({"error": "runtimeArn is required"}),
            }

        # Security: validate the runtime name portion of the ARN against allowlist
        # ARN format: arn:aws:bedrock-agentcore:{region}:{account}:runtime/{name}
        runtime_name = runtime_arn.rsplit("/", 1)[-1] if "/" in runtime_arn else runtime_arn
        if not ALLOWED_RUNTIME_PATTERN.match(runtime_name):
            logger.warning(f"Blocked runtime invocation for: {runtime_arn}")
            return {
                "statusCode": 403,
                "headers": cors_headers,
                "body": json.dumps({"error": "Runtime name not allowed"}),
            }

        # Rebuild the ARN using the Lambda's own account ID and region.
        # The client may send a dummy account (e.g. 000000000000) because it
        # doesn't have access to the real account ID.  We always reconstruct
        # the canonical ARN server-side so IAM policies match correctly.
        account_id = _get_account_id()
        canonical_arn = f"arn:aws:bedrock-agentcore:{_REGION}:{account_id}:runtime/{runtime_name}"
        logger.info(f"Canonical runtime ARN: {canonical_arn} (original: {runtime_arn})")

        if isinstance(payload, str):
            payload_bytes = payload.encode("utf-8")
        else:
            payload_bytes = json.dumps(payload).encode("utf-8")
        logger.info(f"Proxying to runtime: {canonical_arn}, payload length: {len(payload_bytes)}")

        # Build the invoke_agent_runtime kwargs
        invoke_kwargs = {
            "agentRuntimeArn": canonical_arn,
            "payload": payload_bytes,
        }
        # Construct runtimeSessionId in '<actorId>___<sessionId>' format
        session_id = _safe_session_component(session_id, "session")
        runtime_session_id = f"{actor_id}___{session_id}"
        invoke_kwargs["runtimeSessionId"] = runtime_session_id

        # Call AgentCore via boto3 — handles SigV4 signing automatically
        response = agentcore_client.invoke_agent_runtime(**invoke_kwargs)

        # Read the streaming response body
        # The response field is a StreamingBody (blob with streaming=True)
        response_stream = response.get("response", b"")
        if hasattr(response_stream, "read"):
            raw_body = response_stream.read().decode("utf-8")
        elif isinstance(response_stream, bytes):
            raw_body = response_stream.decode("utf-8")
        else:
            raw_body = str(response_stream)

        status_code = response.get("statusCode", 200)
        logger.info(f"Runtime response: status={status_code}, body length={len(raw_body)}")

        # The runtime returns SSE format ("data: {...}\n\n") or NDJSON.
        # Parse all events into a clean JSON envelope for the frontend.
        events = []
        text_parts = []
        final_message = None
        for line in raw_body.splitlines():
            line = line.strip()
            if not line:
                continue
            # Strip SSE "data: " prefix if present
            if line.startswith("data: "):
                line = line[6:]
            if not line or line == "[DONE]":
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue  # Skip unparseable lines (Python repr debug strings)

            # Skip non-dict values (e.g. quoted Python repr strings)
            if not isinstance(parsed, dict):
                continue

            events.append(parsed)

            # Extract text from nested AgentCore/Strands event formats:
            # 1. Streaming delta: {"event":{"contentBlockDelta":{"delta":{"text":"..."}}}}
            evt = parsed.get("event")
            if isinstance(evt, dict):
                delta_block = evt.get("contentBlockDelta")
                if isinstance(delta_block, dict):
                    delta = delta_block.get("delta")
                    if isinstance(delta, dict) and delta.get("text"):
                        text_parts.append(delta["text"])

            # 2. Final message: {"message":{"role":"assistant","content":[{"text":"..."}]}}
            msg = parsed.get("message")
            if isinstance(msg, dict) and msg.get("content"):
                final_message = msg

            # 3. Direct text (fallback)
            if parsed.get("text") and not evt and not msg:
                text_parts.append(parsed["text"])

        # Prefer aggregated streaming deltas; fall back to final message text
        if text_parts:
            response_text = "".join(text_parts)
        elif final_message:
            # Extract text from the final message content blocks
            parts = []
            for block in final_message.get("content", []):
                if isinstance(block, dict) and block.get("text"):
                    parts.append(block["text"])
            response_text = "".join(parts)
        else:
            response_text = ""

        result = {
            "response": response_text,
            "events": events,
            "sessionId": session_id,
            "message": final_message,
        }

        return {
            "statusCode": status_code,
            "headers": {**cors_headers, "Content-Type": "application/json"},
            "body": json.dumps(result),
        }

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        status_code = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 500)
        logger.error(f"AgentCore error: {error_code} - {error_message}")
        return {
            "statusCode": status_code,
            "headers": {**cors_headers, "Content-Type": "application/json"},
            "body": json.dumps({"error": error_code, "detail": error_message}),
        }
    except Exception as e:
        logger.error(f"Runtime proxy error: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": cors_headers,
            "body": json.dumps({"error": "Internal server error"}),
        }
