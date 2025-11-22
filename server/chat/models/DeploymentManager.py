# models/deployment.py
from datetime import datetime
from typing import Optional, List, Dict
from config.dynamo_instance import DynamoDBConnection
from boto3.dynamodb.conditions import Key, Attr
import uuid
from datetime import datetime, timezone

class DeploymentManager:
    
    _instance = None
    
    def __new__(cls):
        """Ensure only one instance exists"""
        if cls._instance is None:
            cls._instance = super(DeploymentManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        self.table = DynamoDBConnection.get_instance().get_table('deployments_manager')
    
    @staticmethod
    def get_deployment_manager_instance():
        """Get singleton instance (static method - no self parameter)"""
        if DeploymentManager._instance is None:
            DeploymentManager._instance = DeploymentManager()
        return DeploymentManager._instance
            

    async def create_deployment(
        self,
        user_id: str,
        chat_id: str,
        deployment_data: Dict
    ) -> str:
        """Create new deployment record"""
        
        deployment_id = f"dep-{uuid.uuid4().hex[:8]}"
        
        item = {
            'user_id': user_id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'deployment_id': deployment_id,
            'chat_id': chat_id,
            'app_name': deployment_data.get('app_name', 'unnamed-app'),
            'repo_url': deployment_data.get('repo_url'),
            'alb_dns': deployment_data.get('alb_dns'),
            'alb_arn': deployment_data.get('alb_arn'),
            'app_url': deployment_data.get('app_url'),
            'ecs_cluster_name': deployment_data.get('ecs_cluster_name'),
            'ecs_service_name': deployment_data.get('ecs_service_name'),
            'task_definition_arn': deployment_data.get('task_definition_arn'),
            'ecr_image_uri': deployment_data.get('ecr_image_uri'),
            'status': 'live',
            'health_status': 'unknown',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'deployed_at': datetime.now(timezone.utc).isoformat(),
            'last_updated': datetime.now(timezone.utc).isoformat(),
            'tech_stack': deployment_data.get('tech_stack', {}),
            'metrics': {
                'total_requests': 0,
                'error_count': 0,
                'avg_response_time_ms': 0,
                'last_sync': datetime.now(timezone.utc).isoformat(),
            }
        }
        
        self.table.put_item(Item=item)
        return { "deployment_id": deployment_id }
    
    async def get_user_deployments(self, user_id: str) -> List[Dict]:
        """Get all deployments for a user"""
        
        response = self.table.query(
            KeyConditionExpression=Key("user_id").eq(user_id),
            ScanIndexForward=False
        )
        
        return response.get('Items', [])
    
    async def get_deployment(self, user_id: str, deployment_id: str) -> Optional[Dict]:
        """Get single deployment"""
        
        response = self.table.get_item(
            Key={'user_id': user_id, 'deployment_id': deployment_id}
        )
        
        return response.get('Item')
    
    async def update_deployment_metrics(
        self,
        user_id: str,
        deployment_id: str,
        metrics: Dict
    ):
        """Update deployment metrics"""
        
        print(f'[DeploymentManager] Updating metrics for {deployment_id}')
        
        try:
            self.table.update_item(
                Key={'user_id': user_id, 'deployment_id': deployment_id},
                UpdateExpression='SET #m = :m, #ts = :ts',  # Use #m instead of metrics
                ExpressionAttributeNames={
                    '#m': 'metrics',      # Map #m to 'metrics'
                    '#ts': 'last_updated'  # Map #ts to 'last_updated'
                },
                ExpressionAttributeValues={
                    ':m': metrics,
                    ':ts': datetime.utcnow().isoformat()
                }
            )
            print(f'[DeploymentManager] ✅ Metrics updated successfully')
        except Exception as e:
            print(f'[DeploymentManager] ❌ Error updating metrics: {str(e)}')
            raise
    
    async def update_health_status(
        self,
        user_id: str,
        deployment_id: str,
        health_status: str
    ):
        """Update health status"""
        
        self.table.update_item(
            Key={'user_id': user_id, 'deployment_id': deployment_id},
            UpdateExpression='SET health_status = :hs, last_updated = :ts',
            ExpressionAttributeValues={
                ':hs': health_status,
                ':ts': datetime.utcnow().isoformat()
            }
        )