---
name: financial-planning-assistant
description: Standard operating procedure for portfolio optimization, weekly plan review, and financial planning explanation. Use when the user asks about portfolio planning, buy/sell plans, weekly review, liquidity constraints, or forecast deviations.
allowed-tools:
  - portfolio-planning___get_math_model_input
  - portfolio-planning___get_math_model_output
  - portfolio-planning___override_math_model_input
  - portfolio-planning___get_math_model_formulation
  - portfolio-planning___run_math_model
  - portfolio-planning___override_math_model
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

- Use `get_math_model_input` to inspect a model input. Prefer `input_id` when the user provides an input id from the UI; use `run_id` when the user asks for the input used by a specific run.
- Use `get_math_model_output` to inspect raw optimizer output. Prefer `run_id` when available; if the user provides an `input_id` from the UI, pass it as `input_id` to retrieve the latest output for that input.
- Use `get_math_model_formulation` to explain the optimization objective, variables, constraints, and outputs.
- Use `override_math_model_input` to create an adjusted input payload before rerunning the model.
- Use `run_math_model` to execute the optimizer from an existing or overridden input payload.
- Use `override_math_model` to record a governed manual override decision with a justification.

## Optimization Flow

1. Confirm the `input_id`. For template-only smoke tests, `demo-model-input` is available.
2. Run the math model with `run_math_model`.
3. Retrieve model input, model output, and formulation when the user asks why the plan was generated.
4. Explain the plan.
5. Present the next actions by week, highlighting week 1 separately.

## Model Override Flow

1. Ask what input should be changed and why.
2. Retrieve the current model input with `get_math_model_input`. Pass `input_id` directly if the user copied an input id from the UI.
3. Create a new input with `override_math_model_input`.
4. Record the human justification with `override_math_model`.
5. Run the math model with `run_math_model`.
6. Compare the new output with the previous output and explain the business impact.

## Weekly Review Flow

1. Ask for the current `run_id` and the previous `run_id` if comparison is needed.
2. Retrieve model input and model output for the relevant runs.
3. Compare portfolio value path, planned trades, cash usage, and any overridden assumptions.
4. If the user wants a new scenario, create an overridden input, record the justification, and rerun the math model.
5. Explain whether deviations are due to liquidity, changed assumptions, forecast drift, or override decisions.
