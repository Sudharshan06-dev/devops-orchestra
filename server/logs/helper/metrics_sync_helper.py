# services/metrics_sync_service.py
from fastapi import Depends
from chat.models.DeploymentManager import DeploymentManager
from logs.helper.cloudwatch_logs_helper import CloudWatchLogsService
import aiocache
from decimal import Decimal
from typing import Dict
'''
from typing import List
from sqlalchemy.orm import Session
import asyncio
from datetime import datetime, timedelta
from auth.models.UserModel import UserModel, UserTokenModel
from config.database import get_db_connection
'''

class MetricsSyncService:
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MetricsSyncService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.deployment_manager = DeploymentManager.get_deployment_manager_instance()
            self.logs_service = CloudWatchLogsService.get_instance()
            self.cache = aiocache.Cache(aiocache.Cache.MEMORY)
            self.initialized = True
    
    @staticmethod
    def get_instance():
        if MetricsSyncService._instance is None:
            MetricsSyncService._instance = MetricsSyncService()
        return MetricsSyncService._instance
    
    async def sync_metrics_for_deployment(
        self,
        user_id: str,
        deployment_id: str,
        deployment: Dict
    ):
        """Sync metrics for single deployment"""

        try:
            log_group = deployment.get('log_group_name', '/ecs/client')
            
            logs = await self.logs_service.query_logs(
                log_group=log_group,
            )
            
            # Extract metrics
            metrics = await self.logs_service.extract_metrics(logs)
            print(f'[SyncMetrics] Extracted metrics: {metrics}')
            
            # Get ECS health
            health = await self.logs_service.get_ecs_health(
                cluster_name=deployment.get('ecs_cluster_name'),
                service_name=deployment.get('ecs_service_name')
            )
            print(f'[SyncMetrics] ECS health: {health}')
            
            # Update DynamoDB
            metrics['health_status'] = health['status']
            metrics['ecs_health'] = health
            metrics = self._convert_to_decimal(metrics)  
            
            await self.deployment_manager.update_deployment_metrics(
                user_id=user_id,
                deployment_id=deployment_id,
                metrics=metrics
            )
            
            print(f'[SyncMetrics] ✅ SYNC COMPLETE')
            
        except Exception as e:
            print(f'[SyncMetrics] ❌ ERROR: {str(e)}')
            import traceback
            traceback.print_exc()
            

    def _convert_to_decimal(self, obj):
        """Convert floats to Decimal for DynamoDB"""
        if isinstance(obj, dict):
            return {k: self._convert_to_decimal(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_to_decimal(item) for item in obj]
        elif isinstance(obj, float):
            return Decimal(str(obj))  # Convert float to Decimal
        elif isinstance(obj, int):
            return Decimal(str(obj))
        
        return obj
        