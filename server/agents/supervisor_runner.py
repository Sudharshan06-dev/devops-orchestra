import os
import re
from dotenv import load_dotenv
from core.context_vars import user_id_ctx
from agents.chat_agent import stream_assistant_reply
from agents.repo_analyzer import GitHubRepoAnalyzer
from agents.terraform_agent import terraform_generator

load_dotenv()

# === Config ===
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
OLLAMA_MODEL = os.getenv("OLLAMA_CHAT_MODEL")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")

# === Session Context (tracks last agent used per chat) ===
SESSION_CONTEXT = {
    # Structure: {
    #   "chat_id": {
    #       "last_agent": "agent_name",
    #       "repo_data": {...},  # Store full analysis here
    #       "repo_url": "https://...",
    #   }
    # }
}

# === Helper Functions ===
def is_github_url(text: str) -> bool:
    """Check if text contains a GitHub URL"""
    return bool(re.search(r"https://github\.com/[^\s)]+", text))

def extract_github_url(text: str) -> str:
    """Extract GitHub URL from text"""
    match = re.search(r"https://github\.com/[^\s)]+", text)
    return match.group(0) if match else ""

# === Main Router ===
async def route_to_agent(user_input: str, chat_id: str = "default"):
    """
    Smart routing logic that determines which agent to use.
    Returns: (agent_name, response_generator)
    """
    print(f"🎯 Routing input: {user_input[:100]}...")
    
    # === Priority 1: GitHub URL Detection ===
    if is_github_url(user_input):
        github_url = extract_github_url(user_input)
        print(f"✅ Detected GitHub URL: {github_url}")
        print(f"🔀 Routing to: repo_analyzer")
        
        async def repo_stream():
            print(f"🚀 Starting repo_stream for: {github_url} {GITHUB_TOKEN}")
            analyzer = GitHubRepoAnalyzer(
                github_token=GITHUB_TOKEN, 
                ollama_model=OLLAMA_MODEL
            )
            
            # Initialize storage for this chat (MOVED BEFORE ASSIGNMENT)
            if chat_id not in SESSION_CONTEXT:
                SESSION_CONTEXT[chat_id] = {}
            
            # Now it's safe to assign properties
            SESSION_CONTEXT[chat_id]["last_agent"] = "repo_analyzer"
            SESSION_CONTEXT[chat_id]["repo_url"] = github_url
            SESSION_CONTEXT[chat_id]["repo_data"] = {
                "files": [],
                "analysis": "",
                "dependencies": {}
            }
            
            full_response = ""
            chunk_count = 0
            async for chunk in analyzer.analyze_stream(github_url):
                chunk_count += 1
                full_response += chunk
                yield chunk
            
            # Store the complete analysis
            SESSION_CONTEXT[chat_id]["repo_data"]["full_analysis"] = full_response
            
            print(f"✅ repo_stream completed: {chunk_count} chunks")
            print(f"💾 Stored analysis for chat_id: {chat_id}")
        
        return "repo_analyzer", repo_stream()
    
    # === Priority 2: Terraform Keywords ===
    terraform_keywords = [
        'terraform', 'infrastructure', 'ecs', 'rds', 
        'alb', 'load balancer', 'generate infra', 'deploy infrastructure',
        'cloudformation', 'cloud formation'
    ]
    if any(keyword in user_input.lower() for keyword in terraform_keywords):
        # Initialize session context if needed
        if chat_id not in SESSION_CONTEXT:
            SESSION_CONTEXT[chat_id] = {}
        
        # Check if we have repo context
        repo_context = SESSION_CONTEXT[chat_id].get("repo_data")
        
        if repo_context:
            print(f"✅ Found repo context for terraform generation")
        else:
            print(f"⚠️ No repo context found - generating generic terraform")
        
        SESSION_CONTEXT[chat_id]["last_agent"] = "terraform_generator"
        print(f"🔀 Routing to: terraform_generator")
        
        async def terraform_stream():
            print("🚀 Starting terraform_stream")
            chunk_count = 0
            full_terraform = ""
            user_context = user_id_ctx.get()
            user_id = user_context.user_id
            
            async for chunk in terraform_generator(user_input, repo_context, chat_id=chat_id, user_id=user_id):
                chunk_count += 1
                full_terraform += chunk
                yield chunk
            
            # Store the terraform config for later validation/deployment
            SESSION_CONTEXT[chat_id]["terraform_config"] = full_terraform
            
            print(f"✅ terraform_stream completed: {chunk_count} chunks")
    
        return "terraform_generator", terraform_stream()
    
    # === Priority 3: Deployment/Validation Keywords ===
    deployment_keywords = [
        'deploy', 'validate', 'check prerequisites', 'ready to deploy',
        'deployment check', 'can i deploy', 'validate deployment'
    ]
    if any(keyword in user_input.lower() for keyword in deployment_keywords):
        # Initialize session context if needed
        if chat_id not in SESSION_CONTEXT:
            SESSION_CONTEXT[chat_id] = {}
        
        # Check if we have terraform config
        if "terraform_config" in SESSION_CONTEXT[chat_id]:
            print(f"🔀 Routing to: deployment_validator")
            
            async def deployment_stream():
                # This will be implemented with your validation logic
                yield "🔍 Validating deployment prerequisites...\n\n"
                yield "⚠️ Deployment validation agent not yet implemented.\n"
                yield "This will check:\n"
                yield "- AWS credentials\n"
                yield "- Environment variables\n"
                yield "- S3 code presence\n"
                yield "- Terraform variables\n"
            
            return "deployment_validator", deployment_stream()
        else:
            async def no_terraform_stream():
                yield "⚠️ No Terraform configuration found.\n\n"
                yield "Please generate Terraform configuration first by asking:\n"
                yield '"Generate Terraform for AWS" or similar.\n'
            
            return "chat_agent", no_terraform_stream()
    
    # === Priority 4: Default to Chat Agent ===
    if chat_id not in SESSION_CONTEXT:
        SESSION_CONTEXT[chat_id] = {}
    
    SESSION_CONTEXT[chat_id]["last_agent"] = "chat_agent"
    print(f"🔀 Routing to: chat_agent")
    
    async def chat_stream():
        print("🚀 Starting chat_stream")
        chunk_count = 0
        async for chunk in stream_assistant_reply(user_input):
            chunk_count += 1
            yield chunk
        print(f"✅ chat_stream completed: {chunk_count} chunks")
    
    return "chat_agent", chat_stream()