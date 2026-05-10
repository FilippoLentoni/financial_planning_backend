# Financial Planning Backend

Public AWS CDK template for a Strands financial planning assistant deployed on Amazon Bedrock AgentCore Runtime.

This template assumes a future daily financial-data pipeline will populate portfolio, stock, forecast, and market-context data in DynamoDB or another public AWS data store. For now, the backend includes a cost-safe synthetic tool Lambda so teams can validate skills, gateway behavior, and UX before building the real math-model pipeline.

## What It Deploys

- Bedrock AgentCore Runtime running a Strands agent with Nova 2 Lite by default.
- IAM-protected API Gateway endpoint for runtime invocation.
- IAM-protected gateway discovery endpoint: `/gateways/iam`.
- IAM-protected MCP-compatible proxy endpoint: `/mcp/proxy`.
- Lambda-backed dummy portfolio planning tools.
- DynamoDB state table for short-lived synthetic simulations and weekly reviews.
- CDK Pipeline for alpha, gamma, and prod stages.

## Gateway And Tools

| Gateway | Tools |
| --- | --- |
| `portfolio-planning` | `list-portfolios`, `get-portfolio-snapshot`, `get-market-context`, `run-portfolio-optimization`, `get-simulation-status`, `get-simulation-results`, `run-what-if-analysis`, `explain-trade-plan`, `record-weekly-review`, `generate-weekly-plan-report` |

The current dummy optimizer generates a 16-week buy/sell plan from synthetic holdings, prices, expected returns, risk scores, and liquidity constraints. It is intentionally lightweight and deterministic. It is not financial advice.

## What Should Be A Tool Vs A Skill

Use **tools** for deterministic actions or data access:

- Read portfolio snapshot from the future daily DynamoDB table.
- Read stock/market context for a date.
- Run the portfolio optimizer.
- Retrieve simulation status/results.
- Run what-if analysis for liquidity, forecast shocks, or missed trades.
- Record weekly review observations.
- Generate the structured weekly report payload.

Use **agent skills / prompts** for reasoning and orchestration:

- Ask clarifying questions about risk target, liquidity, and constraints.
- Decide which tools to call and in what order.
- Explain why the optimizer recommends buy/sell actions.
- Compare the current plan with the previous plan.
- Summarize why the plan deviated: liquidity issue, forecast error, market-context change, or adherence problem.
- Produce a human-readable weekly report from tool outputs.

## Future MCP Model Pipeline

Step 2 should move the portfolio math model into a dedicated package/pipeline and expose it through MCP. At that point, replace or extend the dummy `run-portfolio-optimization` Lambda handler with an MCP-backed optimizer target while keeping the same gateway/tool contract.

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
