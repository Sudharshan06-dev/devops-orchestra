from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from config.database import get_db_connection
from chat import chat_router
from chat.schemas.user_chat_schema import UserChatRequest, UserChatResponse
from chat.models.UserChatCount import UserChatCountModel
from agents.chat_agent import generate_assistant_reply
from core.utility import create_response
from uuid import uuid4
from chat.dynamo_instance import DynamoDBConnection
from core.context_vars import user_id_ctx
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key, Attr
import logging


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
            FilterExpression=Attr("is_active").eq(1),
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

@chat_router.get("/history/{chat_id}")
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
    


@chat_router.post('/ask', response_model=UserChatResponse)
async def ask_assistant(user_chat_data: UserChatRequest, db: Session = Depends(get_db_connection)):
    try:
        user_context = user_id_ctx.get()
        if not user_context or not hasattr(user_context, 'user_id'):
            raise HTTPException(status_code=401, detail="User not authenticated")
    
        user_id = user_context.user_id
    
        # Get user's message count for chat_id generation
        user_chat_count = db.query(UserChatCountModel).filter(
            UserChatCountModel.user_id == user_id
        ).first()
        
        count = 0
        if user_chat_count and user_chat_count.count:
            count = user_chat_count.count

        chat_id = f"user{user_id}-chat{count + 1}"
        timestamp = datetime.now(timezone.utc).isoformat()

        # 1. Store User Message
        user_message = {
            "chat_id": chat_id,
            "timestamp": timestamp,
            "message_id": str(uuid4()),
            "role": "user",
            "user_id": user_id,
            "content": user_chat_data.content,
            "is_active": 1
        }
        dynamo_db.put_item(Item=user_message)

        # 2. Get AI response - Add await here
        assistant_text = await generate_assistant_reply(user_chat_data.content)

        # 3. Store Assistant Message
        assistant_message = {
            "chat_id": chat_id,
            "timestamp": timestamp,
            "message_id": str(uuid4()),
            "role": "assistant",
            "user_id": user_id,
            "content": assistant_text,
            "is_active": 1
        }
        dynamo_db.put_item(Item=assistant_message)

        # 4. Increment count
        if not user_chat_count:
            user_chat_count = UserChatCountModel(user_id=user_id, count=1)
            db.add(user_chat_count)
        else:
            user_chat_count.count += 1
        db.commit()

        # 5. Respond
        return UserChatResponse.model_validate(assistant_message)

    except Exception as e:
        logger.error(f"Failed in /chat/ask: {str(e)}")
        db.rollback()  # Rollback on error
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