# Financial Planning Backend

Public AWS CDK template for a Strands financial planning assistant deployed on Amazon Bedrock AgentCore Runtime.

This template includes a first-pass market-data pipeline that uses `yfinance` to populate stock OHLCV-derived features in DynamoDB. The math model is still a lightweight template optimizer, but its inputs can now use market prices, annualized return estimates, volatility estimates, and volume derived from yfinance rather than only hardcoded synthetic stock values.

## What It Deploys

- Bedrock AgentCore Runtime running a Strands agent with Nova 2 Lite by default.
- Bedrock AgentCore Gateway with an IAM-protected MCP endpoint.
- AgentCore Gateway Lambda target exposing the portfolio-planning tool catalog.
- IAM-protected API Gateway endpoint for runtime invocation.
- IAM-protected gateway discovery endpoint: `/gateways/iam`.
- IAM-protected MCP-compatible proxy endpoint: `/mcp/proxy`.
- IAM-protected model-run ledger endpoint: `/planning/runs`.
- Lambda-backed dummy math-model control tools.
- DynamoDB state table for market-data snapshots, model inputs, model runs, and override records.
- EventBridge market-data rule that refreshes yfinance data after market close and creates a model input/run.
- CDK Pipeline for alpha, gamma, and prod stages.

## Gateway And Tools

| Gateway | Tools |
| --- | --- |
| `portfolio-planning` | `portfolio-planning___hello_world`, `portfolio-planning___get_math_model_input`, `portfolio-planning___get_math_model_output`, `portfolio-planning___override_math_model_input`, `portfolio-planning___get_math_model_formulation`, `portfolio-planning___trigger_math_model`, `portfolio-planning___get_math_model_status`, `portfolio-planning___override_math_model` |

The current dummy optimizer generates a 16-week buy/sell plan from holdings, prices, expected returns, risk scores, and liquidity constraints. When the yfinance pipeline has run, prices/risk/return features come from yfinance OHLCV history. Holdings, cash, constraints, and the optimizer itself are still template logic. It is not financial advice.

The backend uses one AgentCore Gateway per bounded business domain. The `portfolio-planning` Lambda target exposes multiple tools through a single MCP endpoint. That is the preferred default for a cohesive tool set because Gateway is designed to compose multiple targets and tools into one MCP server. Split into additional gateways only when security boundaries, ownership, deployment cadence, or scaling needs are materially different.

AgentCore prefixes Lambda-target tool names with the target name. For this target, tools are discovered as `portfolio-planning___<tool-name>`.

## Model Input And Output Contract

The portfolio optimizer is modeled as an input/output workflow so the agent can inspect, override_math_model, rerun, and explain the math model.

**Input** means the complete payload sent to the optimizer. In this template it contains:

- `input_id`: stable id for the model input payload.
- `portfolioId`: portfolio being optimized.
- `riskTarget`: `conservative`, `moderate`, or `growth`.
- `cashAvailable`: liquidity available for the 16-week plan.
- `maxTradeValuePerWeek`: weekly trading limit.
- `planningHorizonWeeks`: fixed at `16`.
- `snapshot`: holdings, cash, prices, and portfolio value. Prices come from yfinance when the market-data pipeline has run.
- `marketContext`: yfinance OHLCV-derived return/risk/volume context for tracked symbols. News sentiment is not connected yet.
- `constraints`: optimizer constraints such as no short selling and weekly trade limits.

**Output** means the optimizer result for a run. In this template it contains:

- `run_id`: stable id for the model run.
- `input_id`: input payload used by the run.
- `status`: run lifecycle status, currently `COMPLETED` for the in-process template optimizer.
- `outputReady`: whether the model output can be retrieved.
- `solverStatus`: synthetic solver status, currently `OPTIMAL`.
- `objectiveValue`: expected value at week 16 from the dummy objective.
- `plan`: 16-week buy/sell plan, expected value path, trade rationale, and liquidity usage.
- `formulationVersion`: version of the dummy formulation.

The minimum model-control tools are:

- `get_math_model_input(run_id | input_id)`: inspect the input used by a run, or retrieve a model input directly from the `input_id` shown in the UI.
- `get_math_model_output(run_id | input_id)`: inspect raw optimizer output by run, or retrieve the latest output for the `input_id` shown in the UI.
- `override_math_model_input(input_id)`: create a new input by applying synthetic overrides.
- `get_math_model_formulation(run_id)`: inspect objective, variables, constraints, and outputs.
- `trigger_math_model(input_id)`: trigger the dummy optimizer from an existing input and return a `run_id`.
- `get_math_model_status(run_id)`: check whether the run has completed before retrieving output.
- `override_math_model(input_id, justification)`: record a governed human override decision.

For template-only smoke tests, use `demo-model-input` as a safe synthetic `input_id`. For market-data smoke tests, call `createMarketDataModelRun` or `POST /planning/runs` with `{"source":"yfinance-market-data"}`.

