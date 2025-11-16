import os
import re
from typing import AsyncGenerator, Optional
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langchain.agents import AgentExecutor, create_react_agent
from langchain.prompts import PromptTemplate
from chat.models.ChatSessions import get_session_context, save_session_context
from agents.langchain_tools import create_tools
from agents.chat_agent import stream_assistant_reply
from agents.repo_analyzer import GitHubRepoAnalyzer
from agents.deployment_agent import deployment_generator

load_dotenv()

# === Config ===
OLLAMA_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "phi3:mini")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
USE_AGENTIC_MODE = os.getenv("USE_AGENTIC_MODE", "false").lower() == "true"


# ========================== HELPER FUNCTIONS ==========================

def extract_github_url(text: str) -> Optional[str]:
    """Extract GitHub URL from text"""
    match = re.search(r'https://github\.com/[\w\-]+/[\w\-\.]+', text)
    return match.group(0) if match else None


def is_deployment_request(text: str) -> bool:
    """Check if user is requesting deployment"""
    deployment_keywords = ['deploy', 'deployment', 'generate', 'create', 'dockerfile', 'cdk', 'infrastructure']
    return any(keyword in text.lower() for keyword in deployment_keywords)


# ========================== SIMPLE ROUTING (RELIABLE) ==========================

async def simple_route(user_input: str, chat_id: str, user_id: Optional[int] = None):
    github_url = extract_github_url(user_input)
    
    if github_url:
        analyzer = GitHubRepoAnalyzer(github_token=GITHUB_TOKEN, ollama_model=OLLAMA_MODEL)
        
        session = get_session_context(chat_id)
        if 'data' not in session:
            session['data'] = {}
        session['data']['repo_data'] = {"repo_url": github_url, "status": "analyzing"}
        session['last_agent'] = 'repo_analyzer'
        save_session_context(chat_id, session)
        
        full_response = ""
        async for chunk in analyzer.analyze_stream(github_url):
            full_response += chunk
            yield chunk
        
        # CRITICAL: Save the structured data from analyzer
        if hasattr(analyzer, 'structured_data'):
            session = get_session_context(chat_id)
            session['data']['repo_data'] = analyzer.structured_data
            session['data']['repo_data']['full_analysis_text'] = full_response
            session['data']['repo_data']['status'] = 'completed'
            save_session_context(chat_id, session)
        
        if is_deployment_request(user_input):
            yield "\n\n🚀 Starting deployment...\n\n"
            session = get_session_context(chat_id)
            repo_context = session.get('data', {}).get('repo_data')
            
            if repo_context and repo_context.get('status') == 'completed':
                async for chunk in deployment_generator(repo_context, chat_id, user_id):
                    yield chunk
            else:
                yield "❌ No repository analysis found. Please analyze a repository first.\n"
        return
    
    if is_deployment_request(user_input):
        session = get_session_context(chat_id)
        repo_context = session.get('data', {}).get('repo_data')
        
        if repo_context and repo_context.get('status') == 'completed':
            async for chunk in deployment_generator(repo_context, chat_id, user_id):
                yield chunk
        else:
            yield "⚠️ No repository found. Share a GitHub URL first.\n"
        return
    
    async for chunk in stream_assistant_reply(user_input):
        yield chunk


# ========================== AGENTIC ROUTING (EXPERIMENTAL) ==========================

REACT_PROMPT = PromptTemplate.from_template("""You are a DevOps assistant.

Tools available:
{tools}

Tool names: {tool_names}

When user provides GitHub URL, extract it and use analyze_github_repository tool.
When user asks to deploy, use generate_deployment_configuration tool.
For other questions, use general_chat tool.

IMPORTANT: When calling tools, you MUST include chat_id and user_id in the Action Input.
Example:
Action: analyze_github_repository
Action Input: {{"github_url": "https://github.com/user/repo", "chat_id": "{chat_id}"}}

Format:
Question: {input}
Thought: [your reasoning]
Action: [tool name]
Action Input: [JSON with parameters INCLUDING chat_id: "{chat_id}" and user_id: "{user_id}"]
Observation: [tool result]
... repeat as needed ...
Thought: I now know the answer
Final Answer: [your response]

Begin!

Question: {input}
{agent_scratchpad}
""")


class AgenticSupervisor:
    """LangChain agent - may have issues, use simple routing as fallback"""
    
    def __init__(self, chat_id: str, user_id: Optional[int] = None):
        self.chat_id = chat_id
        print('self.chat_id', chat_id)
        self.user_id = user_id
        
        self.llm = ChatOllama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=0.1,
            num_predict=2000,
            timeout=120
        )
        
        self.tools = create_tools(chat_id=chat_id, user_id=user_id)
        
        self.agent = create_react_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=REACT_PROMPT
        )
        
        self.agent_executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=3,
            max_execution_time=120,
            return_intermediate_steps=True
        )
    
    async def process_message(self, user_input: str) -> AsyncGenerator[str, None]:
        """Process with agent (may fail, has fallback)"""
        yield "🤖 Agent is thinking...\n\n"
        
        try:
            import asyncio
            
            task = asyncio.create_task(
                self.agent_executor.ainvoke({
                    "input": user_input,
                    "chat_id": self.chat_id,
                    "user_id": self.user_id or "None"
                })
            )
            
            # Progress updates
            wait_time = 0
            while not task.done():
                await asyncio.sleep(5)
                wait_time += 5
                if wait_time <= 30:
                    yield f"⏱️ Processing... ({wait_time}s)\n"
            
            result = await task
            
            output = result.get("output", "")
            intermediate_steps = result.get("intermediate_steps", [])
            
            if intermediate_steps:
                yield "\n✅ **Actions:**\n"
                for action, _ in intermediate_steps:
                    yield f"- {action.tool}\n"
            
            yield "\n**Answer:**\n\n"
            yield output
            
        except Exception as e:
            print(f"❌ [AGENT] Error: {e}")
            import traceback
            traceback.print_exc()
            
            yield f"\n⚠️ Agent failed: {str(e)}\n\n"
            yield "🔄 Using simple routing instead...\n\n"
            
            # Fallback to simple routing
            async for chunk in simple_route(user_input, self.chat_id, self.user_id):
                yield chunk



# ========================== MAIN ENTRY POINT ==========================

async def route_to_agent(
    user_input: str,
    chat_id: str = "default",
    user_id: Optional[int] = None
) -> tuple[str, AsyncGenerator[str, None]]:
    """
    Main routing with automatic fallback
    """
    print(f"\n{'='*60}")
    print(f"🎯 [ROUTER] Input: {user_input[:100]}")
    print(f"📋 Chat: {chat_id}, User: {user_id}")
    print(f"🤖 Agentic Mode: {USE_AGENTIC_MODE}")
    print(f"{'='*60}\n")
    
    if USE_AGENTIC_MODE:
        print("🤖 [ROUTER] Using agentic mode (with fallback)")
        try:
            supervisor = AgenticSupervisor(chat_id=chat_id, user_id=user_id)
            return "agentic_supervisor", supervisor.process_message(user_input)
        except Exception as e:
            print(f"❌ [ROUTER] Agent init failed: {e}")
            print("🔄 [ROUTER] Falling back to simple routing")
    
    # Simple routing (always works)
    print("🔀 [ROUTER] Using simple routing")
    
    async def simple_stream():
        async for chunk in simple_route(user_input, chat_id, user_id):
            yield chunk
    
    return "simple_routing", simple_stream()