import json
from chat.dynamo_instance import DynamoDBConnection

chat_sessions_model = DynamoDBConnection.get_instance().get_table('chat-sessions')

# === Helper Functions for Session Management ===
def get_session_context(chat_id: str) -> dict:
    """Retrieve session context from DynamoDB"""
    try:
        response = chat_sessions_model.get_item(Key={'chat_id': chat_id})
        
        if 'Item' in response:
            context = response['Item']
            
            # Deserialize the 'data' field if it exists
            if 'data' in context and isinstance(context['data'], str):
                context['data'] = json.loads(context['data'])
            
            print(f"📦 Retrieved session: {list(context.keys())}")
            if 'data' in context:
                print(f"   Data keys: {list(context['data'].keys())}")
            
            return context
        
        print(f"📭 No session found for chat_id: {chat_id}")
        return {}
        
    except Exception as e:
        print(f"⚠️ Error loading session context: {e}")
        import traceback
        traceback.print_exc()
        return {}


def save_session_context(chat_id: str, context: dict):
    """Save session context to DynamoDB"""
    try:
        # Structure: Store everything under 'data' key
        item = {
            'chat_id': chat_id,
            'last_agent': context.get('last_agent', 'unknown'),
            'data': json.dumps(context.get('data', {}))  # Serialize data object
        }
        
        chat_sessions_model.put_item(Item=item)
        print(f"💾 Session context saved for {chat_id}")
        print(f"   Last agent: {item['last_agent']}")
        
    except Exception as e:
        print(f"❌ Error saving session context: {e}")
        import traceback
        traceback.print_exc()


def update_session_field(chat_id: str, field_path: str, value):
    """
    Update a specific field in session context
    
    Args:
        chat_id: Chat identifier
        field_path: Dot notation path (e.g., 'data.repo_data' or 'data.terraform_config')
        value: Value to set
    """
    try:
        context = get_session_context(chat_id)
        
        # Ensure data object exists
        if 'data' not in context:
            context['data'] = {}
        
        # Parse field path and update
        keys = field_path.split('.')
        
        if keys[0] == 'data':
            # Navigate to the correct nested location
            target = context['data']
            for key in keys[1:-1]:
                if key not in target:
                    target[key] = {}
                target = target[key]
            
            # Set the final value
            target[keys[-1]] = value
        else:
            # Direct field update (like last_agent)
            context[field_path] = value
        
        save_session_context(chat_id, context)
        print(f"✅ Updated {field_path} for {chat_id}")
        
    except Exception as e:
        print(f"❌ Error updating session field: {e}")
        import traceback
        traceback.print_exc()