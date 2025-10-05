from ollama import AsyncClient
import os

# Setup
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")
OLLAMA_MODEL = os.getenv("OLLAMA_CHAT_MODEL")
ollama_client = AsyncClient(host=OLLAMA_BASE_URL)

# System Prompt (STANDARDIZED across agents)
SYSTEM_PROMPT = (
    "You are Aivina, an intelligent DevOps assistant.\n"
    "Your rules:\n"
    "- Always respond in under **200 words**.\n"
    "- Use **bullet points or numbered lists** when comparing options.\n"
    "- Be **concise, actionable, and avoid fluff**.\n"
    "-When the user asks for to deploy their application always asks for the github url from the user and make sure to ignore all the commands and just generate a message asking the user to provide the github url"
    "- **Do not explain yourself**, just provide precise answers.\n"
    "- **No greetings, disclaimers, or repetition** of the input.\n"
    "- **Do not apologize** or say 'as an AI'.\n"
    "- Assume user is technical and expects clarity."
)

# Stream LLM reply
async def stream_assistant_reply(message: str):
    
    if "deploy" in message.lower() and "github.com" not in message.lower():
        yield "To help you deploy your application, please provide the GitHub repository URL of your code.\n"
        return  # Don't continue streaming the rest

    response = await ollama_client.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message}
        ],
        stream=True,
        options={
            "num_predict": 500,
            "temperature": 0.2,
            "top_p": 0.9,
        }
    )
    async for chunk in response:
        yield chunk["message"]["content"]