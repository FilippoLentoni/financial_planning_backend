from __future__ import annotations

import hashlib
import json
import os
import time
from decimal import Decimal
from typing import Any

try:
    import boto3
    from botocore.exceptions import ClientError
except ModuleNotFoundError:
    boto3 = None

    class ClientError(Exception):
        pass


STOCKS = {
    "AAPL": {"sector": "Technology", "price": 188.4, "expected_return": 0.11, "risk": 0.18, "signal": "positive"},
    "MSFT": {"sector": "Technology", "price": 421.2, "expected_return": 0.12, "risk": 0.16, "signal": "positive"},
    "AMZN": {"sector": "Consumer", "price": 182.7, "expected_return": 0.10, "risk": 0.22, "signal": "neutral"},
    "NVDA": {"sector": "Technology", "price": 875.0, "expected_return": 0.18, "risk": 0.34, "signal": "positive"},
    "JPM": {"sector": "Financials", "price": 196.5, "expected_return": 0.08, "risk": 0.15, "signal": "neutral"},
    "JNJ": {"sector": "Healthcare", "price": 151.8, "expected_return": 0.05, "risk": 0.09, "signal": "defensive"},
    "XOM": {"sector": "Energy", "price": 118.2, "expected_return": 0.06, "risk": 0.20, "signal": "neutral"},
    "V": {"sector": "Financials", "price": 279.4, "expected_return": 0.09, "risk": 0.13, "signal": "positive"},
}

BASE_HOLDINGS = {
    "AAPL": 42,
    "MSFT": 18,
    "AMZN": 30,
    "NVDA": 8,
    "JPM": 35,
    "JNJ": 24,
    "XOM": 22,
    "V": 15,
}

DEFAULT_CASH = 18_500.0
DEFAULT_RISK_TARGET = "moderate"

TOOL_CATALOG = [
    {
        "name": "list-portfolios",
        "gateway": "portfolio-planning",
        "description": "List synthetic portfolios available for planning.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get-portfolio-snapshot",
        "gateway": "portfolio-planning",
        "description": "Return current synthetic holdings, cash, prices, and portfolio value.",
        "inputSchema": {
            "type": "object",
            "properties": {"portfolio_id": {"type": "string"}},
        },
    },
    {
        "name": "get-market-context",
        "gateway": "portfolio-planning",
        "description": "Return synthetic daily market/news context for tracked stocks.",
        "inputSchema": {
            "type": "object",
            "properties": {"symbols": {"type": "array", "items": {"type": "string"}}},
        },
    },
    {
        "name": "run-portfolio-optimization",
        "gateway": "portfolio-planning",
        "description": "Create a cost-safe 16-week synthetic buy/sell optimization plan.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "portfolio_id": {"type": "string"},
                "risk_target": {"type": "string", "enum": ["conservative", "moderate", "growth"]},
                "cash_available": {"type": "number"},
                "max_trade_value_per_week": {"type": "number"},
            },
        },
    },
    {
        "name": "get-simulation-status",
        "gateway": "portfolio-planning",
        "description": "Read synthetic optimization simulation status.",
        "inputSchema": {
            "type": "object",
            "properties": {"simulation_id": {"type": "string"}},
            "required": ["simulation_id"],
        },
    },
    {
        "name": "get-simulation-results",
        "gateway": "portfolio-planning",
        "description": "Retrieve the generated 16-week trade plan and expected portfolio path.",
        "inputSchema": {
            "type": "object",
            "properties": {"simulation_id": {"type": "string"}},
            "required": ["simulation_id"],
        },
    },
    {
        "name": "run-what-if-analysis",
        "gateway": "portfolio-planning",
        "description": "Analyze liquidity, adherence, or forecast-shock impact on a 16-week plan.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "simulation_id": {"type": "string"},
                "cash_available": {"type": "number"},
                "forecast_shock_pct": {"type": "number"},
                "missed_trade_symbols": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["simulation_id"],
        },
    },
    {
        "name": "explain-trade-plan",
        "gateway": "portfolio-planning",
        "description": "Explain why the dummy optimizer suggests each buy/sell action.",
        "inputSchema": {
            "type": "object",
            "properties": {"simulation_id": {"type": "string"}},
            "required": ["simulation_id"],
        },
    },
    {
        "name": "record-weekly-review",
        "gateway": "portfolio-planning",
        "description": "Record a weekly review snapshot and adherence notes for the current plan.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "simulation_id": {"type": "string"},
                "week": {"type": "integer"},
                "actual_cash": {"type": "number"},
                "actual_value": {"type": "number"},
                "notes": {"type": "string"},
            },
            "required": ["simulation_id", "week"],
        },
    },
    {
        "name": "generate-weekly-plan-report",
        "gateway": "portfolio-planning",
        "description": "Generate a weekly report summarizing the next 16 weeks and deviations from the prior plan.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "simulation_id": {"type": "string"},
                "previous_simulation_id": {"type": "string"},
                "week": {"type": "integer"},
            },
            "required": ["simulation_id"],
        },
    },
]


