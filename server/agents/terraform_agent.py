# agents/terraform_agent.py
from ollama import AsyncClient
import os
import asyncio
import uuid
from datetime import datetime, timezone
from chat.dynamo_instance import DynamoDBConnection
from pathlib import Path
import boto3

OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL')
OLLAMA_CHAT_MODEL = os.getenv('OLLAMA_CHAT_MODEL')
TERRAFORM_OUTPUT_DIR = os.getenv("TERRAFORM_OUTPUT_DIR", "./generated_terraform")
dynamo_db = DynamoDBConnection.get_instance().table
ollama_client = AsyncClient(host=OLLAMA_BASE_URL)

async def terraform_generator(user_input: str, repo_context: dict = None, chat_id: str = "default", user_id: int = None):
    """
    Start background generation and return immediately
    """
    job_id = str(uuid.uuid4())
    
    # Start background task (don't wait for it)
    asyncio.create_task(
        _generate_in_background(job_id, user_input, repo_context, chat_id, user_id)
    )
    
    # Return immediate response
    yield f"🚀 Generating Terraform configuration...\n\n"
    yield f"📋 Job ID: `{job_id}`\n\n"
    yield f"⏱️ This will take 2-3 minutes.\n"
    yield f"💬 You can continue chatting. I'll notify you when it's ready!\n"


async def _generate_in_background(job_id: str, user_input: str, repo_context: dict, chat_id: str, user_id: int):
    
    env_file_path = Path(f"./user_uploads/{user_id}/.env")
    env_vars_text = ""

    if env_file_path.exists():
        env_vars_text += env_file_path.read_text()
        print(f"Loaded .env file for {chat_id}")
    else:
        print(f" No .env file found for {chat_id}")
    
    """
    Generate terraform in background and save to file
    """
    try:
        if repo_context:
            prompt = f"""
                    Generate production-ready Terraform for AWS.

                    Repository Analysis:
                    {repo_context.get('full_analysis', '')}

                    Environment Variables (.env):
                    {env_vars_text or 'None provided'}

                    User Request: {user_input}

                    Generate complete Terraform files including:
                    - main.tf
                    - variables.tf
                    - outputs.tf

                    Use clear file separators like:
                    ### FILE: main.tf
                    [content]

                    ### FILE: variables.tf
                    [content]
                """
        else:
            prompt = f"""Generate Terraform for: {user_input}

        Environment Variables (.env):
        {env_vars_text or 'None provided'}
        """
        
        print(f"🔨 Generating Terraform for job {job_id}...")
        
        # Generate (no streaming, unlimited tokens)
        response = await ollama_client.chat(
            model=OLLAMA_CHAT_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_input}
            ],
            stream=False,
            options={
                "num_predict": -1,  # Unlimited
                "temperature": 0.2,
            }
        )
        
        content = response["message"]["content"]
        
        # Save to file
        output_dir = Path(TERRAFORM_OUTPUT_DIR) / job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save full content
        terraform_file = output_dir / "terraform_config.tf"
        terraform_file.write_text(content)
        
        file_path = str(terraform_file.absolute())
        
        print(f"✅ Terraform saved to: {file_path}")
        
        # Insert completion message into DynamoDB
        completion_msg = {
            "chat_id": chat_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message_id": str(uuid.uuid4()),
            "role": "assistant",
            "user_id": user_id,  # Already an integer
            "content": f"**Terraform generation complete!**\n\n File saved to:\n`{file_path}`\n\n Job ID: `{job_id}`\n\n **Next steps:**\n1. Download the file\n2. Run `terraform init`\n3. Review variables\n4. Ask me to validate deployment",
            "is_active": 1,
            "job_id": job_id,
            "file_path": file_path
        }
        
        dynamo_db.put_item(Item=completion_msg)
        print(f"✅ Completion message saved to DynamoDB for chat {chat_id}")
        
    except Exception as e:
        print(f"❌ Error generating Terraform: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Save error message to DynamoDB
        try:
            error_msg = {
                "chat_id": chat_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message_id": str(uuid.uuid4()),
                "role": "assistant",
                "user_id": user_id,  # Already an integer
                "content": f"Terraform generation failed\n\n Job ID: `{job_id}`\n\n Error: {str(e)}",
                "is_active": 1,
                "job_id": job_id
            }
            dynamo_db.put_item(Item=error_msg)
        except Exception as save_error:
            print(f"❌ Failed to save error message: {str(save_error)}")
            traceback.print_exc()