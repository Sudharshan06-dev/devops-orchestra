import aiohttp

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
            print(f"🔍 Fetching tree from branch '{branch}' {url}...")
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
