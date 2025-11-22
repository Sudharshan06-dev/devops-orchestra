# routes/deployments.py
from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from chat.models.DeploymentManager import DeploymentManager
from typing import List, Dict
from datetime import datetime, timedelta
from logs.helper.cloudwatch_logs_helper import CloudWatchLogsService
from logs.helper.metrics_sync_helper import MetricsSyncService
from logs.services import deployments_router
import logging

# Get singleton instances once at module load
deployment_manager = DeploymentManager.get_deployment_manager_instance()
logs_service = CloudWatchLogsService.get_instance()
sync_service = MetricsSyncService.get_instance()

logger = logging.getLogger(__name__)

@deployments_router.post("/update-deployment")
async def create_new_deployment(request: Request, deployment_data: Dict = None):
    """
    Create deployment record from shell script
    Called via curl from deploy.sh after CDK deploy succeeds
    """
    
    try:
        # If deployment_data not passed, try to get from request body
        if deployment_data is None:
            deployment_data = await request.json()
        
        # Extract from request body
        chat_id = deployment_data.get('chat_id')
        user_id = deployment_data.get('user_id')
        
        if not chat_id or not user_id:
            return {
                "status": 400,
                "message": "chat_id and user_id required"
            }
        
        # Create deployment record
        response = await DeploymentManager.get_deployment_manager_instance().create_deployment(
            user_id=user_id,
            chat_id=chat_id,
            deployment_data=deployment_data
        )
        
        if not response:
            return {
                "status": 500,
                "message": "Failed to create deployment record"
            }
        
        return {
            "status": 200,
            "message": "Deployment created successfully",
            "deployment_id": response.get('deployment_id')
        }
        
    except Exception as e:
        logger.error(f"Error creating deployment: {str(e)}")
        return {
            "status": 500,
            "message": str(e)
        }
            

@deployments_router.get("/{user_id}")
async def get_user_deployments(user_id: str):
    """Get all deployments for user"""
    
    deployments = await deployment_manager.get_user_deployments(user_id)
    
    return {
        "count": len(deployments),
        "deployments": deployments
    }

@deployments_router.get("/{user_id}/{deployment_id}")
async def get_deployment_details(user_id: str, deployment_id: str):
    """Get full deployment details with latest metrics"""
    
    deployment = await deployment_manager.get_deployment(user_id, deployment_id)
    
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    return deployment

@deployments_router.get("/{user_id}/{deployment_id}/metrics")
async def get_deployment_metrics(user_id: str, deployment_id: str):
    """Get latest metrics (from cache if available)"""
    
    deployment = await deployment_manager.get_deployment(user_id, deployment_id)
    
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    return {
        "deployment_id": deployment_id,
        "app_name": deployment.get('app_name'),
        "metrics": deployment.get('metrics', {}),
        "health_status": deployment.get('health_status'),
        "last_updated": deployment.get('last_updated')
    }

@deployments_router.post("/{user_id}/{deployment_id}/sync-metrics")
async def trigger_metrics_sync(
    user_id: str,
    deployment_id: str,
    background_tasks: BackgroundTasks
):
    """Manually trigger metrics sync"""
    
    deployment = await deployment_manager.get_deployment(user_id, deployment_id)
    
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    background_tasks.add_task(
        sync_service.sync_metrics_for_deployment,
        user_id,
        deployment_id,
        deployment
    )
    
    return {"status": "sync_started"}

@deployments_router.get("/{user_id}/{deployment_id}/logs")
async def get_deployment_logs(
    user_id: str,
    deployment_id: str,
    limit: int = 100
):
    """Get recent logs for deployment"""
    
    deployment = await deployment_manager.get_deployment(user_id, deployment_id)
    
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    log_group = logs_service.get_log_group_name(deployment['app_name'])
    
    logs = await logs_service.query_logs(log_group, limit)
    
    return {
        "deployment_id": deployment_id,
        "app_name": deployment['app_name'],
        "log_count": len(logs),
        "logs": logs
    }