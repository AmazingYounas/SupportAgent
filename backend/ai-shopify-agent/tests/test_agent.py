from app.agent.prompts import SYSTEM_PROMPT
from app.agent.graph import create_tools, create_llm_with_tools, create_agent_graph
 

def test_system_prompt_core_voice_rules_present():
    assert "REAL-TIME VOICE AGENT" in SYSTEM_PROMPT
    assert "English only" in SYSTEM_PROMPT
    assert "Never make up" in SYSTEM_PROMPT
    assert "interrupt" in SYSTEM_PROMPT.lower()


def test_agent_graph_structure():
    tools = create_tools()
    llm = create_llm_with_tools(tools)
    app_graph = create_agent_graph(tools, llm)

    assert "reasoning" in app_graph.nodes
    assert "tools" in app_graph.nodes
    assert app_graph is not None


def test_tools_are_bound_to_llm():
    tools = create_tools()
    llm = create_llm_with_tools(tools)

    assert len(tools) > 0
    assert llm is not None

    tool_names = [tool.name for tool in tools]
    assert "check_order_status" in tool_names
    assert "cancel_order" in tool_names
    assert "search_products" in tool_names
    assert "update_customer_facts" in tool_names
    assert "get_customer_facts" in tool_names
    assert "escalate_to_human" in tool_names


def test_tool_instance_isolation():
    tools1 = create_tools()
    tools2 = create_tools()

    assert tools1[0] is not tools2[0]
    assert [tool.name for tool in tools1] == [tool.name for tool in tools2]

