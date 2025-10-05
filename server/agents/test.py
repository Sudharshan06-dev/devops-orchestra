import asyncio
import json
import aiohttp
import sys
import ollama

# Simple GitHub file fetcher without MCP (fallback approach)
class SimpleGitHubFetcher:
    """Simpler approach using GitHub API directly"""
    
    def __init__(self, github_token: str):
        self.github_token = github_token
        self.base_url = "https://api.github.com"
        
    def parse_github_url(self, github_url: str) -> tuple[str, str]:
        """Parse GitHub URL to extract owner and repo"""
        github_url = github_url.rstrip('/')
        if 'github.com' in github_url:
            parts = github_url.split('github.com/')[-1].split('/')
            owner = parts[0]
            repo = parts[1].replace('.git', '')
            return owner, repo
        else:
            raise ValueError("Invalid GitHub URL format")
    
    async def get_file_contents(self, owner: str, repo: str, path: str) -> str:
        """Get file contents using GitHub API"""
                
        url = f"{self.base_url}/repos/{owner}/{repo}/contents/{path}"
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3.raw"
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        return await response.text()
                    return ""
        except Exception:
            return ""
    
    async def get_repository_tree(self, owner: str, repo: str) -> list:
        
        url = f"{self.base_url}/repos/{owner}/{repo}/git/trees/main?recursive=1"
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('tree', [])
                    # Try master branch if main doesn't exist
                    url = f"{self.base_url}/repos/{owner}/{repo}/git/trees/master?recursive=1"
                    async with session.get(url, headers=headers, timeout=15) as response2:
                        if response2.status == 200:
                            data = await response2.json()
                            return data.get('tree', [])
                    return []
        except Exception as e:
            print(f"Error fetching tree: {e}")
            return []


class GitHubRepoAnalyzer:
    """
    Analyzes GitHub repositories using direct API and local Ollama LLM
    """
    
    def __init__(self, github_token: str, ollama_model: str = "llama3.1"):
        """
        Initialize the analyzer
        
        Args:
            github_token: GitHub personal access token
            ollama_model: Ollama model to use
        """
        self.github_token = github_token
        self.ollama_model = ollama_model
        self.fetcher = SimpleGitHubFetcher(github_token)
    
    def call_ollama_with_context(self, prompt: str, context: str) -> str:
        
        extraction_prompt = f"""
                You are a code analysis assistant. Your task is to extract **factual information only** from the repository content below.
                DO NOT guess, infer, or describe what "might" be there — report only what you can confirm from file names or visible file contents.

                Analyze the repository context and return:

                Languages:
                - (List each language explicitly mentioned or implied by file types, e.g. .py → Python, .java → Java)

                Frameworks & Libraries:
                - (Extract from dependency or build files only — requirements.txt, package.json, pom.xml, build.gradle, etc. Include versions if listed.)

                Configuration Files:
                - (List only config files actually present, e.g., package.json, pom.xml, tsconfig.json, docker-compose.yml)

                Environment Variables:
                - (List environment variables explicitly present in .env, .env.example, config.yml/json, or referenced in code. 
                If none are visible, output "None found" without speculation.)

                Rules:
                - Do not explain anything.
                - Do not repeat file names multiple times.
                - Do not include Docker, Terraform, AWS, or cloud infra unless specified in a file.
                - Keep your answer factual and concise.

                Repository Context:
                {context}
            """

        try:
            stream = ollama.generate(
                model=self.ollama_model,
                prompt=extraction_prompt,
                options={
                    "num_predict": 750,    # enough for listing 20–30 dependencies
                    "temperature": 0.1,    # near-deterministic factual extraction
                    "top_p": 0.9
                },
                stream=True
            )

            response_text = ""
            for chunk in stream:
                if "response" in chunk:
                    print(chunk["response"], end="", flush=True)
                    response_text += chunk["response"]
            print()
            return response_text.strip()

        except Exception as e:
            return f"Error calling Ollama: {str(e)}\n\nMake sure Ollama is running: ollama serve"

    
    async def analyze_repository(self, github_url: str) -> dict:
        """
        Analyze a GitHub repository
        
        Args:
            github_url: Full GitHub repository URL
            
        Returns:
            Dictionary with analysis results
        """
        # Parse URL
        owner, repo = self.fetcher.parse_github_url(github_url)
        print(f"\n🔍 Analyzing repository: {owner}/{repo}")
        print(f"🌐 URL: {github_url}\n")
        
        # Get repository tree
        print("📂 Fetching repository structure...")
        tree = await self.fetcher.get_repository_tree(owner, repo)
        
        if not tree:
            print("❌ Could not fetch repository tree. Check your token and repo access.")
            return {}
        
        print(f"✅ Found {len(tree)} files in repository")
        
        # Search for common configuration files
        print("\n🔎 Searching for configuration files...")
        config_files_to_find = [
            "package.json", "package-lock.json", "yarn.lock",
            "requirements.txt", "pyproject.toml", "setup.py", "Pipfile",
            "pom.xml", "build.gradle", "build.gradle.kts",
            "go.mod", "Cargo.toml", "composer.json", "Gemfile",
            "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
            ".env.example", ".env.sample",
            "next.config.js", "next.config.ts", "angular.json", "vue.config.js",
            "tsconfig.json", "vercel.json", "netlify.toml"
        ]
        
        # Find which files exist in the repo
        existing_files = []
        for item in tree:
            if item.get('type') == 'blob':
                file_path = item.get('path', '')
                if any(config in file_path for config in config_files_to_find):
                    existing_files.append(file_path)
        
        print(f"✅ Found {len(existing_files)} configuration files")
        
        # Fetch contents of found files
        found_files = {}
        for file_path in existing_files[:15]:  # Limit to first 15 files
            print(f"  📄 Fetching: {file_path}")
            content = await self.fetcher.get_file_contents(owner, repo, file_path)
            if content:
                found_files[file_path] = content
                print(f"     ✅ Got {len(content)} bytes")
        
        if not found_files:
            print("⚠️  No configuration files could be fetched")
            return {}
        
        # Build context for LLM
        print(f"\n📝 Preparing analysis with {len(found_files)} files...")
        
        context = f"""
Repository: {owner}/{repo}
URL: {github_url}

Configuration Files Found:
"""
        for filename, content in found_files.items():
            truncated_content = content[:2000] + "\n... (truncated)" if len(content) > 2000 else content
            context += f"\n{'='*60}\n📄 {filename}\n{'='*60}\n{truncated_content}\n"
        
        # Ask LLM to analyze
        print("\n🤖 Analyzing with Ollama...")
        prompt = """Analyze this repository for AWS ECS deployment:

**🎯 Technology Stack:**
- Language and version
- Framework(s) and versions
- Package manager

**📦 Deployment Requirements:**
- Docker base image needed
- Port number
- Build command
- Start command
- Health check endpoint

**🔧 Configuration:**
- Important files found
- Missing files (especially Dockerfile)

**🌍 Environment Variables:**
- Required environment variables
- Secrets needed

**💡 Recommendations:**
- Docker configuration
- AWS ECS deployment notes

Be specific and actionable."""
        
        llm_response = self.call_ollama_with_context(prompt, context)
        
        return {
            "repository": f"{owner}/{repo}",
            "url": github_url,
            "found_files": list(found_files.keys()),
            "file_contents": found_files,
            "analysis": llm_response,
            "total_files": len(tree)
        }