## Market Data Pipeline

The backend deploys an EventBridge rule named `MarketDataPipelineRule`. It runs Monday through Friday at 23:00 UTC, after the US market close, and invokes the tool Lambda with `source=financial-planning.market-data-pipeline`.

The Lambda uses `yfinance` to retrieve daily OHLCV history for the configured ticker universe:

```text
AAPL, MSFT, AMZN, NVDA, JPM, JNJ, XOM, V
```

For each symbol, it stores a typed DynamoDB `market-data` item with:

- `symbol`
- `provider`: `yfinance`
- latest close price
- annualized expected return from daily close-to-close returns
- annualized volatility/risk from daily returns
- average daily volume
- observation count
- sector placeholder
- source summary

It also stores a `market-data-batch` item for the run, then creates a `model-input` item with `source=yfinance-market-data`, and finally runs `trigger_math_model(input_id)` to create a `portfolio-optimization` output.

`yfinance` is excellent for prototyping and demos, but it is not a production market-data SLA. The provider boundary is intentionally isolated so a paid provider such as Polygon, Tiingo, Finnhub, or Bloomberg/FactSet can replace it later without changing the agent tools or model input/output contract.

## Weekly Planning Lifecycle

The intended operating model is:

1. Every scheduled market-data run refreshes yfinance market data and creates a model input with a new `input_id`.
2. After the input is saved, the backend triggers `trigger_math_model(input_id)` and stores a new run with a `run_id`.
3. The UI reads `GET /planning/runs` to show the latest `input_id`, `run_id`, status, timestamp, portfolio, risk target, source, model id, and high-level result metadata.
4. The user can ask the chatbot to check status, inspect input, inspect output, inspect formulation, and record overrides by passing `input_id` or `run_id`.
5. If the user overrides an input, `override_math_model_input(input_id)` saves a new `model-input` record with a new `input_id` and `sourceInputId`.
6. If the user records a governed override decision, `override_math_model(input_id, justification)` saves a `model-input-override` record.

The same behavior is also available by calling `POST /planning/runs` with `{"source":"yfinance-market-data"}` for smoke tests.

The DynamoDB state table stores typed records:

| Record type | Purpose |
| --- | --- |
| `model-input` | Optimizer input payload, including source, as-of date, snapshot, constraints, and market context. |
| `portfolio-optimization` | Optimizer run/output payload, including `run_id`, `input_id`, `modelUsed`, solver status, and the 16-week plan. |
| `model-input-override` | Governed human override decision with justification. |
| `market-data` | Per-symbol yfinance-derived market features. |
| `market-data-batch` | Batch metadata for one market-data retrieval run. |

The template uses a single table for the golden path because these records are accessed together by `input_id` and `run_id`. A production system can split them into separate tables if ownership, retention, or throughput boundaries require it.

## What Should Be A Tool Vs A Skill

Use **tools** for deterministic actions or data access:

- Retrieve model input and output payloads.
- Retrieve the math-model formulation.
- Create overridden input payloads.
- Run the portfolio optimizer from an input id.
- Record governed override decisions.

Use **agent skills / prompts** for reasoning and orchestration:

- Ask clarifying questions about `run_id`, `input_id`, liquidity, constraints, and override justification.
- Decide which tools to call and in what order.
- Explain why the optimizer recommends buy/sell actions.
- Compare the current model run with the previous run.
- Summarize why the plan deviated: liquidity issue, forecast error, market-context change, or adherence problem.
- Produce a human-readable weekly planning narrative from model inputs and outputs.

## Future MCP Model Pipeline

Step 2 should move the portfolio math model into a dedicated package/pipeline and expose it through MCP. At that point, replace the dummy `trigger_math_model` Lambda handler with an MCP-backed optimizer target while keeping the same seven-tool gateway contract.

## Manual Setup For A Real Project

Before deploying this template as a project, create:

1. A GitHub repo for the backend package.
2. An AWS CodeConnections connection to that repo.
3. `SOURCE_REPO`, `SOURCE_BRANCH`, and `CODESTAR_CONNECTION_ARN`.
4. Target account/region values for personal, alpha, gamma, and prod.
5. Bedrock model access for `us.amazon.nova-2-lite-v1:0` or your chosen model.

## Local Validation

```bash
npm install
npm test
npm run synth -- FinancialPlanningBackend-PersonalStack
```

## Personal Deploy

```bash
AWS_PROFILE=<profile> npm run deploy:personal -- --require-approval never
```

Personal deploy is for pre-PR testing. Alpha/gamma/prod should flow through GitHub review and CDK Pipelines.

## Pipeline Deploy

```bash
export SOURCE_REPO=owner/repo
export SOURCE_BRANCH=main
export CODESTAR_CONNECTION_ARN=arn:aws:codeconnections:...

AWS_PROFILE=<profile> npm run deploy:pipeline -- --require-approval never
```
