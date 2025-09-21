from ollama import AsyncClient
import os

OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL')
OLLAMA_CHAT_MODEL = os.getenv('OLLAMA_CHAT_MODEL')
ollama_client = AsyncClient(host=OLLAMA_BASE_URL)


async def generate_assistant_reply(prompt: str):
    
    ai_response = await ollama_client.chat(
            model=OLLAMA_CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}]
    )
    
    return ai_response["message"]["content"]