from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from config.database import get_db_connection
from fastapi.responses import StreamingResponse
from chat import chat_router
from chat.schemas.user_chat_schema import UserChatRequest, UserChatResponse
from chat.models.UserChatCount import UserChatCountModel
from core.utility import create_response
from agents.chat_agent import stream_assistant_reply
from uuid import uuid4
from chat.dynamo_instance import DynamoDBConnection
from core.context_vars import user_id_ctx
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key, Attr
import logging
from typing import Optional
from agents.supervisor_runner import route_to_agent
import asyncio


logger = logging.getLogger(__name__)

dynamo_db = DynamoDBConnection.get_instance().table

@chat_router.get("/all")
async def get_all_chats():
    
    user_context = user_id_ctx.get()
    if not user_context or not hasattr(user_context, 'user_id'):
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    user_id = user_context.user_id  # Get the actual user_id from the UserModel object
            
    try:
        # Query all chats grouped by chat_id (last message as preview)
        response = dynamo_db.query(
            IndexName="user_chat_index",
            KeyConditionExpression=Key("user_id").eq(user_id),
            #FilterExpression=Attr("is_active").eq(1),
            ScanIndexForward=False
        )
            
        grouped = {}
        for item in response.get('Items', []):
            chat_id = item["chat_id"]
            if chat_id not in grouped:  # First message = most recent due to sort
                grouped[chat_id] = item

        chat_summaries = [
            {
                "chat_id": chat_id,
                "title": grouped[chat_id]["content"][:50] + "...",
                "timestamp": grouped[chat_id]["timestamp"]
            }
            for chat_id in grouped
        ]

        return chat_summaries

    except Exception as e:
        logger.error(f"Error in /chat/all: {str(e)}")
        return create_response(500, "error_fetch_items", "Error")

@chat_router.get("/history/")
async def get_chat_history(chat_id: str):

    try:
        response = dynamo_db.query(
            KeyConditionExpression=Key("chat_id").eq(chat_id),
            FilterExpression=Attr("is_active").eq(1),
            ScanIndexForward=True
        )

        # Sort by timestamp
        return response.get("Items", [])

    except Exception as e:
        logger.error(f"Error in /chat/history: {str(e)}")
        return create_response(500, "error_fetch_items", "Error")

# === 5. FastAPI Endpoint ===
@chat_router.post('/ask')
async def ask_streaming_agent(user_chat_data: UserChatRequest, db: Session = Depends(get_db_connection)):
    try:
        print(f"\n{'='*60}")
        print(f"📨 New request received")
        print(f"{'='*60}")
        
        # 🧑‍💼 Get user ID from context
        user_context = user_id_ctx.get()
        user_id = user_context.user_id
        print(f"👤 User ID: {user_id}")

        # 🔢 Chat ID Setup
        user_chat_count = db.query(UserChatCountModel).filter(UserChatCountModel.user_id == user_id).first()
        count = user_chat_count.count if user_chat_count else 0

        final_chat_id = user_chat_data.chat_id or f"user{user_id}-chat{count + 1}"
        timestamp = datetime.now(timezone.utc).isoformat()
        print(f"💬 Chat ID: {final_chat_id}")
        print(f"📝 User message: {user_chat_data.content[:100]}...")

        # 📝 Save user message
        user_msg = {
            "chat_id": final_chat_id,
            "timestamp": timestamp,
            "message_id": str(uuid4()),
            "role": "user",
            "user_id": user_id,
            "content": user_chat_data.content,
            "is_active": 1
        }
        dynamo_db.put_item(Item=user_msg)
        print("✅ User message saved to DynamoDB")

        async def event_stream():
            nonlocal user_chat_count
            
            print("\n🌊 Starting event stream...")
            
            # Send chat ID first
            yield f"__CHAT_ID__:{final_chat_id}\n"
            print(f"✅ Sent chat ID: {final_chat_id}")
            await asyncio.sleep(0.05)
            
            full_reply = ""
            
            try:
                # Route to appropriate agent
                print("🎯 Calling route_to_agent...")
                agent_name, response_generator = await route_to_agent(
                    user_chat_data.content, 
                    chat_id=final_chat_id
                )
                print(f"✅ Agent selected: {agent_name}")
                
                # Stream the response
                chunk_count = 0
                print("📤 Starting to stream chunks to client...")
                async for chunk in response_generator:
                    if chunk:  # Only yield non-empty chunks
                        yield chunk
                        full_reply += chunk
                        chunk_count += 1
                        
                        # Log progress every 50 chunks
                        if chunk_count % 50 == 0:
                            print(f"📊 Streamed {chunk_count} chunks so far...")
                
                print(f"✅ Streaming complete: {chunk_count} total chunks, {len(full_reply)} total chars")
                        
            except Exception as err:
                print(f"❌ Error in event_stream: {str(err)}")
                import traceback
                traceback.print_exc()
                error_msg = f"❌ Error: {str(err)}\n"
                yield error_msg
                full_reply = error_msg

            # 💬 Save assistant reply to Dynamo
            try:
                print("💾 Saving assistant message to DynamoDB...")
                assistant_msg = {
                    "chat_id": final_chat_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "message_id": str(uuid4()),
                    "role": "assistant",
                    "user_id": user_id,
                    "content": full_reply.strip(),
                    "is_active": 1
                }
                dynamo_db.put_item(Item=assistant_msg)
                print("✅ Assistant message saved to DynamoDB")
            except Exception as e:
                print(f"❌ Failed to save to DynamoDB: {str(e)}")

            # ➕ Update chat count
            try:
                if not user_chat_count:
                    user_chat_count = UserChatCountModel(user_id=user_id, count=1)
                    db.add(user_chat_count)
                else:
                    user_chat_count.count += 1
                db.commit()
                print(f"✅ Updated chat count for user {user_id}: {user_chat_count.count}")
            except Exception as e:
                print(f"❌ Failed to update chat count: {str(e)}")
            
            print(f"{'='*60}")
            print(f"✅ Request completed successfully")
            print(f"{'='*60}\n")

        return StreamingResponse(event_stream(), media_type="text/plain")

    except Exception as e:
        print(f"❌ Fatal error in /chat/ask: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    

@chat_router.get("/delete/{chat_id}")
async def delete_chat(chat_id: str):

    try:
        response = dynamo_db.query(
            KeyConditionExpression=Key("chat_id").eq(chat_id)
        )

        items = response.get("Items", [])
        for item in items:
            item["is_active"] = 0  # Soft delete
            dynamo_db.put_item(Item=item)

        return create_response(200, "chat_delete", "Success")

    except Exception as e:
        logger.error(f"Error in /chat/delete: {str(e)}")
        return create_response(500, "delete_item_failed", "Error")