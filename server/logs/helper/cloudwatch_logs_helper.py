# services/logs_service.py
import boto3
import json
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from typing import Dict, List, Tuple
from decimal import Decimal
import statistics
import asyncio
import re


class CloudWatchLogsService:
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CloudWatchLogsService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        self.logs_client = boto3.client('logs', region_name='us-east-2')
        self.ecs_client = boto3.client('ecs', region_name='us-east-2')
    
    @staticmethod
    def get_instance():
        if CloudWatchLogsService._instance is None:
            CloudWatchLogsService._instance = CloudWatchLogsService()
        return CloudWatchLogsService._instance
    
    def get_log_group_name(self, app_name: str, region: str = "us-east-2") -> str:
        """Get ECS log group name for app"""
        return f"/ecs/client"
    
    async def query_logs(
        self,
        log_group: str,
        limit: int = 100
    ):
    
        log_group = "/ecs/client"
        start_time = int((datetime.utcnow() - timedelta(days=1)).timestamp())
        end_time = int(datetime.utcnow().timestamp())

        query = """
            fields @timestamp, @message
            | filter @message like /HTTP/
            | sort @timestamp desc
            | limit 100
        """

        response = self.logs_client.start_query(
            logGroupName=log_group,
            startTime=start_time,
            endTime=end_time,
            queryString=query,
            limit=limit
        )
        
        query_id = response["queryId"]

        while True:
            result = self.logs_client.get_query_results(queryId=query_id)
            
            if result["status"] == "Complete":
                # Parse and return individual logs
                parsed_logs = []
                for record in result["results"]:
                    log_data = {}
                    for field in record:
                        log_data[field["field"]] = field["value"]
                    
                    message = log_data.get("@message", "")
                    parsed = self._parse_http_message(message)
                    parsed['@timestamp'] = log_data.get("@timestamp")
                    parsed['@message'] = message
                    
                    parsed_logs.append(parsed)
                
                return parsed_logs

            if result["status"] in ["Failed", "Cancelled", "Timeout"]:
                raise Exception(f"Query failed: {result['status']}")

            await asyncio.sleep(1)

    def _parse_http_message(self, message: str) -> Dict:
        """Parse: HTTP 11/22/2025 8:31:26 PM 58.8.0.218 Returned 200 in 2 ms"""
        
        parsed = {}
        
        status_match = re.search(r'Returned (\d{3})', message)
        if status_match:
            parsed['status_code'] = int(status_match.group(1))
        
        duration_match = re.search(r'in (\d+)\s*ms', message)
        if duration_match:
            parsed['duration_ms'] = int(duration_match.group(1))
        
        ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', message)
        if ip_match:
            parsed['client_ip'] = ip_match.group(1)
        
        return parsed
    
    async def extract_metrics(
        self,
        logs: List[Dict],
        time_window_minutes: int = 5
    ) -> Dict:
        """Extract metrics from CloudWatch logs"""
    
        print(f'[Metrics] Extracting metrics from {len(logs)} logs')
        
        if not logs:
            print('[Metrics] ❌ No logs provided, returning empty metrics')
            return self._empty_metrics()
        
        # Extract fields from logs
        status_codes = []
        response_times = []
        
        for log in logs:
            print(f'[Metrics] Processing log: {log}')
         
            status_code = log.get('status_code')
            duration_ms = log.get('duration_ms')
            
            if status_code is not None:
                status_codes.append(int(status_code))
            
            if duration_ms is not None:
                response_times.append(int(duration_ms))
        
        print(f'[Metrics] Parsed {len(status_codes)} status codes: {status_codes}')
        print(f'[Metrics] Parsed {len(response_times)} durations: {response_times}')
        
        # Calculate metrics
        success_count = len([s for s in status_codes if 200 <= s < 300])
        error_count = len([s for s in status_codes if s >= 400])
        total_requests = len(status_codes)
        
        print(f'[Metrics] Total requests: {total_requests}')
        print(f'[Metrics] Success count: {success_count}')
        print(f'[Metrics] Error count: {error_count}')
        
        # Calculate averages
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        metrics = {
            'total_requests': total_requests,
            'success_count': success_count,
            'error_count': error_count,
            'success_rate': (success_count / total_requests * 100) if total_requests > 0 else 0,
            'error_rate': (error_count / total_requests * 100) if total_requests > 0 else 0,
            'avg_response_time_ms': avg_response_time,
            'p95_response_time_ms': sorted(response_times)[int(len(response_times) * 0.95)] if len(response_times) > 1 else 0,
            'p99_response_time_ms': sorted(response_times)[int(len(response_times) * 0.99)] if len(response_times) > 1 else 0,
            'requests_per_minute': total_requests / (time_window_minutes or 1),
            'status_code_distribution': {str(code): Decimal(str(count)) for code, count in Counter(status_codes).items()},
            'top_errors': [],
            'timestamp': datetime.utcnow().isoformat()
        }
        
        print(f'[Metrics] ✅ Extracted metrics: {metrics}')
        return metrics

    def _empty_metrics(self) -> Dict:
        return {
            'total_requests': 0,
            'success_count': 0,
            'error_count': 0,
            'success_rate': 0,
            'error_rate': 0,
            'avg_response_time_ms': 0,
            'p95_response_time_ms': 0,
            'p99_response_time_ms': 0,
            'requests_per_minute': 0,
            'status_code_distribution': {},
            'top_errors': [],
            'timestamp': datetime.utcnow().isoformat()
        }
    
    async def get_ecs_health(
        self,
        cluster_name: str,
        service_name: str
    ) -> Dict:
        """Get ECS service health"""
        
        try:
            response = self.ecs_client.describe_services(
                cluster=cluster_name,
                services=[service_name]
            )
            
            if not response['services']:
                return {'status': 'unknown', 'running_count': 0}
            
            service = response['services'][0]
            
            return {
                'status': 'healthy' if service['runningCount'] > 0 else 'unhealthy',
                'running_count': service['runningCount'],
                'desired_count': service['desiredCount'],
                'pending_count': service['pendingCount'],
                'deployment_status': service['deployments'][0]['status'] if service['deployments'] else 'unknown'
            }
        except Exception as e:
            return {'status': 'unknown', 'error': str(e)}