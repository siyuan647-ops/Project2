"""Investment Advisor agent – synthesises research & financial analysis into a strategy."""

from autogen_agentchat.agents import AssistantAgent

from app.agents.llm_config import get_model_client
from app.prompts.investment_advisor import INVESTMENT_ADVISOR_SYSTEM_MESSAGE as SYSTEM_MESSAGE


def create_investment_advisor() -> AssistantAgent:
    return AssistantAgent(
        name="Investment_Advisor",
        system_message=SYSTEM_MESSAGE,
        model_client=get_model_client(),
    )
