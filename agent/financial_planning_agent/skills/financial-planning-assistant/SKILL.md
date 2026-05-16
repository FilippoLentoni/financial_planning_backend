---
name: financial-planning-assistant
description: Standard operating procedure for portfolio optimization, weekly plan review, and financial planning explanation. Use when the user asks about portfolio planning, buy/sell plans, weekly review, liquidity constraints, or forecast deviations.
allowed-tools:
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
- Ask for missing `run_id`, `input_id`, override details, or override justification before calling model tools.
- Use a 16-week planning horizon.
- Prefer tool outputs over guessing.
- Review liquidity, adherence, and forecast drift every week.
- If the user asks what to buy or sell, retrieve the model output or run the math model before explaining trade rationale.
- If the user asks why the plan changed, compare model inputs and outputs before and after an override or rerun.

## Tool Routing

- Use `get_model_input` to inspect the exact input used for a model run.
- Use `get_model_output` to inspect the raw optimizer output for a model run.
- Use `get_model_formulation` to explain the optimization objective, variables, constraints, and outputs.
- Use `override_input` to create an adjusted input payload before rerunning the model.
- Use `run_math_model` to execute the optimizer from an existing or overridden input payload.
- Use `override` to record a governed manual override decision with a justification.

## Optimization Flow

1. Confirm the `input_id`. For template-only smoke tests, `demo-model-input` is available.
2. Run the math model with `run_math_model`.
3. Retrieve model input, model output, and formulation when the user asks why the plan was generated.
4. Explain the plan.
5. Present the next actions by week, highlighting week 1 separately.

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
