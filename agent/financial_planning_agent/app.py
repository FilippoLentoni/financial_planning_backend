from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

import boto3
from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent, tool
from strands_tools import calculator

app = BedrockAgentCoreApp()


def _model_id() -> str:
    return os.environ.get("MODEL_ID", "us.amazon.nova-2-lite-v1:0")


def _invoke_tool_lambda(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    function_name = os.environ.get("TOOL_FUNCTION_NAME")
    if not function_name:
        return {"error": "TOOL_FUNCTION_NAME is not configured"}
    client = boto3.client("lambda", region_name=os.environ.get("AWS_REGION"))
    response = client.invoke(
        FunctionName=function_name,
        Payload=json.dumps({"tool": tool_name, "arguments": payload}).encode("utf-8"),
    )
    raw = response["Payload"].read().decode("utf-8")
    parsed = json.loads(raw)
    body = parsed.get("body", parsed)
    if isinstance(body, str):
        return json.loads(body)
    return body


@tool
def health_check() -> dict[str, str]:
    """Return runtime health metadata."""
    return {
        "status": "ok",
        "stage": os.environ.get("STAGE", "unknown"),
        "region": os.environ.get("AWS_REGION", "unknown"),
    }


@tool
def discover_gateways() -> dict[str, Any]:
    """List financial-planning gateways available to this backend."""
    return _invoke_tool_lambda("listGateways", {})


@tool
def discover_gateway_tools(gateway: str = "portfolio-planning") -> dict[str, Any]:
    """List tools exposed by the portfolio-planning gateway."""
    return _invoke_tool_lambda("listTools", {"gateway": gateway or "portfolio-planning"})


@tool
def list_portfolios() -> dict[str, Any]:
    """List synthetic portfolios available for planning."""
    return _invoke_tool_lambda("list-portfolios", {})


@tool
def get_portfolio_snapshot(portfolio_id: str = "demo-growth-income") -> dict[str, Any]:
    """Return holdings, cash, prices, and synthetic daily context."""
    return _invoke_tool_lambda("get-portfolio-snapshot", {"portfolio_id": portfolio_id})


@tool
def get_market_context(symbols: list[str] | None = None) -> dict[str, Any]:
    """Return synthetic daily news/context for requested stock symbols."""
    return _invoke_tool_lambda("get-market-context", {"symbols": symbols or []})


@tool
def run_portfolio_optimization(
    portfolio_id: str = "demo-growth-income",
    risk_target: str = "moderate",
    cash_available: float = 18500.0,
    max_trade_value_per_week: float = 7500.0,
) -> dict[str, Any]:
    """Run a dummy 16-week portfolio optimizer and return a simulation id."""
    return _invoke_tool_lambda(
        "run-portfolio-optimization",
        {
            "portfolio_id": portfolio_id,
            "risk_target": risk_target,
            "cash_available": cash_available,
            "max_trade_value_per_week": max_trade_value_per_week,
        },
    )


@tool
def get_simulation_status(simulation_id: str) -> dict[str, Any]:
    """Read the status for a portfolio-planning simulation."""
    return _invoke_tool_lambda("get-simulation-status", {"simulation_id": simulation_id})


@tool
def get_simulation_results(simulation_id: str) -> dict[str, Any]:
    """Retrieve a generated 16-week trade plan."""
    return _invoke_tool_lambda("get-simulation-results", {"simulation_id": simulation_id})


@tool
def explain_trade_plan(simulation_id: str) -> dict[str, Any]:
    """Explain the buy/sell rationale for a generated trade plan."""
    return _invoke_tool_lambda("explain-trade-plan", {"simulation_id": simulation_id})


@tool
def run_what_if_analysis(
    simulation_id: str,
    cash_available: float = 18500.0,
    forecast_shock_pct: float = 0.0,
    missed_trade_symbols: list[str] | None = None,
) -> dict[str, Any]:
    """Analyze liquidity, adherence, or forecast-error impact on the plan."""
    return _invoke_tool_lambda(
        "run-what-if-analysis",
        {
            "simulation_id": simulation_id,
            "cash_available": cash_available,
            "forecast_shock_pct": forecast_shock_pct,
            "missed_trade_symbols": missed_trade_symbols or [],
        },
    )


@tool
def record_weekly_review(
    simulation_id: str,
    week: int,
    actual_cash: float = 18500.0,
    actual_value: float = 0.0,
    notes: str = "",
) -> dict[str, Any]:
    """Record weekly adherence and actual portfolio-value observations."""
    return _invoke_tool_lambda(
        "record-weekly-review",
        {
            "simulation_id": simulation_id,
            "week": week,
            "actual_cash": actual_cash,
            "actual_value": actual_value,
            "notes": notes,
        },
    )


@tool
def generate_weekly_plan_report(
    simulation_id: str,
    previous_simulation_id: str = "",
    week: int = 1,
) -> dict[str, Any]:
    """Generate a report for the next 16 weeks and deviations from the prior plan."""
    return _invoke_tool_lambda(
        "generate-weekly-plan-report",
        {
            "simulation_id": simulation_id,
            "previous_simulation_id": previous_simulation_id,
            "week": week,
        },
    )


_agent: Agent | None = None


def _agent_instance() -> Agent:
    global _agent
    if _agent is None:
        _agent = Agent(
            model=_model_id(),
            tools=[
                calculator,
                health_check,
                discover_gateways,
                discover_gateway_tools,
                list_portfolios,
                get_portfolio_snapshot,
                get_market_context,
                run_portfolio_optimization,
                get_simulation_status,
                get_simulation_results,
                explain_trade_plan,
                run_what_if_analysis,
                record_weekly_review,
                generate_weekly_plan_report,
            ],
            system_prompt=(
                "You are a financial planning assistant for portfolio review workflows. "
                "Use the portfolio-planning gateway tools to inspect synthetic holdings, run the "
                "dummy 16-week optimizer, retrieve simulations, explain buy/sell plans, analyze "
                "liquidity or forecast deviation, and prepare weekly review reports. "
                "Never present output as financial advice. Clearly state that the current math "
                "model and daily stock data are synthetic placeholders until the dedicated "
                "portfolio model pipeline is connected through MCP."
            ),
            callback_handler=None,
        )
    return _agent


def _extract_prompt(payload: dict[str, Any]) -> str:
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is required")
    return prompt


def _is_health_prompt(prompt: str) -> bool:
    return prompt.strip().lower() in {"health", "health check", "ping", "status"}


@app.entrypoint
async def invoke(payload: dict[str, Any], context: Any = None) -> AsyncIterator[dict[str, Any]]:
    prompt = _extract_prompt(payload)
    if _is_health_prompt(prompt):
        yield {
            "message": {
                "content": [
                    {
                        "text": json.dumps(
                            {
                                "status": "ok",
                                "stage": os.environ.get("STAGE", "unknown"),
                                "region": os.environ.get("AWS_REGION", "unknown"),
                            },
                        ),
                    },
                ],
            },
        }
        return

    async for event in _agent_instance().stream_async(prompt):
        yield event


def main() -> None:
    app.run(host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8080")))


if __name__ == "__main__":
    main()