def _table():
    name = os.environ.get("STATE_TABLE_NAME")
    if not name or boto3 is None:
        return None
    return boto3.resource("dynamodb").Table(name)


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(_json_safe(body)),
    }


def _agentcore_context_tool_name(context: Any) -> str:
    client_context = getattr(context, "client_context", None)
    custom = getattr(client_context, "custom", None) if client_context is not None else None
    if not isinstance(custom, dict):
        return ""
    return str(custom.get("bedrockAgentCoreToolName") or "")


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _stable_id(prefix: str, payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _put_state(item: dict[str, Any]) -> None:
    table = _table()
    if table is None:
        return
    ttl = int(time.time()) + 30 * 24 * 60 * 60
    table.put_item(Item=json.loads(json.dumps({**item, "ttl": ttl, "updatedAt": int(time.time())}), parse_float=Decimal))


def _get_state(item_id: str) -> dict[str, Any] | None:
    table = _table()
    if table is None:
        return None
    try:
        result = table.get_item(Key={"id": item_id})
    except ClientError:
        return None
    item = result.get("Item")
    return _json_safe(item) if item else None


def _symbols(value: Any) -> list[str]:
    if isinstance(value, str):
        items = [item.strip().upper() for item in value.split(",")]
    elif isinstance(value, list):
        items = [str(item).strip().upper() for item in value]
    else:
        items = list(STOCKS)
    return [item for item in items if item in STOCKS] or list(STOCKS)


def _portfolio_id(args: dict[str, Any]) -> str:
    return str(args.get("portfolio_id") or "demo-growth-income").strip() or "demo-growth-income"


def _round(value: float) -> float:
    return round(float(value), 2)


def _snapshot(portfolio_id: str = "demo-growth-income", cash: float = DEFAULT_CASH) -> dict[str, Any]:
    positions = []
    for symbol, quantity in BASE_HOLDINGS.items():
        stock = STOCKS[symbol]
        value = quantity * stock["price"]
        positions.append(
            {
                "symbol": symbol,
                "quantity": quantity,
                "price": stock["price"],
                "marketValue": _round(value),
                "sector": stock["sector"],
                "expectedReturn": stock["expected_return"],
                "risk": stock["risk"],
                "dailyContext": _daily_context(symbol),
            }
        )
    invested = sum(item["marketValue"] for item in positions)
    return {
        "portfolioId": portfolio_id,
        "asOf": "synthetic-today",
        "cash": _round(cash),
        "positions": positions,
        "totalValue": _round(invested + cash),
        "assumption": "Prices, news, and holdings are synthetic placeholders until the daily financial-data pipeline is connected.",
    }


def _daily_context(symbol: str) -> str:
    stock = STOCKS[symbol]
    if stock["signal"] == "positive":
        return f"{symbol} has positive synthetic momentum with supportive daily news sentiment."
    if stock["signal"] == "defensive":
        return f"{symbol} is modeled as a defensive stabilizer with lower expected volatility."
    return f"{symbol} has neutral synthetic context; planner treats it as a diversification holding."


def _target_weight(stock: dict[str, Any], risk_target: str) -> float:
    score = stock["expected_return"] / max(stock["risk"], 0.01)
    if risk_target == "conservative":
        score *= 0.7 if stock["risk"] > 0.18 else 1.3
    elif risk_target == "growth":
        score *= 1.35 if stock["expected_return"] >= 0.10 else 0.75
    return score


def _build_trade_plan(
    portfolio_id: str,
    risk_target: str,
    cash_available: float,
    max_trade_value_per_week: float,
) -> dict[str, Any]:
    snapshot = _snapshot(portfolio_id, cash_available)
    total_value = snapshot["totalValue"]
    scores = {symbol: _target_weight(stock, risk_target) for symbol, stock in STOCKS.items()}
    score_total = sum(scores.values())
    current_values = {pos["symbol"]: pos["marketValue"] for pos in snapshot["positions"]}
    trades = []

    for symbol, score in sorted(scores.items(), key=lambda item: item[1], reverse=True):
        target_value = total_value * score / score_total
        delta = target_value - current_values.get(symbol, 0)
        if abs(delta) < 800:
            continue
        weekly_value = max(-max_trade_value_per_week, min(max_trade_value_per_week, delta / 4))
        action = "BUY" if weekly_value > 0 else "SELL"
        quantity = max(1, round(abs(weekly_value) / STOCKS[symbol]["price"]))
        trades.append(
            {
                "symbol": symbol,
                "action": action,
                "weeklyQuantity": quantity,
                "weeklyTradeValue": _round(quantity * STOCKS[symbol]["price"]),
                "reason": _trade_reason(symbol, action, risk_target),
            }
        )

    if not trades:
        trades.append(
            {
                "symbol": "MSFT",
                "action": "BUY",
                "weeklyQuantity": 1,
                "weeklyTradeValue": STOCKS["MSFT"]["price"],
                "reason": "Maintains the demo plan with a small high-quality technology allocation.",
            }
        )

    weeks = []
    value = total_value
    expected_weekly_return = {"conservative": 0.0025, "moderate": 0.004, "growth": 0.006}[risk_target]
    for week in range(1, 17):
        week_trades = [trade for index, trade in enumerate(trades) if index % 4 == (week - 1) % 4]
        net_cash_use = sum(
            trade["weeklyTradeValue"] if trade["action"] == "BUY" else -trade["weeklyTradeValue"]
            for trade in week_trades
        )
        value = value * (1 + expected_weekly_return)
        weeks.append(
            {
                "week": week,
                "targetPortfolioValue": _round(value),
                "plannedTrades": week_trades,
                "netCashUse": _round(net_cash_use),
                "reviewFocus": _review_focus(week),
            }
        )
    return {
        "portfolioId": portfolio_id,
        "riskTarget": risk_target,
        "startingValue": total_value,
        "expectedValueAtWeek16": weeks[-1]["targetPortfolioValue"],
        "expectedReturnPct16w": _round((weeks[-1]["targetPortfolioValue"] / total_value - 1) * 100),
        "weeks": weeks,
        "tradeRationale": trades,
    }


def _trade_reason(symbol: str, action: str, risk_target: str) -> str:
    stock = STOCKS[symbol]
    if action == "BUY":
        return (
            f"{symbol} scores well for {risk_target} planning because expected return is "
            f"{stock['expected_return']:.0%} with {stock['signal']} synthetic context."
        )
    return (
        f"{symbol} is reduced to free liquidity or rebalance sector exposure under the "
        f"{risk_target} risk target."
    )


def _review_focus(week: int) -> str:
    if week == 1:
        return "Confirm cash availability and execute only the first tranche."
    if week % 4 == 0:
        return "Monthly review: compare realized value against expected path and rerun if forecast error is material."
    return "Check adherence, liquidity, and whether daily market context changed the thesis."


def health_check() -> dict[str, Any]:
    return {
        "status": True,
        "stage": os.environ.get("STAGE", "unknown"),
        "runtime": "lambda",
        "gateways": ["portfolio-planning"],
        "toolCount": len(TOOL_CATALOG),
    }


def list_gateways() -> dict[str, Any]:
    return {
        "gateways": [
            {
                "id": "portfolio-planning",
                "name": "Portfolio Planning",
                "description": "Synthetic portfolio optimization, what-if analysis, and weekly plan review tools.",
                "mcpUrl": "local://portfolio-planning",
                "authType": "iam-proxy",
                "sigv4Region": os.environ.get("AWS_REGION", "us-west-2"),
                "sigv4Service": "execute-api",
            }
        ]
    }


def list_tools(gateway: str | None = None) -> dict[str, Any]:
    tools = [tool for tool in TOOL_CATALOG if not gateway or tool["gateway"] == gateway]
    return {"tools": tools, "gateway": gateway or "all"}


def list_portfolios() -> dict[str, Any]:
    return {
        "portfolios": [
            {
                "portfolioId": "demo-growth-income",
                "name": "Demo Growth Income Portfolio",
                "baseCurrency": "USD",
                "planningHorizonWeeks": 16,
            }
        ]
    }


def get_market_context(args: dict[str, Any]) -> dict[str, Any]:
    symbols = _symbols(args.get("symbols"))
    return {
        "asOf": "synthetic-today",
        "items": [
            {
                "symbol": symbol,
                "sector": STOCKS[symbol]["sector"],
                "signal": STOCKS[symbol]["signal"],
                "expectedReturn": STOCKS[symbol]["expected_return"],
                "risk": STOCKS[symbol]["risk"],
                "summary": _daily_context(symbol),
            }
            for symbol in symbols
        ],
    }


def run_optimization(args: dict[str, Any]) -> dict[str, Any]:
    portfolio_id = _portfolio_id(args)
    risk_target = str(args.get("risk_target") or DEFAULT_RISK_TARGET).lower()
    if risk_target not in {"conservative", "moderate", "growth"}:
        raise ValueError("risk_target must be conservative, moderate, or growth")
    cash_available = float(args.get("cash_available") or DEFAULT_CASH)
    max_trade_value = float(args.get("max_trade_value_per_week") or 7_500.0)
    plan = _build_trade_plan(portfolio_id, risk_target, cash_available, max_trade_value)
    simulation_id = _stable_id(
        "portfolio-plan",
        {
            "portfolio_id": portfolio_id,
            "risk_target": risk_target,
            "cash_available": cash_available,
            "max_trade_value": max_trade_value,
            "version": "dummy-v1",
        },
    )
    item = {
        "id": simulation_id,
        "type": "portfolio-optimization",
        "status": "COMPLETED",
        "createdAt": int(time.time()),
        "inputs": {
            "portfolioId": portfolio_id,
            "riskTarget": risk_target,
            "cashAvailable": cash_available,
            "maxTradeValuePerWeek": max_trade_value,
        },
        "plan": plan,
    }
    _put_state(item)
    return {
        "simulation_id": simulation_id,
        "status": "COMPLETED",
        "summary": {
            "portfolioId": portfolio_id,
            "riskTarget": risk_target,
            "expectedReturnPct16w": plan["expectedReturnPct16w"],
            "expectedValueAtWeek16": plan["expectedValueAtWeek16"],
        },
        "nextStep": "Call get-simulation-results, explain-trade-plan, or generate-weekly-plan-report.",
    }


def _require_simulation(args: dict[str, Any]) -> dict[str, Any]:
    simulation_id = str(args.get("simulation_id") or "").strip()
    if not simulation_id:
        raise ValueError("simulation_id is required")
    state = _get_state(simulation_id)
    if state:
        return state
    return run_optimization({"portfolio_id": "demo-growth-income", "risk_target": DEFAULT_RISK_TARGET})


def get_simulation_status(args: dict[str, Any]) -> dict[str, Any]:
    state = _require_simulation(args)
    return {
        "simulation_id": state.get("id") or state.get("simulation_id"),
        "status": state.get("status", "COMPLETED"),
        "createdAt": state.get("createdAt"),
        "inputs": state.get("inputs", {}),
    }


def get_simulation_results(args: dict[str, Any]) -> dict[str, Any]:
    state = _require_simulation(args)
    return {
        "simulation_id": state.get("id") or args.get("simulation_id"),
        "status": state.get("status", "COMPLETED"),
        "plan": state.get("plan", {}),
    }


def run_what_if(args: dict[str, Any]) -> dict[str, Any]:
    state = _require_simulation(args)
    plan = state.get("plan", {})
    expected_value = float(plan.get("expectedValueAtWeek16", plan.get("startingValue", 0)))
    cash_available = float(args.get("cash_available") or state.get("inputs", {}).get("cashAvailable", DEFAULT_CASH))
    forecast_shock_pct = float(args.get("forecast_shock_pct") or 0)
    missed = _symbols(args.get("missed_trade_symbols")) if args.get("missed_trade_symbols") else []
    adjusted_value = expected_value * (1 + forecast_shock_pct / 100)
    liquidity_gap = max(0.0, 5_000.0 - cash_available)
    return {
        "simulation_id": state.get("id"),
        "scenario": {
            "cashAvailable": _round(cash_available),
            "forecastShockPct": forecast_shock_pct,
            "missedTradeSymbols": missed,
        },
        "impact": {
            "adjustedExpectedValueAtWeek16": _round(adjusted_value),
            "valueDeltaVsPlan": _round(adjusted_value - expected_value),
            "liquidityGap": _round(liquidity_gap),
            "adherenceRisk": "HIGH" if liquidity_gap > 0 or len(missed) >= 3 else "MEDIUM" if missed else "LOW",
        },
        "recommendation": "Rerun optimization if liquidity gap or forecast error persists for two weekly reviews.",
    }


def explain_trade_plan(args: dict[str, Any]) -> dict[str, Any]:
    state = _require_simulation(args)
    plan = state.get("plan", {})
    return {
        "simulation_id": state.get("id"),
        "explanation": [
            "The dummy optimizer scores each stock using expected return divided by risk.",
            "Risk target changes the score: conservative favors lower volatility, growth favors higher expected return.",
            "Trades are spread over 16 weeks to reduce liquidity pressure and allow weekly re-planning.",
        ],
        "tradeRationale": plan.get("tradeRationale", []),
        "limitations": [
            "This is synthetic template logic, not financial advice.",
            "The future math-model pipeline should replace this Lambda handler with an MCP-exposed optimizer.",
        ],
    }


def record_weekly_review(args: dict[str, Any]) -> dict[str, Any]:
    state = _require_simulation(args)
    week = int(args.get("week") or 1)
    review_id = _stable_id("review", {"simulation_id": state.get("id"), "week": week, "notes": args.get("notes", "")})
    review = {
        "id": review_id,
        "type": "weekly-review",
        "simulationId": state.get("id"),
        "week": week,
        "actualCash": _round(float(args.get("actual_cash") or DEFAULT_CASH)),
        "actualValue": _round(float(args.get("actual_value") or state.get("plan", {}).get("startingValue", 0))),
        "notes": str(args.get("notes") or ""),
        "status": "RECORDED",
    }
    _put_state(review)
    return review


def generate_weekly_report(args: dict[str, Any]) -> dict[str, Any]:
    state = _require_simulation(args)
    plan = state.get("plan", {})
    week = int(args.get("week") or 1)
    remaining_weeks = [item for item in plan.get("weeks", []) if int(item.get("week", 0)) >= week]
    previous_id = str(args.get("previous_simulation_id") or "").strip()
    deviation = "No previous plan was provided."
    if previous_id:
        previous = _get_state(previous_id)
        if previous:
            prev_value = float(previous.get("plan", {}).get("expectedValueAtWeek16", 0))
            current_value = float(plan.get("expectedValueAtWeek16", 0))
            deviation = f"Current week-16 expected value differs from previous plan by ${_round(current_value - prev_value):,.2f}."
        else:
            deviation = "Previous plan id was provided but not found in synthetic state."
    return {
        "simulation_id": state.get("id"),
        "week": week,
        "title": f"Weekly Portfolio Plan Review - Week {week}",
        "summary": {
            "portfolioId": plan.get("portfolioId"),
            "riskTarget": plan.get("riskTarget"),
            "expectedReturnPct16w": plan.get("expectedReturnPct16w"),
            "expectedValueAtWeek16": plan.get("expectedValueAtWeek16"),
            "deviationFromPreviousPlan": deviation,
        },
        "next16WeekPlan": remaining_weeks[:16],
        "watchItems": [
            "Liquidity available for the next tranche of buy orders.",
            "Forecast drift versus actual portfolio value.",
            "Symbols with changed daily context from the financial-data table.",
        ],
        "disclaimer": "Synthetic template output for workflow and UX validation only; not financial advice.",
    }


TOOL_HANDLERS = {
    "healthCheck": lambda args: health_check(),
    "listGateways": lambda args: list_gateways(),
    "listTools": lambda args: list_tools(args.get("gateway")),
    "list-portfolios": lambda args: list_portfolios(),
    "get-portfolio-snapshot": lambda args: _snapshot(_portfolio_id(args), float(args.get("cash") or DEFAULT_CASH)),
    "get-market-context": get_market_context,
    "run-portfolio-optimization": run_optimization,
    "get-simulation-status": get_simulation_status,
    "get-simulation-results": get_simulation_results,
    "run-what-if-analysis": run_what_if,
    "explain-trade-plan": explain_trade_plan,
    "record-weekly-review": record_weekly_review,
    "generate-weekly-plan-report": generate_weekly_report,
}


def _normalize_tool_name(tool_name: str) -> str:
    name = str(tool_name or "").strip()
    if name in TOOL_HANDLERS:
        return name
    for delimiter in ("___", "__"):
        if delimiter in name:
            candidate = name.split(delimiter, 1)[1]
            if candidate in TOOL_HANDLERS:
                return candidate
    for known in TOOL_HANDLERS:
        if name.endswith(known):
            return known
    return name


def invoke_tool(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_tool_name(tool_name)
    handler = TOOL_HANDLERS.get(normalized)
    if handler is None:
        raise ValueError(f"unknown tool: {tool_name}")
    return handler(args)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    try:
        gateway_tool_name = _agentcore_context_tool_name(context)
        if gateway_tool_name:
            return _json_safe(invoke_tool(gateway_tool_name, event))

        tool_name = event.get("tool") or event.get("name")
        args = event.get("arguments") or event.get("args") or {}
        if not tool_name:
            return _response(400, {"error": "tool is required"})
        return _response(200, invoke_tool(str(tool_name), args))
    except Exception as exc:
        if _agentcore_context_tool_name(context):
            return {"error": str(exc)}
        return _response(400, {"error": str(exc)})
