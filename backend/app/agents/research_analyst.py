"""Research Analyst agent – gathers news, industry trends, competitor info."""

from autogen_agentchat.agents import AssistantAgent

from app.agents.llm_config import get_model_client
from app.tools.news_search import search_company_news
from app.tools.stock_data import get_stock_info
from app.prompts.research_analyst import RESEARCH_ANALYST_SYSTEM_MESSAGE as SYSTEM_MESSAGE


def create_research_analyst() -> AssistantAgent:
    return AssistantAgent(
        name="Research_Analyst",
        system_message=SYSTEM_MESSAGE,
        model_client=get_model_client(),
        tools=[get_stock_info, search_company_news],
    )
