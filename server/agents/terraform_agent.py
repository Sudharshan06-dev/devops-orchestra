from ollama import AsyncClient
import os
from langchain_core.tools import tool

# === Load Env ===
OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL')
OLLAMA_CHAT_MODEL = os.getenv('OLLAMA_CHAT_MODEL')
ollama_client = AsyncClient(host=OLLAMA_BASE_URL)

# === Terraform Code Prompt ===
TERRAFORM_GEN_SYSTEM_PROMPT = """You are Aivina, a DevOps assistant that writes clean and production-grade Terraform code.

Guidelines:
- Generate only `main.tf` code using AWS resources
- Always include provider, variables (where needed), and clean naming
- Return ONLY valid Terraform syntax (.tf)
- Include minimal inline comments
- Do NOT explain the code or add disclaimers
- Do NOT output anything except the Terraform code
"""

async def terraform_generator(input: str):
    """
    Generates Terraform infrastructure configuration based on user input or repo summary.

    Input: natural language description of desired infra (e.g., 'create ECS with ALB and RDS')
    Output: Terraform main.tf code only
    """
    print("🛠️ Terraform Generator Invoked")

    response = await ollama_client.chat(
        model=OLLAMA_CHAT_MODEL,
        messages=[
            {"role": "system", "content": TERRAFORM_GEN_SYSTEM_PROMPT},
            {"role": "user", "content": input}
        ],
        stream=True,
        options={
            "num_predict": 2000,
            "temperature": 0.2,
            "top_p": 0.9,
        }
    )
    
    async for chunk in response:
        yield chunk["message"]["content"]