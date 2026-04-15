"""ReAct-style analyst agents for dynamic tool calling.

ReAct (Reasoning + Acting) enables agents to:
1. Think about what information is needed
2. Call tools based on reasoning
3. Observe results
4. Iterate until enough information is gathered
"""

from autogen_agentchat.agents import AssistantAgent

from app.agents.llm_config import get_model_client
from app.tools.news_search import search_company_news
from app.tools.stock_data import get_stock_info, get_financial_statements, get_price_history
from app.prompts.react_analyst import REACT_ANALYST_SYSTEM_MESSAGE


def create_react_analyst() -> AssistantAgent:
    """Create a ReAct-style analyst agent with all tools.

    This agent can dynamically decide which tools to call and in what order,
    based on the user's question and intermediate results.
    """
    return AssistantAgent(
        name="ReAct_Analyst",
        system_message=REACT_ANALYST_SYSTEM_MESSAGE,
        model_client=get_model_client(),
        tools=[
            get_stock_info,
            get_financial_statements,
            get_price_history,
            search_company_news,
        ],
        max_tool_iterations=5,  # Allow up to 5 rounds of tool calls
        reflect_on_tool_use=True,  # Enable reflection on tool results
    )