async def main():
    """Example usage"""
    print("="*80)
    print("🚀 GitHub Repository Analyzer for AWS ECS Deployment")
    print("="*80)
    
    # Configuration
    GITHUB_TOKEN = input("\n🔑 Enter your GitHub Personal Access Token: ").strip()
    if not GITHUB_TOKEN:
        print("❌ GitHub token is required!")
        return
    
    OLLAMA_MODEL = input("🤖 Enter Ollama model (press Enter for 'phi3:mini'): ").strip() or "phi3:mini"
    
    # Check Ollama
    print(f"\n🔍 Checking if model '{OLLAMA_MODEL}' is available...")
    try:
        models = ollama.list()
        model_names = [m['model'] for m in models.get('models', [])]
        print(f"Available models: {model_names}")
        
        if not any(OLLAMA_MODEL in name for name in model_names):
            print(f"⚠️  Model '{OLLAMA_MODEL}' not found.")
            if input("Download it? (yes/no): ").lower() in ['yes', 'y']:
                print(f"⬇️  Downloading...")
                ollama.pull(OLLAMA_MODEL)
            else:
                return
    except Exception as e:
        print(f"❌ Ollama error: {e}")
        return
    
    # Get GitHub URL
    github_url = input("\n🔗 Enter GitHub repository URL: ").strip()
    if not github_url:
        print("❌ URL required!")
        return
    
    # Analyze
    analyzer = GitHubRepoAnalyzer(github_token=GITHUB_TOKEN, ollama_model=OLLAMA_MODEL)
    
    try:
        results = await analyzer.analyze_repository(github_url)
        
        if not results:
            print("\n❌ Analysis failed")
            return
        
        # Display results
        print("\n" + "="*80)
        print("📊 ANALYSIS RESULTS")
        print("="*80)
        
        print(f"\n📦 Repository: {results['repository']}")
        print(f"🔗 URL: {results['url']}")
        print(f"📁 Total files: {results.get('total_files', 0)}")
        
        print(f"\n📄 Configuration Files Analyzed ({len(results['found_files'])}):")
        for filename in results['found_files']:
            print(f"  • {filename}")
        
        print("\n" + "="*80)
        print("🤖 LLM ANALYSIS")
        print("="*80)
        print(results['analysis'])
        
        # Save results
        with open('analysis_results.json', 'w') as f:
            json.dump({
                'repository': results['repository'],
                'url': results['url'],
                'found_files': results['found_files'],
                'analysis': results['analysis']
            }, f, indent=2)
        
        print(f"\n💾 Results saved to 'analysis_results.json'")
        
        # Validation
        print("\n" + "="*80)
        if input("\n✅ Does this look correct? (yes/no): ").strip().lower() in ['yes', 'y']:
            print("\n🎉 Great! Ready for Terraform generation...")
        else:
            print("\n🔄 Please provide corrections...")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("\n🚀 Starting Analyzer...\n")
    
    # Check if aiohttp is installed
    try:
        import aiohttp
    except ImportError:
        print("❌ Missing dependency: aiohttp")
        print("   Install with: pip install aiohttp")
        sys.exit(1)
    
    asyncio.run(main())