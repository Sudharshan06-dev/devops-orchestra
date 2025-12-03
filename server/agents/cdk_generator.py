from typing import Dict, List, Optional
import json


class CDKGenerator:
    """Generate AWS CDK infrastructure code"""
    
    def generate_single_service_cdk(
        self,
        chat_id: str,
        service: Dict,
        ecr_image_uri: str,
        env_vars: Optional[Dict] = None
    ) -> Dict[str, str]:
        """Generate CDK stack for single service"""
        env_vars = env_vars or {}
        
        return {
            'app.py': self._get_app_py(chat_id),
            'infrastructure_stack.py': self._get_single_service_infrastructure_stack(
                service, 
                ecr_image_uri, 
                env_vars
            ),
            'requirements.txt': self._get_requirements_txt(),
            'cdk.json': self._get_cdk_json()
        }
    
    def generate_monorepo_cdk(
        self,
        chat_id: str,
        services: List[Dict],
        ecr_image_uris: Dict,
        env_vars: Optional[Dict] = None
    ) -> Dict[str, str]:
        """Generate CDK stack for monorepo with multiple services"""
        env_vars = env_vars or {}
        
        return {
            'app.py': self._get_app_py(chat_id),
            'infrastructure_stack.py': self._get_monorepo_infrastructure_stack(
                services,
                ecr_image_uris,
                env_vars
            ),
            'requirements.txt': self._get_requirements_txt(),
            'cdk.json': self._get_cdk_json()
        }
    
    def _get_app_py(self, chat_id: str) -> str:
        """Return app.py - CDK app entry point"""
        return f'''#!/usr/bin/env python3
import os
import aws_cdk as cdk
from infrastructure_stack import InfrastructureStack

app = cdk.App()
InfrastructureStack(
    app,
    "AppStack",
    stack_name="devops-orchestra-{chat_id[:8]}",
    env=cdk.Environment(
        account=os.getenv('CDK_DEFAULT_ACCOUNT'),
        region=os.getenv('CDK_DEFAULT_REGION', 'us-east-2')
    )
)
app.synth()
'''
    
    def _get_single_service_infrastructure_stack(
        self,
        service: Dict,
        ecr_image_uri: str,
        env_vars: Dict
    ) -> str:
        """Generate infrastructure stack for single service"""
        
        service_name = service.get('name', 'app')
        port = service.get('port', 3000)
        memory = service.get('memory_mib', 512)
        cpu = service.get('cpu', 256)
        
        # Format environment variables as Python dict
        env_vars_str = "{\n" + "\n".join([
            f'            "{k}": "{v}",' for k, v in env_vars.items()
        ]) + "\n        }" if env_vars else "{}"
        
        return f'''from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_elasticloadbalancingv2 as elbv2,
    aws_iam as iam,
    aws_logs as logs,
    Duration,
    CfnOutput,
    RemovalPolicy
)
from constructs import Construct

class InfrastructureStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # VPC
        vpc = ec2.Vpc(
            self, "VPC",
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24
                )
            ]
        )
        
        # ECS Cluster
        cluster = ecs.Cluster(self, "Cluster", vpc=vpc)
        
        # Security Group
        sg = ec2.SecurityGroup(self, "AppSG", vpc=vpc, allow_all_outbound=True)
        sg.add_ingress_rule(peer=ec2.Peer.any_ipv4(), connection=ec2.Port.tcp({port}))
        sg.add_ingress_rule(peer=ec2.Peer.any_ipv4(), connection=ec2.Port.tcp(80))
        
        # CloudWatch Log Group
        log_group = logs.LogGroup(
            self, "LogGroup",
            log_group_name="/ecs/{service_name}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY
        )
        
        # Execution Role (for ECR pull permissions)
        execution_role = iam.Role(
            self, "ExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com")
        )
        execution_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AmazonECSTaskExecutionRolePolicy"
            )
        )
        execution_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "CloudWatchLogsFullAccess"
            )
        )
        
        # Task Definition
        task_def = ecs.FargateTaskDefinition(
            self, "TaskDef",
            memory_limit_mib={memory},
            cpu={cpu},
            execution_role=execution_role
        )
        
        # Container
        task_def.add_container(
            "Container",
            image=ecs.ContainerImage.from_registry("{ecr_image_uri}"),
            port_mappings=[ecs.PortMapping(container_port={port})],
            environment={env_vars_str},
            logging=ecs.LogDriver.aws_logs(
                log_group=log_group,
                stream_prefix="ecs"
            )
        )
        
        # ECS Service
        service = ecs.FargateService(
            self, "Service",
            cluster=cluster,
            task_definition=task_def,
            desired_count=1,
            security_groups=[sg],
            assign_public_ip=True,
            service_name="{service_name}"
        )
        
        # Application Load Balancer
        alb = elbv2.ApplicationLoadBalancer(
            self, "ALB",
            vpc=vpc,
            internet_facing=True
        )
        
        # Listener
        listener = alb.add_listener("Listener", port=80)
        
        # Target Group
        listener.add_targets(
            "Target",
            port={port},
            targets=[service],
            protocol=elbv2.ApplicationProtocol.HTTP,
            health_check=elbv2.HealthCheck(
                path="/",
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3
            )
        )
        
        # CloudFormation Outputs (IMPORTANT: These are exported for retrieval)
        CfnOutput(
            self, "ALBDNSName",
            value=alb.load_balancer_dns_name,
            export_name=f"{service_name}-alb-dns",
            description="ALB DNS Name for accessing the app"
        )
        
        CfnOutput(
            self, "ALBArn",
            value=alb.load_balancer_arn,
            export_name=f"{service_name}-alb-arn",
            description="ALB ARN"
        )
        
        CfnOutput(
            self, "LogGroupName",
            value=log_group.log_group_name,
            export_name=f"{service_name}-log-group",
            description="CloudWatch Log Group Name"
        )
        
        CfnOutput(
            self, "ServiceName",
            value=service.service_name,
            export_name=f"{service_name}-service-name",
            description="ECS Service Name"
        )
        
        CfnOutput(
            self, "ClusterName",
            value=cluster.cluster_name,
            export_name=f"{service_name}-cluster-name",
            description="ECS Cluster Name"
        )
        
        CfnOutput(
            self, "TaskDefinitionArn",
            value=task_def.task_definition_arn,
            export_name=f"{service_name}-task-def",
            description="Task Definition ARN"
        )
'''
    
    def _get_monorepo_infrastructure_stack(
        self,
        services: List[Dict],
        ecr_image_uris: Dict,
        env_vars: Dict
    ) -> str:
        """Generate infrastructure stack for monorepo"""
        
        # Generate service definitions
        service_defs = []
        routing_rules = []
        
        for idx, service in enumerate(services):
            service_name = service.get('name', f'service-{idx}')
            port = service.get('port', 3000 + idx)
            ecr_uri = ecr_image_uris.get(service_name, ecr_image_uris.get('default'))
            
            service_defs.append(self._generate_service_def(idx, service, ecr_uri, env_vars))
            routing_rules.append(self._generate_routing_rule(idx, service))
        
        services_code = "\n".join(service_defs)
        routing_code = "\n".join(routing_rules)
        
        return f'''from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_elasticloadbalancingv2 as elbv2,
    aws_iam as iam,
    aws_logs as logs,
    Duration,
    CfnOutput,
    RemovalPolicy
)
from constructs import Construct

class InfrastructureStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # VPC
        vpc = ec2.Vpc(
            self, "VPC",
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24
                )
            ]
        )
        
        # ECS Cluster
        cluster = ecs.Cluster(self, "Cluster", vpc=vpc)
        
        # Security Group
        sg = ec2.SecurityGroup(self, "AppSG", vpc=vpc, allow_all_outbound=True)
        sg.add_ingress_rule(peer=ec2.Peer.any_ipv4(), connection=ec2.Port.tcp(80))
        sg.add_ingress_rule(peer=ec2.Peer.any_ipv4(), connection=ec2.Port.tcp(443))
        
        # Execution Role
        execution_role = iam.Role(
            self, "ExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com")
        )
        execution_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AmazonECSTaskExecutionRolePolicy"
            )
        )
        execution_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "CloudWatchLogsFullAccess"
            )
        )
        
        # Load Balancer
        alb = elbv2.ApplicationLoadBalancer(
            self, "ALB",
            vpc=vpc,
            internet_facing=True
        )
        
        listener = alb.add_listener("Listener", port=80)
        
        # Services
{services_code}
        
        # Routing Rules
{routing_code}
        
        # Outputs
        CfnOutput(
            self, "ALBDNSName",
            value=alb.load_balancer_dns_name,
            description="ALB DNS Name"
        )
        
        CfnOutput(
            self, "ALBArn",
            value=alb.load_balancer_arn,
            description="ALB ARN"
        )
'''
    
    def _generate_service_def(
        self,
        idx: int,
        service: Dict,
        ecr_image_uri: str,
        env_vars: Dict
    ) -> str:
        """Generate service definition for monorepo"""
        
        service_name = service.get('name', f'service-{idx}')
        port = service.get('port', 3000 + idx)
        memory = service.get('memory_mib', 512)
        cpu = service.get('cpu', 256)
        
        # Format env vars
        env_vars_str = "{\n" + "\n".join([
            f'                "{k}": "{v}",' for k, v in env_vars.items()
        ]) + "\n            }" if env_vars else "{}"
        
        return f'''        # Service: {service_name}
        {service_name}_log_group = logs.LogGroup(
            self, "{service_name.capitalize()}LogGroup",
            log_group_name="/ecs/{service_name}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY
        )
        
        {service_name}_task_def = ecs.FargateTaskDefinition(
            self, "{service_name.capitalize()}Task",
            memory_limit_mib={memory},
            cpu={cpu},
            execution_role=execution_role
        )
        
        {service_name}_task_def.add_container(
            "{service_name}Container",
            image=ecs.ContainerImage.from_registry("{ecr_image_uri}"),
            port_mappings=[ecs.PortMapping(container_port={port})],
            environment={env_vars_str},
            logging=ecs.LogDriver.aws_logs(
                log_group={service_name}_log_group,
                stream_prefix="ecs"
            )
        )
        
        {service_name}_svc = ecs.FargateService(
            self, "{service_name.capitalize()}Service",
            cluster=cluster,
            task_definition={service_name}_task_def,
            desired_count=1,
            security_groups=[sg],
            assign_public_ip=True,
            service_name="{service_name}"
        )
        
        {service_name}_tg = elbv2.ApplicationTargetGroup(
            self, "{service_name.capitalize()}TG",
            vpc=vpc,
            port={port},
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.IP,
            health_check=elbv2.HealthCheck(
                path="/",
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3
            )
        )
        
        {service_name}_svc.attach_to_target_group({service_name}_tg)
        sg.add_ingress_rule(peer=ec2.Peer.any_ipv4(), connection=ec2.Port.tcp({port}))
'''
    
    def _generate_routing_rule(self, idx: int, service: Dict) -> str:
        """Generate ALB routing rule for monorepo service"""
        
        service_name = service.get('name', f'service-{idx}')
        path = service.get('path', f'/{service_name}')
        priority = 10 + (idx * 10)
        
        return f'''        listener.add_targets(
            "{service_name}Route",
            path_pattern="{path}/*",
            target_groups=[{service_name}_tg],
            priority={priority}
        )
'''
    
    def _get_requirements_txt(self) -> str:
        """Return requirements.txt for CDK"""
        return '''aws-cdk-lib==2.100.0
constructs>=10.0.0,<11.0.0
'''
    
    def _get_cdk_json(self) -> str:
        """Return cdk.json"""
        return json.dumps({"app": "python3 app.py", "context": {"@aws-cdk/core:newStyleStackSynthesis": True}}, indent=2)