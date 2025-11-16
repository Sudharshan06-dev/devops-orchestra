import os
import asyncio
from typing import Optional
from langchain.tools import Tool, StructuredTool
from langchain.pydantic_v1 import BaseModel, Field
from agents.repo_analyzer import GitHubRepoAnalyzer
from agents.deployment_agent import deployment_generator
from agents.chat_agent import stream_assistant_reply
from chat.models.ChatSessions import get_session_context, save_session_context

# Environment variables
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
OLLAMA_MODEL = os.getenv("OLLAMA_CHAT_MODEL")


# ========================== INPUT SCHEMAS ==========================
class RepoAnalyzerInput(BaseModel):
    """Input schema for repository analyzer"""
    github_url: str = Field(description="GitHub repository URL to analyze")
    chat_id: str = Field(description="Chat session ID for storing results")


class DeploymentGeneratorInput(BaseModel):
    """Input schema for deployment generator"""
    chat_id: str = Field(description="Chat session ID containing repo analysis")
    user_id: Optional[int] = Field(description="User ID for file paths", default=None)


class SessionQueryInput(BaseModel):
    """Input schema for querying session data"""
    chat_id: str = Field(description="Chat session ID to query")
    data_key: str = Field(description="Key to retrieve from session data (e.g., 'repo_data', 'deployment_config')")


# ========================== TOOL FUNCTIONS ==========================

async def analyze_repository_tool(github_url: str, chat_id: str) -> str:
    """
    Analyzes a GitHub repository and stores structured data in session.
    
    Args:
        github_url: GitHub repository URL
        chat_id: Chat session ID for storing results
    
    Returns:
        Summary of analysis with key findings
    """
    print(f"🔧 [TOOL] analyze_repository called: {github_url}")
    
    try:
        analyzer = GitHubRepoAnalyzer(
            github_token=GITHUB_TOKEN,
            ollama_model=OLLAMA_MODEL
        )
        
        # Get session context
        session_context = get_session_context(chat_id)
        if 'data' not in session_context:
            session_context['data'] = {}
        
        # Initialize repo data
        session_context['data']['repo_data'] = {
            "repo_url": github_url,
            "status": "analyzing"
        }
        session_context['last_agent'] = 'repo_analyzer'
        
        # Collect all chunks
        full_response = ""
        async for chunk in analyzer.analyze_stream(github_url):
            full_response += chunk
        
        # Store structured data
        if hasattr(analyzer, 'structured_data'):
            session_context['data']['repo_data'] = analyzer.structured_data
            session_context['data']['repo_data']['full_analysis_text'] = full_response
            session_context['data']['repo_data']['status'] = "completed"
            
            # Save to DynamoDB
            save_session_context(chat_id, session_context)
            
            # Extract key findings for summary
            analysis = session_context['data']['repo_data'].get('analysis', {})
            tech_stack = analysis.get('tech_stack', {})
            
            summary = f"""Repository Analysis Complete ✅

**Repository:** {github_url}

**Technology Stack:**
- Primary: {tech_stack.get('primary', 'Unknown')}
- Frameworks: {', '.join(tech_stack.get('frameworks', []))}
- TypeScript: {tech_stack.get('has_typescript', False)}

**Configuration:**
- Port: {analysis.get('port', {}).get('port', 'Not detected')}
- Database: {analysis.get('database', {}).get('needs_database', False)}
- Package Manager: {analysis.get('package_manager', 'Unknown')}

**Status:** Analysis stored in session for deployment generation.
"""
            
            print(f"✅ [TOOL] Repository analyzed successfully")
            return summary
        else:
            session_context['data']['repo_data']['status'] = "failed"
            save_session_context(chat_id, session_context)
            return f"❌ Failed to analyze repository: No structured data returned"
    
    except Exception as e:
        print(f"❌ [TOOL] Repository analysis failed: {e}")
        return f"❌ Error analyzing repository: {str(e)}"


async def generate_deployment_tool(chat_id: str, user_id: Optional[int] = None) -> str:
    """
    Generates Dockerfile and AWS CDK infrastructure based on repository analysis.
    
    Args:
        chat_id: Chat session ID containing repo analysis
        user_id: User ID for file paths
    
    Returns:
        Summary of generated deployment configuration
    """
    print(f"🔧 [TOOL] generate_deployment called for chat_id: {chat_id}")
    
    try:
        # Get session context
        session_context = get_session_context(chat_id)
        repo_context = session_context.get('data', {}).get('repo_data')
        
        if not repo_context:
            return "❌ Cannot generate deployment: No repository analysis found. Please analyze a repository first using the analyze_repository tool."
        
        if repo_context.get('status') != 'completed':
            return f"❌ Cannot generate deployment: Repository analysis status is '{repo_context.get('status')}'. Please complete analysis first."
        
        # Initialize deployment status
        session_context['last_agent'] = 'deployment_generator'
        session_context['data']['deployment_config'] = {
            'status': 'generating',
            'job_id': None
        }
        save_session_context(chat_id, session_context)
        
        # Collect deployment generation output
        output = ""
        async for chunk in deployment_generator(repo_context, chat_id=chat_id, user_id=user_id):
            output += chunk
        
        # Get final deployment status
        updated_context = get_session_context(chat_id)
        deployment_config = updated_context.get('data', {}).get('deployment_config', {})
        
        if deployment_config.get('status') == 'completed':
            job_id = deployment_config.get('job_id', 'N/A')
            port = deployment_config.get('port', 'N/A')
            needs_db = deployment_config.get('needs_database', False)
            
            summary = f"""Deployment Configuration Generated ✅

**Job ID:** {job_id}

**Generated Files:**
- ✅ Dockerfile (production-ready)
- ✅ AWS CDK Infrastructure (Python)

**Configuration:**
- Port: {port}
- Database: {'Yes (RDS)' if needs_db else 'No'}
- Method: {deployment_config.get('generation_method', 'template')}

**Status:** Ready for deployment. User can deploy using CDK commands.
"""
            print(f"✅ [TOOL] Deployment generated successfully")
            return summary
        else:
            return f"⚠️ Deployment generation status: {deployment_config.get('status', 'unknown')}"
    
    except Exception as e:
        print(f"❌ [TOOL] Deployment generation failed: {e}")
        return f"❌ Error generating deployment: {str(e)}"


