import pytest
import json
from langchain_core.messages import HumanMessage, AIMessage
from app.main import init_db_and_seed
from app.agent import agent_manager, AgentState

@pytest.mark.asyncio
async def test_langgraph_graph_structure():
    """Verify that the LangGraph workflow is properly built with required nodes."""
    assert agent_manager.graph is not None
    # Check that required nodes exist in the graph
    node_names = set(agent_manager.graph.nodes.keys())
    assert "triage" in node_names
    assert "advisor" in node_names
    assert "tools" in node_names
    assert "escalation" in node_names

@pytest.mark.asyncio
async def test_langgraph_process_inquiry():
    """Test standard inquiry processing through LangGraph."""
    await init_db_and_seed()
    res = await agent_manager.process_user_message(
        phone="2348011223344",
        user_text="What courses do you have in data analytics?",
        chat_history_messages=[]
    )
    assert "response" in res
    assert len(res["response"]) > 0
    assert isinstance(res["tool_logs"], list)

@pytest.mark.asyncio
async def test_langgraph_triage_human_escalation():
    """Test that triage router detects requests for human agents and routes to escalation."""
    await init_db_and_seed()
    res = await agent_manager.process_user_message(
        phone="2348099887766",
        user_text="I want to speak to human advisor right now, please transfer me to a person",
        chat_history_messages=[]
    )
    assert "response" in res
    assert "Admissions Advisor" in res["response"] or "advisor" in res["response"].lower()
    assert "escalate_to_human_advisor" in res["tool_logs"]

@pytest.mark.asyncio
async def test_langgraph_multi_turn_state():
    """Test multi-turn conversational persistence with memory checkpointer."""
    await init_db_and_seed()
    test_phone = "2348055443322"
    
    # Turn 1
    res1 = await agent_manager.process_user_message(
        phone=test_phone,
        user_text="Hi, I am interested in Python",
        chat_history_messages=[]
    )
    assert "response" in res1
    
    # Turn 2
    res2 = await agent_manager.process_user_message(
        phone=test_phone,
        user_text="How much does it cost per month?",
        chat_history_messages=[]
    )
    assert "response" in res2

    # Check that thread state was stored in MemorySaver
    cfg = {"configurable": {"thread_id": test_phone}}
    state = await agent_manager.graph.aget_state(cfg)
    assert state is not None
    assert len(state.values.get("messages", [])) >= 2
