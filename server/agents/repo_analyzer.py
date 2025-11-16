from ollama import AsyncClient
import os
from dotenv import load_dotenv
from typing import AsyncGenerator
from .deterministic_repo_analyzer import DeterministicRepoAnalyzer
from .github_fetcher import SimpleGitHubFetcher
import asyncio
import traceback

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
OLLAMA_MODEL = os.getenv("OLLAMA_CHAT_MODEL")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")

# Initialize Ollama AsyncClient
ollama_client = AsyncClient(host=OLLAMA_BASE_URL)

class GitHubRepoAnalyzer:
    def __init__(self, github_token: str, ollama_model: str = "phi3:mini"):
        self.github_token = GITHUB_TOKEN
        self.ollama_model = ollama_model
        self.fetcher = SimpleGitHubFetcher(github_token)
        self.ollama_client = ollama_client  # Use the global async client

    async def analyze_stream(self, repo_url: str) -> AsyncGenerator[str, None]:
        """Enhanced streaming with deterministic analysis"""
        print(f"🚀 Starting analysis for: {repo_url}")
        yield "🔍 Analyzing repository structure...\n"
        
        try:
            owner, repo = self.fetcher.parse_url(repo_url)
            yield f"📦 Repository: **{owner}/{repo}**\n\n"
            
            tree = await self.fetcher.get_tree(owner, repo)
            if not tree:
                yield "❌ Unable to fetch repository. Check if public and token valid.\n"
                return
            
            yield f"✅ Found {len(tree)} files\n"
            yield "📥 Fetching critical files...\n\n"
            
            # Critical file patterns with priorities
            critical_patterns = {
                'package.json': 1,
                'package-lock.json': 1,
                'yarn.lock': 1,
                'requirements.txt': 1,
                'angular.json': 1,
                'tsconfig.json': 2,
                '.gitignore': 2,
                '.env.example': 1,
                'next.config.js': 2,
                'server.js': 3,
                'index.js': 3,
                'app.js': 3,
                'main.js': 3,
                'main.py': 3,
                'app.py': 3,
                'manage.py': 3,
            }
            
            matched_files = []
            for item in tree:
                if item["type"] != "blob":
                    continue
                
                path = item["path"]
                
                # SKIP these directories entirely
                skip_dirs = ['node_modules/', '.git/', '__pycache__/', 
                            '.cache/', 'build/', 'dist/', '.next/']
                if any(skip in path for skip in skip_dirs):
                    continue
                
                # Match critical files
                filename = path.split('/')[-1]
                if filename in critical_patterns:
                    priority = critical_patterns[filename]
                    # Prefer root-level files
                    if '/' not in path:
                        priority = 0
                    matched_files.append((path, priority))
            
            # Sort by priority
            matched_files.sort(key=lambda x: (x[1], x[0]))
            matched_files = [f[0] for f in matched_files[:20]]  # Top 20 files
            
            yield f"📋 Found {len(matched_files)} critical files:\n"
            for f in matched_files[:10]:
                yield f"  - {f}\n"
            yield "\n"
            
            # Fetch file contents
            files_content = {}
            for idx, file_path in enumerate(matched_files, 1):
                yield f"📖 Reading {file_path}...\n"
                content = await self.fetcher.get_file(owner, repo, file_path)
                if content:
                    files_content[file_path] = content
                    yield f"   ✅ Done\n"
                else:
                    yield f"   ⚠️ Failed\n"
                await asyncio.sleep(0.01)
            
            if not files_content:
                yield "⚠️ Could not read any files\n"
                return
            
            yield "\n🔬 Performing deterministic analysis...\n\n"
            
            # DETERMINISTIC ANALYSIS
            deterministic = DeterministicRepoAnalyzer(tree, files_content)
            structured_analysis = deterministic.analyze()
            
            # Display results
            yield "## 📊 Analysis Results:\n\n"

            # Check if monorepo or single service
            if structured_analysis.get('repo_type') == 'monorepo':
                # MONOREPO: Multiple services
                services = structured_analysis['services']
                yield f"**Repository Type:** Monorepo ({len(services)} services detected)\n\n"
                
                for idx, service in enumerate(services, 1):
                    yield f"### 🔹 Service {idx}: {service['name']}\n"
                    yield f"- **Type:** {service['type'].capitalize()}\n"
                    yield f"- **Path:** `{service['path']}`\n"
                    
                    tech = service['tech_stack']
                    yield f"- **Runtime:** {tech['runtime']} {tech['version']}\n"
                    
                    if tech['frameworks']:
                        yield f"- **Frameworks:** {', '.join(tech['frameworks'])}\n"
                    
                    server = service['server_config']
                    yield f"- **Port:** {server['port']}\n"
                    
                    build = service['build_system']
                    if build.get('needs_build'):
                        yield f"- **Build Command:** `{build['build_command']}`\n"
                        yield f"- **Output Directory:** `{build['output_dir']}`\n"
                    
                    db = service['database']
                    if db.get('needs_database'):
                        yield f"- **Database:** {db['type']} ({db.get('orm', 'No ORM')})\n"
            
                yield "\n"

            else:
                # SINGLE SERVICE: Original display logic
                tech = structured_analysis.get('tech_stack', {})
                if tech:
                    yield f"**Tech Stack:**\n"
                    yield f"- Runtime: {tech.get('runtime', 'unknown')} {tech.get('version', '')}\n"
                    yield f"- Frontend: {tech.get('frontend') or 'None'}\n"
                    yield f"- Backend: {tech.get('backend') or 'None'}\n"
                    if tech.get('frameworks'):
                        yield f"- Frameworks: {', '.join(tech['frameworks'])}\n"
                    yield "\n"
            
            server = structured_analysis.get('server_config', {})
            
            if server:
                yield f"**Server Configuration:**\n"
                yield f"- Port: {server.get('port', 'N/A')} ({server.get('port_source', 'unknown')})\n"
                yield f"- Entry Point: {server.get('entry_point', 'N/A')}\n\n"
            
            build = structured_analysis.get('build_system', {})
            
            if build.get('needs_build'):
                yield f"**Build System:**\n"
                yield f"- Needs Build: Yes\n"
                yield f"- Build Command: `{build.get('build_command')}`\n"
                yield f"- Output Directory: `{build.get('output_dir')}`\n"
                yield f"- Package Manager: {build.get('package_manager', 'npm')}\n\n"
            
            db = structured_analysis.get('database', {})
            
            if db.get('needs_database'):
                yield f"**Database:**\n"
                yield f"- Type: {db.get('type')}\n"
                yield f"- ORM: {db.get('orm') or 'None'}\n\n"
            
            env = structured_analysis.get('environment', {})
            
            if env.get('required_vars'):
                yield f"**Environment Variables Required:**\n"
                for var in env['required_vars'][:10]:
                    yield f"- {var}\n"
                yield "\n"

            yield "💾 Storing structured analysis...\n"

            # Store structured data
            self.structured_data = {
                'repo_url': repo_url,
                'owner': owner,
                'repo': repo,
                'analysis': structured_analysis,
                'files_analyzed': list(files_content.keys()),
                'tree_size': len(tree),
            }

            yield "\n✅ Analysis complete!\n"

            # Check for .env only for single service repos
            if structured_analysis.get('repo_type') != 'monorepo':
                env = structured_analysis.get('environment', {})
                
        except Exception as e:
            error_msg = f"❌ Error: {str(e)}\n"
            print(error_msg)
            print(traceback.format_exc())
            yield error_msg

    async def analyze(self, repo_url: str) -> str:
        """
        Non-streaming version (for backward compatibility)
        """
        result = []
        async for chunk in self.analyze_stream(repo_url):
            result.append(chunk)
        return ''.join(result)