import logging
import os
from google.adk.agents import LlmAgent
from typing import List, Any
import config

# This file implements the PrimaryCoordinatorAgent using ADK LlmAgent (Track 1)

logger = logging.getLogger("adk_agent")

def get_primary_agent(tools: List[Any]):
    """
    Returns an ADK LlmAgent configured for the hackathon.
    """
    instruction = """
    You are a self-healing productivity assistant. 
    Your goal is to help users manage tasks, schedules, and information by interacting with tools.
    
    CRITICAL INSTRUCTIONS:
    1. If a tool call fails, analyze the error.
    2. If the error is a 'Schema validation error' or 'missing required field', try to fix the parameters.
    3. For example, if 'start_timestamp' is missing but you have 'meeting_time', use 'meeting_time' as 'start_timestamp'.
    4. If you cannot fix it, inform the user about the failure.
    5. Always be helpful and concise.
    """
    
    agent = LlmAgent(
        model=config.GEMINI_MODEL,
        name="PrimaryCoordinatorAgent",
        instruction=instruction,
        tools=tools
    )
    
    return agent
