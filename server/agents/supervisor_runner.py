from langchain.agents import Tool, AgentExecutor, initialize_agent
from langchain_community.chat_models import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from agents.chat_agent import stream_assistant_reply
from agents.repo_analyzer import GitHubRepoAnalyzer
# Import the actual function, not the tool wrapper
from agents.terraform_agent import terraform_generator as terraform_generator_tool
import os, re
import asyncio

# === 1. Config ===
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
OLLAMA_MODEL = os.getenv("OLLAMA_CHAT_MODEL")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")

# === 2. LangChain LLM ===
llm = ChatOllama(
    model=OLLAMA_MODEL,
    base_url=OLLAMA_BASE_URL
)

# === 3. Session Memory ===
SESSION_CONTEXT = {}

# === 3.5. Get the actual terraform function ===
# The terraform_generator_tool might be a Tool wrapper, extract the actual function
if hasattr(terraform_generator_tool, 'coroutine'):
    terraform_func = terraform_generator_tool.coroutine
elif hasattr(terraform_generator_tool, 'func'):
    terraform_func = terraform_generator_tool.func
elif callable(terraform_generator_tool):
    terraform_func = terraform_generator_tool
else:
    # Fallback: import directly from module
    try:
        from agents.terraform_agent import generate_terraform_config
        terraform_func = generate_terraform_config
    except ImportError:
        terraform_func = None
        print("⚠️ Warning: Could not import terraform function")

# === 4. Helper Functions ===
def is_github_url(text: str) -> bool:
    return bool(re.search(r"https://github\.com/[^\s)]+", text))

def extract_github_url(text: str) -> str:
    match = re.search(r"https://github\.com/[^\s)]+", text)
    return match.group(0) if match else ""

async def route_to_agent(user_input: str, chat_id: str = "default"):
    """
    Smart routing logic that determines which agent to use
    Returns: (agent_name, response_generator)
    """
    print(f"🎯 Routing input: {user_input[:100]}...")
    last_tool = SESSION_CONTEXT.get(chat_id)
    
    # Check if input contains GitHub URL
    if is_github_url(user_input):
        SESSION_CONTEXT[chat_id] = "repo_analyzer"
        github_url = extract_github_url(user_input)
        print(f"✅ Detected GitHub URL: {github_url}")
        print(f"🔀 Routing to: repo_analyzer")
        
        async def repo_stream():
            print(f"🚀 Starting repo_stream for: {github_url}")
            analyzer = GitHubRepoAnalyzer(github_token=GITHUB_TOKEN, ollama_model=OLLAMA_MODEL)
            
            # Use the streaming version
            chunk_count = 0
            async for chunk in analyzer.analyze_stream(github_url):
                chunk_count += 1
                yield chunk
            
            print(f"✅ repo_stream completed: {chunk_count} chunks yielded")
        
        return "repo_analyzer", repo_stream()
    
    # Check if input is requesting Terraform generation
    terraform_keywords = ['terraform', 'infrastructure', 'ecs', 'rds', 'alb', 'load balancer', 'generate infra']
    if any(keyword in user_input.lower() for keyword in terraform_keywords):
        SESSION_CONTEXT[chat_id] = "terraform_generator"
        print(f"🔀 Routing to: terraform_generator")
        
        async def terraform_stream():
            print("🚀 Starting terraform_stream")
            
            if terraform_func is None:
                yield "❌ Error: Terraform generator not available\n"
                return
            
            try:
                result = await terraform_func(user_input)
            except Exception as e:
                print(f"❌ Error calling terraform_func: {str(e)}")
                import traceback
                traceback.print_exc()
                result = f"❌ Error generating Terraform: {str(e)}"
            
            # Stream the terraform code line by line
            chunk_count = 0
            for line in result.split('\n'):
                yield line + '\n'
                chunk_count += 1
                await asyncio.sleep(0.01)
            print(f"✅ terraform_stream completed: {chunk_count} chunks yielded")
        
        return "terraform_generator", terraform_stream()
    
    # Default to chat agent
    SESSION_CONTEXT[chat_id] = "chat_agent"
    print(f"🔀 Routing to: chat_agent")
    
    async def chat_stream():
        print("🚀 Starting chat_stream")
        chunk_count = 0
        async for chunk in stream_assistant_reply(user_input):
            chunk_count += 1
            yield chunk
        print(f"✅ chat_stream completed: {chunk_count} chunks yielded")
    
    return "chat_agent", chat_stream()


# === Optional: Tool definitions for LangChain (if you want to keep the agent executor) ===

async def chat_agent_tool(input: str) -> str:
    """Collect full response from chat agent"""
    response = ""
    async for chunk in stream_assistant_reply(input):
        response += chunk
    return response.strip()

chat_tool = Tool(
    name="chat_agent",
    func=chat_agent_tool,
    description="Answer DevOps/infrastructure questions (AWS, CI/CD, scaling, cost, etc.)",
    coroutine=chat_agent_tool
)

async def analyze_repo_tool(input: str) -> str:
    """Analyze GitHub repository"""
    print('🔧 analyze_repo_tool called')
    analyzer = GitHubRepoAnalyzer(github_token=GITHUB_TOKEN, ollama_model=OLLAMA_MODEL)
    result = await analyzer.analyze(input)
    return result

repo_tool = Tool(
    name="repo_analyzer",
    func=analyze_repo_tool,
    description="Analyze GitHub repo to extract tech stack, dependencies, Dockerfiles, etc.",
    coroutine=analyze_repo_tool
)

terraform_tool = Tool(
    name="terraform_generator",
    func=terraform_func if terraform_func else lambda x: "Terraform generator not available",
    description="Generate Terraform for AWS infra (e.g., ECS with ALB, RDS).",
    coroutine=terraform_func if terraform_func else None
)

tools = [chat_tool, repo_tool, terraform_tool]

agent_executor = initialize_agent(
    tools=tools,
    llm=llm,
    agent_type="chat-zero-shot-react-description",
    verbose=True,
    handle_parsing_errors=True
)