async def query_session_data_tool(chat_id: str, data_key: str) -> str:
    """
    Queries session data to check what information is available.
    
    Args:
        chat_id: Chat session ID
        data_key: Key to retrieve ('repo_data', 'deployment_config', etc.)
    
    Returns:
        Summary of requested session data
    """
    print(f"🔧 [TOOL] query_session_data called: {data_key}")
    
    try:
        session_context = get_session_context(chat_id)
        data = session_context.get('data', {})
        
        if data_key not in data:
            return f"No data found for key '{data_key}'. Available keys: {', '.join(data.keys())}"
        
        requested_data = data[data_key]
        
        if data_key == 'repo_data':
            repo_url = requested_data.get('repo_url', 'Unknown')
            status = requested_data.get('status', 'Unknown')
            analysis = requested_data.get('analysis', {})
            tech = analysis.get('tech_stack', {}).get('primary', 'Unknown')
            
            return f"""Repository Data:
- URL: {repo_url}
- Status: {status}
- Tech Stack: {tech}
- Analysis Available: {status == 'completed'}
"""
        
        elif data_key == 'deployment_config':
            status = requested_data.get('status', 'Unknown')
            job_id = requested_data.get('job_id', 'None')
            
            return f"""Deployment Configuration:
- Status: {status}
- Job ID: {job_id}
- Completed: {status == 'completed'}
"""
        
        else:
            return f"Data for '{data_key}': {str(requested_data)[:200]}"
    
    except Exception as e:
        print(f"❌ [TOOL] Session query failed: {e}")
        return f"❌ Error querying session: {str(e)}"


async def general_chat_tool(question: str) -> str:
    """
    Handles general questions and conversations using the chat agent.
    
    Args:
        question: User's question or message
    
    Returns:
        Chat agent's response
    """
    print(f"🔧 [TOOL] general_chat called: {question[:50]}...")
    
    try:
        response = ""
        async for chunk in stream_assistant_reply(question):
            response += chunk
        
        return response
    
    except Exception as e:
        print(f"❌ [TOOL] Chat failed: {e}")
        return f"❌ Error in chat: {str(e)}"


# ========================== TOOL DEFINITIONS ==========================

def create_tools(chat_id: str, user_id: Optional[int] = None) -> list:
    """
    Creates LangChain tools for the agentic supervisor.
    
    Args:
        chat_id: Current chat session ID
        user_id: Current user ID
    
    Returns:
        List of LangChain tools
    """
    
    # Tool 1: Repository Analyzer
    analyze_repo_tool = StructuredTool.from_function(
        coroutine=analyze_repository_tool,
        name="analyze_github_repository",
        description="""Analyzes a GitHub repository to extract technology stack, frameworks, dependencies, and configuration.
Use this when:
- User provides a GitHub URL
- User asks to analyze/check/examine a repository
- You need repository information before deployment

Input: github_url (string), chat_id (string)
Output: Analysis summary with tech stack, port, database requirements, etc.

IMPORTANT: Always use this tool BEFORE generating deployment configurations.""",
        args_schema=RepoAnalyzerInput
    )
    
    # Tool 2: Deployment Generator
    generate_deployment_tool_def = StructuredTool.from_function(
        coroutine=generate_deployment_tool,
        name="generate_deployment_configuration",
        description="""Generates Dockerfile and AWS CDK infrastructure for a previously analyzed repository.
Use this when:
- User asks to deploy/generate deployment/create infrastructure
- User wants Dockerfile or CDK files
- Repository has been analyzed (check with query_session_data first)

Input: chat_id (string), user_id (optional int)
Output: Deployment configuration summary with job ID and file paths

IMPORTANT: Repository MUST be analyzed first. Use query_session_data to verify.""",
        args_schema=DeploymentGeneratorInput
    )
    
    # Tool 3: Session Data Query
    query_session_tool = StructuredTool.from_function(
        coroutine=query_session_data_tool,
        name="query_session_data",
        description="""Queries the current session to check what data is available.
Use this when:
- You need to check if a repository has been analyzed
- You need to verify deployment status
- User asks "what have we done so far"
- Before generating deployment (to verify repo_data exists)

Input: chat_id (string), data_key (string: 'repo_data' or 'deployment_config')
Output: Summary of requested data

IMPORTANT: Use this to verify repository analysis exists before deployment generation.""",
        args_schema=SessionQueryInput
    )
    
    # Tool 4: General Chat
    chat_tool = Tool.from_function(
        func=lambda q: asyncio.run(general_chat_tool(q)),
        name="general_chat",
        description="""Handles general questions, explanations, and conversations that don't require specialized tools.
Use this when:
- User asks general questions about DevOps, AWS, Docker, etc.
- User needs explanations or help
- None of the other tools are appropriate

Input: question (string)
Output: Helpful response from chat agent"""
    )
    
    return [
        analyze_repo_tool,
        generate_deployment_tool_def,
        query_session_tool,
        chat_tool
    ]