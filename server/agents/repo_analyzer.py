import json
import aiohttp
from ollama import AsyncClient
import os
from typing import Dict, AsyncGenerator
import asyncio

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
OLLAMA_MODEL = os.getenv("OLLAMA_CHAT_MODEL")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")

# Initialize Ollama AsyncClient
ollama_client = AsyncClient(host=OLLAMA_BASE_URL)

class SimpleGitHubFetcher:
    def __init__(self, github_token: str):
        self.github_token = github_token
        self.base_url = "https://api.github.com"

    def parse_url(self, github_url: str) -> tuple[str, str]:
        parts = github_url.strip().rstrip("/").split("github.com/")[-1].split("/")
        return parts[0], parts[1].replace(".git", "")

    async def get_tree(self, owner: str, repo: str) -> list:
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }

        for branch in ["main", "master"]:
            url = f"{self.base_url}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
            print(f"🔍 Fetching tree from branch '{branch}'...")
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        tree = data.get("tree", [])
                        print(f"✅ Found {len(tree)} files in repository")
                        return tree
                    else:
                        print(f"⚠️ Branch '{branch}' not found (status {response.status})")
        return []

    async def get_file(self, owner: str, repo: str, path: str) -> str:
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3.raw"
        }
        url = f"{self.base_url}/repos/{owner}/{repo}/contents/{path}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    return await response.text()
        return ""


class GitHubRepoAnalyzer:
    def __init__(self, github_token: str, ollama_model: str = "phi3:mini"):
        self.github_token = github_token
        self.ollama_model = ollama_model
        self.fetcher = SimpleGitHubFetcher(github_token)
        self.ollama_client = ollama_client  # Use the global async client

    async def analyze_stream(self, repo_url: str) -> AsyncGenerator[str, None]:
        """
        Streaming version that yields progress and results line by line
        """
        print(f"🚀 Starting analysis for: {repo_url}")
        yield "🔍 Analyzing repository structure...\n"
        
        try:
            owner, repo = self.fetcher.parse_url(repo_url)
            print(f"📦 Parsed repo: {owner}/{repo}")
            yield f"📦 Repository: **{owner}/{repo}**\n\n"
            
            tree = await self.fetcher.get_tree(owner, repo)
            if not tree:
                error_msg = "❌ Unable to fetch repository structure. Check if the repo is public and the token is valid.\n"
                print(error_msg)
                yield error_msg
                return
            
            yield f"✅ Found {len(tree)} files\n"
            yield "📥 Fetching configuration files...\n\n"
            
            config_files = [
                "package.json", "package-lock.json", "yarn.lock",
                "requirements.txt", "pyproject.toml", "setup.py", "Pipfile",
                "pom.xml", "build.gradle", "build.gradle.kts",
                "go.mod", "Cargo.toml", "composer.json", "Gemfile",
                "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
                ".env.example", ".env.sample",
                "next.config.js", "next.config.ts", "angular.json", "vue.config.js",
                "tsconfig.json", "vercel.json", "netlify.toml"
            ]

            matched_files = [item["path"] for item in tree if item["type"] == "blob" and any(f in item["path"] for f in config_files)]
            has_env_file = any(".env" in f for f in matched_files)
            self.missing_env_flag = not has_env_file
            
            print(f"📄 Found {len(matched_files)} config files: {matched_files}")
            
            if not matched_files:
                yield "⚠️ No configuration files found in repository\n"
                return

            yield f"📋 Found {len(matched_files)} configuration files:\n"
            for f in matched_files[:10]:
                yield f"  - {f}\n"
            yield "\n"

            files_content = {}
            for idx, file_path in enumerate(matched_files[:10], 1):
                print(f"📖 Fetching file {idx}/{min(len(matched_files), 10)}: {file_path}")
                yield f"📖 Reading {file_path}...\n"
                await asyncio.sleep(0.01)  # Allow UI to update
                
                content = await self.fetcher.get_file(owner, repo, file_path)
                if content:
                    files_content[file_path] = content[:2000] + "\n...(truncated)" if len(content) > 2000 else content
                    yield f"   ✅ Done\n"
                else:
                    yield f"   ⚠️ Could not read\n"
                
                await asyncio.sleep(0.01)

            if not files_content:
                yield "⚠️ Could not read any configuration files\n"
                return

            yield "\n🤖 Analyzing with AI...\n\n"
            print(f"🤖 Sending {len(files_content)} files to Ollama for analysis")

            context = "\n".join([
                f"===== {filename} =====\n{content}" for filename, content in files_content.items()
            ])

            prompt = f"""
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
- If a .env, .env.example, or config file with variables is not present, list “None found” and add a final message asking the user to upload or provide the necessary environment variables manually.
- Do not include Docker, Terraform, AWS, or cloud infra unless specified in a file.
- Keep your answer factual and concise.

Repository Context:
{context}
"""

            # Use TRUE async streaming from Ollama
            print("⏳ Streaming response from Ollama...")
            yield "---\n\n## 📊 Analysis Results:\n\n"
            
            # Stream using AsyncClient - same as chat_agent
            response = await self.ollama_client.chat(
                model=self.ollama_model,
                messages=[
                    {
                        "role": "system", 
                        "content": "You are a code analysis assistant. Extract only factual information from repository files."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                stream=True,
                options={
                    "temperature": 0.1,
                    "top_p": 0.9,
                    "num_predict": 500
                }
            )
            
            # Stream tokens as they arrive
            token_count = 0
            async for chunk in response:
                if 'message' in chunk and 'content' in chunk['message']:
                    token = chunk['message']['content']
                    yield token
                    token_count += 1
            
            print(f"✅ Streamed {token_count} tokens from Ollama")
            
            yield "\n✅ Analysis complete!\n"
            if self.missing_env_flag:
                yield "\n `.env` file not found in the repository.\n"
                yield "Please upload your `.env` file to continue with deployment.\n"
                
            print("✅ Analysis streaming completed")
            
        except Exception as e:
            error_msg = f"❌ Error during analysis: {str(e)}\n"
            print(error_msg)
            yield error_msg

    async def analyze(self, repo_url: str) -> str:
        """
        Non-streaming version (for backward compatibility)
        """
        result = []
        async for chunk in self.analyze_stream(repo_url):
            result.append(chunk)
        return ''.join(result)