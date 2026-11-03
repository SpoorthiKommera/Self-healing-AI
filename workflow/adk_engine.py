import logging
import uuid
import asyncio
from typing import List, Dict, Any

import config
from mcp_config import get_toolbox_client, generate_tools_yaml
from agents.adk_agent import get_primary_agent
from models.schemas import WorkflowState, WorkflowStatus, StepStatus, WorkflowStep

# Import ADK runner and session components
from google.adk.runners import InMemoryRunner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

logger = logging.getLogger("adk_engine")

class ADKWorkflowEngine:
    """
    New Workflow Engine powered by Google ADK and MCP Toolbox.
    """
    
    def __init__(self):
        # Ensure tools.yaml exists
        generate_tools_yaml()
        
        # In a real hackathon, you'd start the 'toolbox' binary here.
        self.toolbox = get_toolbox_client()
        
        # Load tools from MCP Toolbox
        try:
            self.tools = self.toolbox.load_toolset('main_toolset')
            logger.info("Successfully loaded tools from MCP Toolbox")
        except Exception as e:
            logger.warning(f"Could not connect to MCP Toolbox: {e}. Falling back to local tools.")
            # Fallback to local tools if toolbox is not running
            from tools.adk_tools import create_event, send_message, create_note
            self.tools = [create_event, send_message, create_note]

        # Initialize the ADK Agent
        self.agent = get_primary_agent(self.tools)
        
        # Initialize the ADK Runner with an explicit session service
        self.session_service = InMemorySessionService()
        self.runner = InMemoryRunner(agent=self.agent)
        # Manually inject the session service if needed, or use it to create sessions
        # In this version of ADK, the runner has its own session service.
        # Let's try to use the runner's internal session service.

    async def run_task(self, task_query: str) -> Dict[str, Any]:
        """
        Runs a task using the ADK LlmAgent via InMemoryRunner.
        """
        logger.info(f"ADK Engine starting task: {task_query}")
        
        user_id = "hackathon_user"
        session_id = str(uuid.uuid4())
        
        try:
            # Create the session explicitly before running
            # Accessing the internal session_service of the runner
            self.runner.session_service.create_session(
                app_name="Self-Healing-Agent",
                user_id=user_id,
                session_id=session_id
            )
            
            # Create the message content
            new_message = Content(parts=[Part(text=task_query)])
            
            final_response_text = ""
            
            # Run the agent using the runner's async generator
            async for event in self.runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=new_message
            ):
                # Collect text from the agent's events
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            final_response_text += part.text
                
                if event.get_function_calls():
                    for fc in event.get_function_calls():
                        logger.info(f"Agent calling tool: {fc.name}")

            return {
                "workflow_id": str(uuid.uuid4())[:8],
                "task": task_query,
                "status": "completed",
                "final_response": final_response_text,
                "steps": [], 
                "healing_log": [] 
            }
        except Exception as e:
            logger.error(f"ADK Engine task failed: {e}")
            return {
                "workflow_id": str(uuid.uuid4())[:8],
                "task": task_query,
                "status": "failed",
                "error": str(e)
            }
