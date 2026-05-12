from __future__ import annotations

import atexit
import hashlib
import json
import os
from collections.abc import AsyncIterable, Iterable
from typing import Any
from urllib.parse import urlparse

import botocore.session
import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials as BotoCreds
from mcp.client.streamable_http import streamablehttp_client
from strands.tools.mcp import MCPClient


SERVICE_NAME = "bedrock-agentcore"


def _collect_sync_body(stream: Iterable[bytes]) -> bytes:
    chunks = []
    for chunk in stream:
        chunks.append(chunk if isinstance(chunk, (bytes, bytearray)) else str(chunk).encode("utf-8"))
    return b"".join(chunks)


async def _collect_async_body(stream: AsyncIterable[bytes]) -> bytes:
    chunks = []
    async for chunk in stream:
        chunks.append(chunk if isinstance(chunk, (bytes, bytearray)) else str(chunk).encode("utf-8"))
    return b"".join(chunks)


def _resolve_creds(explicit: BotoCreds | None) -> BotoCreds:
    if explicit is not None:
        return explicit
    session = botocore.session.get_session()
    creds = session.get_credentials()
    if not creds:
        raise RuntimeError("AWS credentials not found for SigV4 signing.")
    return creds


def _signed_headers(
    *,
    service: str,
    region: str,
    method: str,
    url: str,
    body: bytes,
    base_headers: dict[str, str],
    creds: BotoCreds,
) -> dict[str, str]:
    parsed = urlparse(url)
    headers = {
        "Host": parsed.netloc,
        "Accept": base_headers.get("accept", "application/json, text/event-stream"),
        "Content-Type": base_headers.get("content-type", "application/json"),
        "Content-Length": str(len(body)),
        "X-Amz-Content-Sha256": hashlib.sha256(body).hexdigest(),
    }
    aws_req = AWSRequest(method=method, url=url, data=body, headers=headers)
    SigV4Auth(creds, service, region).add_auth(aws_req)
    merged = dict(aws_req.headers)
    for key, value in base_headers.items():
        if key.lower() not in {existing.lower() for existing in merged}:
            merged[key] = value
    return merged


class SigV4HTTPAuth(httpx.Auth):
    requires_request_body = True

    def __init__(self, service: str, region: str, credentials: BotoCreds | None = None):
        self.service = service
        self.region = region
        self.credentials = credentials

    def auth_flow(self, request: httpx.Request):
        creds = _resolve_creds(self.credentials)
        body = b""
        if request.method.upper() == "POST":
            body = bytes(request.content) if request.content is not None else _collect_sync_body(request.stream)
        yield httpx.Request(
            method=request.method,
            url=request.url,
            headers=_signed_headers(
                service=self.service,
                region=self.region,
                method=request.method,
                url=str(request.url),
                body=body,
                base_headers=dict(request.headers),
                creds=creds,
            ),
            content=body,
        )

    async def async_auth_flow(self, request: httpx.Request):
        creds = _resolve_creds(self.credentials)
        body = b""
        if request.method.upper() == "POST":
            body = bytes(request.content) if request.content is not None else await _collect_async_body(request.stream)
        yield httpx.Request(
            method=request.method,
            url=request.url,
            headers=_signed_headers(
                service=self.service,
                region=self.region,
                method=request.method,
                url=str(request.url),
                body=body,
                base_headers=dict(request.headers),
                creds=creds,
            ),
            content=body,
        )


def _gateway_urls() -> list[str]:
    raw = os.environ.get("GATEWAY_URL", "")
    return [url.strip() for url in raw.split(",") if url.strip()]


def _make_client(url: str) -> MCPClient:
    region = os.environ.get("GATEWAY_REGION") or os.environ.get("AWS_REGION") or "us-west-2"
    auth = SigV4HTTPAuth(service=SERVICE_NAME, region=region)
    return MCPClient(
        lambda: streamablehttp_client(
            url=url,
            headers={"Accept": "application/json, text/event-stream"},
            auth=auth,
        )
    )


class GatewayToolPool:
    def __init__(self) -> None:
        self.clients: list[MCPClient] = []
        self.tools_list: list[Any] = []
        self.load_tools()
        atexit.register(self.stop)

    def load_tools(self) -> None:
        urls = _gateway_urls()
        if not urls:
            self.clients = []
            self.tools_list = []
            return

        clients: list[MCPClient] = []
        try:
            for url in urls:
                client = _make_client(url)
                client.__enter__()
                clients.append(client)

            tools: list[Any] = []
            for client in clients:
                tools.extend(client.list_tools_sync())

            self.clients = clients
            self.tools_list = tools
        except Exception:
            for client in clients:
                try:
                    client.__exit__(None, None, None)
                except Exception:
                    pass
            raise

    def stop(self) -> None:
        for client in self.clients:
            try:
                client.__exit__(None, None, None)
            except Exception:
                pass
        self.clients = []
        self.tools_list = []

    def tools(self) -> list[Any]:
        return list(self.tools_list)


def pretty_tool_inventory(tools: list[Any]) -> str:
    names = []
    for tool in tools:
        name = getattr(tool, "tool_name", None) or getattr(tool, "name", None)
        if not name and isinstance(tool, dict):
            name = tool.get("name")
        if name:
            names.append(str(name))
    return json.dumps(sorted(names))
