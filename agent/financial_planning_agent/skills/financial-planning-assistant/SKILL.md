---
name: financial-planning-assistant
description: Standard operating procedure for portfolio optimization, weekly plan review, and financial planning explanation. Use when the user asks about portfolio planning, buy/sell plans, weekly review, liquidity constraints, or forecast deviations.
allowed-tools:
  - portfolio-planning___list-portfolios
  - portfolio-planning___get-portfolio-snapshot
  - portfolio-planning___get-market-context
  - portfolio-planning___run-portfolio-optimization
  - portfolio-planning___get-simulation-status
  - portfolio-planning___get-simulation-results
  - portfolio-planning___run-what-if-analysis
  - portfolio-planning___explain-trade-plan
  - portfolio-planning___record-weekly-review
  - portfolio-planning___generate-weekly-plan-report
  - portfolio-planning___get_model_input
  - portfolio-planning___get_model_output
  - portfolio-planning___override_input
  - portfolio-planning___get_model_formulation
  - portfolio-planning___run_math_model
  - portfolio-planning___override
---

# Financial Planning Assistant

Use this skill to help with synthetic portfolio planning workflows.

## Rules

- Always state that the current data and optimizer are synthetic template logic, not financial advice.
- Ask for missing risk target, available liquidity, or portfolio identifier before running an optimization.
- Use a 16-week planning horizon.
- Prefer tool outputs over guessing.
- Review liquidity, adherence, and forecast drift every week.
- If the user asks what to buy or sell, run or retrieve an optimization before explaining trade rationale.
- If the user asks why the plan changed, compare the current simulation with the previous simulation or weekly review data.

## Tool Routing

- Use `list-portfolios` to discover available portfolios.
- Use `get-portfolio-snapshot` before an optimization or explanation.
- Use `get-market-context` when explaining symbol-level recommendations.
- Use `run-portfolio-optimization` to create the 16-week buy/sell plan.
- Use `get-simulation-results` to retrieve the detailed plan.
- Use `run-what-if-analysis` for liquidity limits, missed trades, or forecast shocks.
- Use `explain-trade-plan` to explain buy/sell rationale.
- Use `record-weekly-review` to capture adherence observations.
- Use `generate-weekly-plan-report` for the weekly summary.
- Use `get_model_input` to inspect the exact input used for a model run.
- Use `get_model_output` to inspect the raw optimizer output for a model run.
- Use `get_model_formulation` to explain the optimization objective, variables, constraints, and outputs.
- Use `override_input` to create an adjusted input payload before rerunning the model.
- Use `run_math_model` to execute the optimizer from an existing or overridden input payload.
- Use `override` to record a governed manual override decision with a justification.

## Optimization Flow

1. Confirm portfolio, risk target, and available cash.
2. Get the portfolio snapshot.
3. Get relevant market context.
4. Run the optimization or run the math model from an existing input.
5. Retrieve model input, model output, and formulation when the user asks why the plan was generated.
6. Explain the plan.
7. Present the next actions by week, highlighting week 1 separately.

## Model Override Flow

1. Ask what input should be changed and why.
2. Retrieve the current model input with `get_model_input`.
3. Create a new input with `override_input`.
4. Record the human justification with `override`.
5. Run the math model with `run_math_model`.
6. Compare the new output with the previous output and explain the business impact.

## Weekly Review Flow

1. Ask for the current simulation id, week number, actual cash, and actual portfolio value.
2. Record the weekly review.
3. Run what-if analysis if liquidity or adherence is off-plan.
4. Generate the weekly report.
5. Explain whether deviations are due to liquidity, missed trades, forecast drift, or market context.
