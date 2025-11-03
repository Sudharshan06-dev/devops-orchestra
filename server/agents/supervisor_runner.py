import os
import re
from dotenv import load_dotenv
from core.context_vars import user_id_ctx
from agents.chat_agent import stream_assistant_reply
from agents.deployment_agent import deployment_generator  # Changed from terraform_generator
from agents.repo_analyzer import GitHubRepoAnalyzer
from chat.models.ChatSessions import save_session_context, update_session_field, get_session_context

load_dotenv()

# === Config ===
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
OLLAMA_MODEL = os.getenv("OLLAMA_CHAT_MODEL")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")

# === Helper Functions ===
def is_github_url(text: str) -> bool:
    """Check if text contains a GitHub URL"""
    return bool(re.search(r"https://github\.com/[^\s)]+", text))

def extract_github_url(text: str) -> str:
    """Extract GitHub URL from text"""
    match = re.search(r"https://github\.com/[^\s)]+", text)
    return match.group(0) if match else ""

# === Main Router ===
async def route_to_agent(user_input: str, chat_id: str = "default", user_id: int = None):
    """
    Smart routing logic that determines which agent to use.
    Returns: (agent_name, response_generator)
    """
    print(f"🎯 Routing input: {user_input[:100]}...")
    print(f"📋 Chat ID: {chat_id}, User ID: {user_id}")
    
    # Load existing session context
    session_context = get_session_context(chat_id)
    
    # Initialize data structure if not exists
    if 'data' not in session_context:
        session_context['data'] = {}
    
    print(f"📦 Session data keys: {list(session_context.get('data', {}).keys())}")
    
    # === Priority 1: GitHub URL Detection ===
    if is_github_url(user_input):
        github_url = extract_github_url(user_input)
        print(f"✅ Detected GitHub URL: {github_url}")
        print(f"🔀 Routing to: repo_analyzer")
        
        async def repo_stream():
            print(f"🚀 Starting repo_stream for: {github_url}")
            analyzer = GitHubRepoAnalyzer(
                github_token=GITHUB_TOKEN, 
                ollama_model=OLLAMA_MODEL
            )
            
            # Initialize session
            session_context['last_agent'] = 'repo_analyzer'
            session_context['data']['repo_data'] = {
                "repo_url": github_url,
                "status": "analyzing"
            }
            
            full_response = ""
            async for chunk in analyzer.analyze_stream(github_url):
                full_response += chunk
                yield chunk
            
            # CRITICAL: Store STRUCTURED data, not raw text
            if hasattr(analyzer, 'structured_data'):
                session_context['data']['repo_data'] = analyzer.structured_data
                session_context['data']['repo_data']['full_analysis_text'] = full_response
                session_context['data']['repo_data']['status'] = "completed"
            else:
                session_context['data']['repo_data']['status'] = "failed"
            
            # Save to DynamoDB
            save_session_context(chat_id, session_context)
            
            print(f"✅ Stored structured analysis for {chat_id}")
            print(f"📊 Analysis keys: {list(session_context['data']['repo_data'].get('analysis', {}).keys())}")
        
        return "repo_analyzer", repo_stream()
    
    # === Priority 2: Terraform Keywords ===
    deployment_keywords = [
        # Direct deployment requests
        'deploy', 'deploy my app', 'deploy application', 'deploy to aws',
        'deploy to cloud', 'go live', 'launch app', 'launch application',
        
        # Infrastructure/Configuration generation
        'generate deployment', 'create deployment', 'setup deployment',
        'generate infrastructure', 'create infrastructure', 'setup infrastructure',
        'prepare deployment', 'build deployment',
        
        # Docker-specific
        'generate docker', 'create docker', 'dockerize', 'containerize',
        'generate dockerfile', 'create dockerfile',
        
        # CDK-specific
        'generate cdk', 'create cdk', 'cdk deployment', 'aws cdk',
        
        # General cloud deployment terms
        'deploy on aws', 'deploy on ecs', 'deploy with fargate',
        'setup on aws', 'host on aws', 'cloud deployment',
        
        # Legacy terms (for backwards compatibility)
        'terraform', 'infrastructure', 'ecs', 'fargate',
        'cloudformation', 'cloud formation'
    ]
    
    if any(keyword in user_input.lower() for keyword in deployment_keywords):
        repo_context = session_context.get('data', {}).get('repo_data')
        
        if repo_context:
            print(f"✅ Found repo context for deployment generation")
            print(f"   Repo URL: {repo_context.get('repo_url', 'N/A')}")
        else:
            print(f"⚠️ No repo context found - cannot generate deployment")
            async def no_repo_stream():
                yield "⚠️ Please analyze a repository first\n"
                yield "Share a GitHub URL to get started!\n"
            return "chat_agent", no_repo_stream()
        
        session_context['last_agent'] = 'deployment_generator'
        session_context['data']['deployment_config'] = {
            'status': 'generating',
            'job_id': None,
            'dockerfile_path': None,
            'cdk_path': None,
            'generated_at': None,
            'error': None
        }
        
        save_session_context(chat_id, session_context)
        
        print(f"🔀 Routing to: deployment_generator")
        
        async def deployment_stream():
            print("🚀 Starting deployment_stream")
            chunk_count = 0
            
            async for chunk in deployment_generator(repo_context, chat_id=chat_id, user_id=user_id):
                chunk_count += 1
                yield chunk
            
            print(f"✅ deployment_stream completed: {chunk_count} chunks")

        return "deployment_generator", deployment_stream()
    
    # === Priority 3: Default to Chat Agent ===
    session_context['last_agent'] = 'chat_agent'
    save_session_context(chat_id, session_context)
    
    print(f"🔀 Routing to: chat_agent")
    
    async def chat_stream():
        print("🚀 Starting chat_stream")
        chunk_count = 0
        async for chunk in stream_assistant_reply(user_input):
            chunk_count += 1
            yield chunk
        print(f"✅ chat_stream completed: {chunk_count} chunks")
    
    return "chat_agent", chat_stream()