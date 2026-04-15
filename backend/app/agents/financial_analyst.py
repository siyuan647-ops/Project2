"""Financial Analyst agent – deep-dives into financial statements and valuation."""

from autogen_agentchat.agents import AssistantAgent

from app.agents.llm_config import get_model_client
from app.tools.stock_data import get_financial_statements, get_price_history
from app.prompts.financial_analyst import FINANCIAL_ANALYST_SYSTEM_MESSAGE as SYSTEM_MESSAGE


def create_financial_analyst() -> AssistantAgent:
    return AssistantAgent(
        name="Financial_Analyst",
        system_message=SYSTEM_MESSAGE,
        model_client=get_model_client(),
        tools=[get_financial_statements, get_price_history],
    )
