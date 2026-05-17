from __future__ import annotations

import json
import os
from typing import Any

try:
    import boto3
except ModuleNotFoundError:
    boto3 = None


lambda_client = None


def _cors_headers() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": os.environ.get("CORS_ALLOWED_ORIGINS", "*"),
        "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token,X-Amz-Content-Sha256",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        "Content-Type": "application/json",
    }


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {"statusCode": status_code, "headers": _cors_headers(), "body": json.dumps(body)}


def _tool_lambda_name() -> str:
    name = os.environ.get("TOOL_FUNCTION_NAME")
    if not name:
        raise RuntimeError("TOOL_FUNCTION_NAME is not configured")
    return name


def _invoke_tool(tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    global lambda_client
    if boto3 is None:
        raise RuntimeError("boto3 is not available")
    if lambda_client is None:
        lambda_client = boto3.client("lambda", region_name=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"))
    response = lambda_client.invoke(
        FunctionName=_tool_lambda_name(),
        Payload=json.dumps({"tool": tool, "arguments": arguments or {}}).encode("utf-8"),
    )
    raw = response["Payload"].read().decode("utf-8")
    parsed = json.loads(raw)
    body = parsed.get("body", parsed)
    if isinstance(body, str):
        return json.loads(body)
    return body


def _gateway_from_target(target_url: str, body: dict[str, Any]) -> str | None:
    params = body.get("params") if isinstance(body.get("params"), dict) else {}
    requested_gateway = params.get("gateway") or body.get("gateway")
    if requested_gateway:
        return str(requested_gateway)
    if "portfolio-planning" in target_url:
        return "portfolio-planning"
    return None


def _mcp_result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _handle_mcp(body: dict[str, Any]) -> dict[str, Any]:
    target_url = str(body.get("targetUrl") or "")
    mcp_body = body.get("mcpBody") if isinstance(body.get("mcpBody"), dict) else body
    method = mcp_body.get("method")
    request_id = mcp_body.get("id")

    if method == "initialize":
        return _mcp_result(
            request_id,
            {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "public-financial-planning-gateway", "version": "1.0.0"},
                "capabilities": {"tools": {}},
            },
        )

    if method == "tools/list":
        gateway = _gateway_from_target(target_url, mcp_body)
        tools = _invoke_tool("listTools", {"gateway": gateway}).get("tools", [])
        return _mcp_result(request_id, {"tools": tools})

    if method == "tools/call":
        params = mcp_body.get("params") if isinstance(mcp_body.get("params"), dict) else {}
        tool_name = params.get("name")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        if not tool_name:
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "tool name is required"}}
        result = _invoke_tool(str(tool_name), arguments)
        return _mcp_result(request_id, {"content": [{"type": "text", "text": json.dumps(result)}]})

    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Unsupported method: {method}"}}


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    method = event.get("httpMethod")
    path = event.get("path", "")
    if method == "OPTIONS":
        return {"statusCode": 204, "headers": _cors_headers(), "body": ""}

    try:
        if method == "GET" and path.endswith("/gateways/iam"):
            return _response(200, _invoke_tool("listGateways", {}))

        if method == "POST" and path.endswith("/mcp/proxy"):
            body = json.loads(event.get("body") or "{}")
            return _response(200, _handle_mcp(body))

        return _response(404, {"error": f"Unsupported route: {method} {path}"})
    except Exception as exc:
        return _response(500, {"error": str(exc)})
