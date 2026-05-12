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
    assert "portfolio-planning___run-portfolio-optimization" in skills[0]["allowedTools"]


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
    assert {gateway["id"] for gateway in gateways} == {"portfolio-planning"}
    assert len(tools) >= 10
    assert any(tool["name"] == "run-portfolio-optimization" for tool in tools)
    assert any(tool["name"] == "generate-weekly-plan-report" for tool in tools)
    assert module._normalize_tool_name("portfolio-planning___run-portfolio-optimization") == "run-portfolio-optimization"


def test_mcp_proxy_local_gateway_contract() -> None:
    module = _load_module("lambda/gateway-proxy/index.py", "gateway_proxy")

    def fake_invoke(tool, arguments=None):
        if tool == "listTools":
            return {"tools": [{"name": "list-portfolios", "gateway": arguments["gateway"]}]}
        if tool == "list-portfolios":
            return {"portfolios": [{"portfolioId": "demo-growth-income"}]}
        raise AssertionError(tool)

    module._invoke_tool = fake_invoke
    list_response = module._handle_mcp(
        {
            "targetUrl": "local://portfolio-planning",
            "mcpBody": {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        }
    )
    assert list_response["result"]["tools"][0]["name"] == "list-portfolios"

    call_response = module._handle_mcp(
        {
            "targetUrl": "local://portfolio-planning",
            "mcpBody": {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "list-portfolios", "arguments": {}},
            },
        }
    )
    assert "demo-growth-income" in call_response["result"]["content"][0]["text"]


if __name__ == "__main__":
    test_sample_dataset_loads()
    test_ping_module_imports()
    test_agent_skills_are_discoverable()
    test_public_gateway_tool_catalog()
    test_mcp_proxy_local_gateway_contract()
    print("OK")
