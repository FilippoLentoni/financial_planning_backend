# Financial Planning Backend

Public AWS CDK template for a Strands financial planning assistant deployed on Amazon Bedrock AgentCore Runtime.

This template assumes a future daily financial-data pipeline will populate portfolio, stock, forecast, and market-context data in DynamoDB or another public AWS data store. For now, the backend includes a cost-safe synthetic tool Lambda so teams can validate skills, gateway behavior, and UX before building the real math-model pipeline.

## What It Deploys

- Bedrock AgentCore Runtime running a Strands agent with Nova 2 Lite by default.
- Bedrock AgentCore Gateway with an IAM-protected MCP endpoint.
- AgentCore Gateway Lambda target exposing the portfolio-planning tool catalog.
- IAM-protected API Gateway endpoint for runtime invocation.
- IAM-protected gateway discovery endpoint: `/gateways/iam`.
- IAM-protected MCP-compatible proxy endpoint: `/mcp/proxy`.
- IAM-protected model-run ledger endpoint: `/planning/runs`.
- Lambda-backed dummy math-model control tools.
- DynamoDB state table for short-lived synthetic model inputs, model runs, and override records.
- EventBridge Monday seed rule that simulates the future data pipeline creating a model input and run.
- CDK Pipeline for alpha, gamma, and prod stages.

## Gateway And Tools

| Gateway | Tools |
| --- | --- |
| `portfolio-planning` | `portfolio-planning___get_math_model_input`, `portfolio-planning___get_math_model_output`, `portfolio-planning___override_math_model_input`, `portfolio-planning___get_math_model_formulation`, `portfolio-planning___run_math_model`, `portfolio-planning___override_math_model` |

The current dummy optimizer generates a 16-week buy/sell plan from synthetic holdings, prices, expected returns, risk scores, and liquidity constraints. It is intentionally lightweight and deterministic. It is not financial advice.

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
- `snapshot`: synthetic holdings, cash, prices, and portfolio value.
- `marketContext`: synthetic daily market/news context for tracked symbols.
- `constraints`: synthetic optimizer constraints such as no short selling and weekly trade limits.

**Output** means the optimizer result for a run. In this template it contains:

- `run_id`: stable id for the model run.
- `input_id`: input payload used by the run.
- `solverStatus`: synthetic solver status, currently `OPTIMAL`.
- `objectiveValue`: expected value at week 16 from the dummy objective.
- `plan`: 16-week buy/sell plan, expected value path, trade rationale, and liquidity usage.
- `formulationVersion`: version of the dummy formulation.

The minimum model-control tools are:

- `get_math_model_input(run_id | input_id)`: inspect the input used by a run, or retrieve a model input directly from the `input_id` shown in the UI.
- `get_math_model_output(run_id | input_id)`: inspect raw optimizer output by run, or retrieve the latest output for the `input_id` shown in the UI.
- `override_math_model_input(input_id)`: create a new input by applying synthetic overrides.
- `get_math_model_formulation(run_id)`: inspect objective, variables, constraints, and outputs.
- `run_math_model(input_id)`: run the dummy optimizer from an existing input.
- `override_math_model(input_id, justification)`: record a governed human override decision.

For template-only smoke tests, use `demo-model-input` as a safe synthetic `input_id`.

## Weekly Planning Lifecycle

The intended operating model is:

1. Every Monday, the financial-data pipeline refreshes market data and creates a model input with a new `input_id`.
2. After the input is saved, the backend triggers `run_math_model(input_id)` and stores a new run with a `run_id`.
3. The UI reads `GET /planning/runs` to show the latest `input_id`, `run_id`, timestamp, portfolio, risk target, source, model id, and high-level result metadata.
4. The user can ask the chatbot to inspect input, output, formulation, and overrides by passing `input_id` or `run_id`.
5. If the user overrides an input, `override_math_model_input(input_id)` saves a new `model-input` record with a new `input_id` and `sourceInputId`.
6. If the user records a governed override decision, `override_math_model(input_id, justification)` saves a `model-input-override` record.

Until the real data pipeline exists, the template deploys an EventBridge rule named `WeeklyDataPipelineSeedRule`. It runs every Monday at 13:00 UTC and creates a synthetic input/run pair. The same behavior is also available by calling `POST /planning/runs` for smoke tests.

The DynamoDB state table stores typed records:

| Record type | Purpose |
| --- | --- |
| `model-input` | Optimizer input payload, including source, as-of date, snapshot, constraints, and market context. |
| `portfolio-optimization` | Optimizer run/output payload, including `run_id`, `input_id`, `modelUsed`, solver status, and the 16-week plan. |
| `model-input-override` | Governed human override decision with justification. |

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

Step 2 should move the portfolio math model into a dedicated package/pipeline and expose it through MCP. At that point, replace the dummy `run_math_model` Lambda handler with an MCP-backed optimizer target while keeping the same six-tool gateway contract.

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
