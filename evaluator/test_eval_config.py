from pathlib import Path
import importlib.util
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from financial_planning_tests.run_eval import load_dataset


def test_sample_dataset_loads() -> None:
    rows = load_dataset(Path("test-data/sample_eval.jsonl"))
    assert rows
    assert {"question", "expected"} <= rows[0].keys()


def test_ping_module_imports() -> None:
    from financial_planning_tests import ping_agent

    assert callable(ping_agent.invoke_agent)


def test_agent_skills_are_discoverable() -> None:
    module = _load_module("agent/financial_planning_agent/skill_registry.py", "skill_registry")
    skills = module.loaded_skills(Path("agent/financial_planning_agent"))
    assert [skill["name"] for skill in skills] == ["financial-planning-assistant"]
    assert "portfolio optimization" in skills[0]["description"]
    assert skills[0]["allowedTools"] == [
        "portfolio-planning___get_model_input",
        "portfolio-planning___get_model_output",
        "portfolio-planning___override_input",
        "portfolio-planning___get_model_formulation",
        "portfolio-planning___run_math_model",
        "portfolio-planning___override",
    ]


def _load_module(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_gateway_tool_catalog() -> None:
    module = _load_module("lambda/tools/index.py", "backend_tools")
    gateways = module.list_gateways()["gateways"]
    tools = module.list_tools()["tools"]
    tool_names = {tool["name"] for tool in tools}
    assert {gateway["id"] for gateway in gateways} == {"portfolio-planning"}
    assert tool_names == {
        "get_model_input",
        "get_model_output",
        "override_input",
        "get_model_formulation",
        "run_math_model",
        "override",
    }
    assert len(tools) == 6
    assert module._normalize_tool_name("portfolio-planning___get_model_input") == "get_model_input"


def test_model_input_output_tools() -> None:
    module = _load_module("lambda/tools/index.py", "backend_tools_model")
    rerun = module.run_math_model({"input_id": "demo-model-input"})
    run_id = rerun["run_id"]
    input_id = rerun["input_id"]

    model_input = module.get_model_input({"run_id": run_id})
    assert model_input["input_id"] == input_id
    assert model_input["model_input"]["planningHorizonWeeks"] == 16

    model_output = module.get_model_output({"run_id": run_id})
    assert model_output["model_output"]["solverStatus"] == "OPTIMAL"
    assert model_output["model_output"]["plan"]["weeks"]

    formulation = module.get_model_formulation({"run_id": run_id})
    assert "objective" in formulation["formulation"]

    override = module.override_input(
        {
            "input_id": input_id,
            "overrides": {"cashAvailable": 5000},
            "justification": "Test liquidity scenario.",
        }
    )
    assert override["source_input_id"] == input_id
    overridden_rerun = module.run_math_model({"input_id": override["input_id"]})
    assert overridden_rerun["status"] == "COMPLETED"
    decision = module.record_override({"input_id": override["input_id"], "justification": "Synthetic test override."})
    assert decision["status"] == "RECORDED"


def test_mcp_proxy_local_gateway_contract() -> None:
    module = _load_module("lambda/gateway-proxy/index.py", "gateway_proxy")

    def fake_invoke(tool, arguments=None):
        if tool == "listTools":
            return {"tools": [{"name": "run_math_model", "gateway": arguments["gateway"]}]}
        if tool == "run_math_model":
            return {"run_id": "model-run-test", "status": "COMPLETED"}
        raise AssertionError(tool)

    module._invoke_tool = fake_invoke
    list_response = module._handle_mcp(
        {
            "targetUrl": "local://portfolio-planning",
            "mcpBody": {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        }
    )
    assert list_response["result"]["tools"][0]["name"] == "run_math_model"

    call_response = module._handle_mcp(
        {
            "targetUrl": "local://portfolio-planning",
            "mcpBody": {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "run_math_model", "arguments": {"input_id": "demo-model-input"}},
            },
        }
    )
    assert "model-run-test" in call_response["result"]["content"][0]["text"]


if __name__ == "__main__":
    test_sample_dataset_loads()
    test_ping_module_imports()
    test_agent_skills_are_discoverable()
    test_public_gateway_tool_catalog()
    test_model_input_output_tools()
    test_mcp_proxy_local_gateway_contract()
    print("OK")
