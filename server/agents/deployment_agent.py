from ollama import AsyncClient
import os
import asyncio
import uuid
import json
from datetime import datetime, timezone
from uuid import uuid4
from pathlib import Path
from chat.models.ChatSessions import update_session_field
from chat.dynamo_instance import DynamoDBConnection
from typing import Dict, List
from .cdk_generator import CDKGenerator
from .docker_templates import generate_dockerfile_from_analysis

OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL')
OLLAMA_CHAT_MODEL = os.getenv('OLLAMA_CHAT_MODEL')
DEPLOYMENT_OUTPUT_DIR = os.getenv("DEPLOYMENT_OUTPUT_DIR", "./generated_deployments")

ollama_client = AsyncClient(host=OLLAMA_BASE_URL)
user_chat_model = DynamoDBConnection.get_instance().get_table()
cdk_generator = CDKGenerator()


async def deployment_generator(repo_data: dict = None, chat_id: str = "default", user_id: int = None):
    job_id = str(uuid.uuid4())
    update_session_field(chat_id, 'data.deployment_config.job_id', job_id)
    update_session_field(chat_id, 'data.deployment_config.status', 'generating')

    # Create task and keep reference
    task = asyncio.create_task(
        _generate_deployment_in_background(job_id, repo_data, chat_id, user_id)
    )

    yield f"🚀 **Generating Deployment Configuration...**\n\n"
    yield f"📋 Job ID: `{job_id}`\n\n"
    
    analysis = repo_data.get('analysis', {})
    repo_type = analysis.get('repo_type', 'single')
    
    if repo_type == 'monorepo':
        services = analysis.get('services', [])
        yield f"📦 **Monorepo Detected:** {len(services)} services\n\n"
        
        for idx, service in enumerate(services, 1):
            tech = service.get('tech_stack', {})
            port = service.get('server_config', {}).get('port', 'N/A')
            yield f"**Service {idx}: {service.get('name')}**\n"
            yield f"- Type: {service.get('type')}\n"
            yield f"- Runtime: {tech.get('runtime')} {tech.get('version')}\n"
            yield f"- Frameworks: {', '.join(tech.get('frameworks', []))}\n"
            yield f"- Port: {port}\n\n"
        
        yield f"📝 Generating:\n"
        yield f"- {len(services)} Dockerfiles (one per service)\n"
        yield f"- AWS CDK with {len(services)} ECS services\n"
        yield f"- Application Load Balancer with path-based routing\n"
    else:
        primary = analysis.get('primary_service', {})

        if not primary:
            yield "❌ No service detected in repository\n"
            return

        tech_stack = primary.get('tech_stack', {})
        port = primary.get('server_config', {}).get('port', 8000)
        service_type = primary.get('type', 'unknown')
        frameworks = tech_stack.get('frameworks', [])

        if service_type == 'frontend':
            app_type = 'Frontend'
        elif service_type == 'backend':
            app_type = 'Backend'
        elif service_type == 'fullstack':
            app_type = 'Fullstack'
        else:
            app_type = tech_stack.get('backend') or tech_stack.get('frontend') or 'Application'
            app_type = app_type.upper() if isinstance(app_type, str) else 'Application'

        yield f"📦 Detected: **{app_type}** application\n"
        yield f"🔌 Port: **{port}**\n"
        if frameworks:
            yield f"🔧 Framework: **{', '.join(frameworks)}**\n"
        yield f"\n📝 Creating:\n- Dockerfile\n- AWS CDK with ECS Fargate\n"
    
    yield f"\n⏱️ Generating files...\n"
    
    # Wait for background task to complete
    try:
        output_dir = await task
        
        # Send files/links to user
        yield f"\n✅ **Generation Complete!**\n\n"
        yield f"📁 **Output Directory:** `{output_dir}`\n\n"
        yield f"**Generated Files:**\n"
        yield f"- Dockerfile\n"
        yield f"- build-and-push.sh\n"
        yield f"- cdk/app.py\n"
        yield f"- cdk/infrastructure_stack.py\n"
        yield f"- cdk/requirements.txt\n"
        yield f"- cdk/cdk.json\n\n"
        yield f"**Next Steps:**\n"
        yield f"1. Download the files\n"
        yield f"2. Run: `./build-and-push.sh`\n"
        yield f"3. Your app will be live on AWS ECS!\n"
        
    except Exception as e:
        yield f"\n❌ **Generation Failed:** {str(e)}\n"


async def _generate_deployment_in_background(job_id: str, repo_data: dict, chat_id: str, user_id: int) -> str:
    """Generate deployment files and return output directory"""
    print(f'🔨 Starting deployment generation: {job_id}')

    analysis = repo_data.get('analysis', {})
    
    if not analysis:
        print("❌ No repo analysis found!")
        update_session_field(chat_id, 'data.deployment_config.status', 'failed')
        raise Exception("No repository analysis found")
    
    repo_type = analysis.get('repo_type', 'single')
    output_dir = Path(DEPLOYMENT_OUTPUT_DIR) / job_id
    output_dir.mkdir(parents=True, exist_ok=True)

    env_file_path = Path(f"./user_uploads/{user_id}/{chat_id}/.env")
    env_vars = {}
    if env_file_path.exists():
        for line in env_file_path.read_text().splitlines():
            if line and '=' in line and not line.strip().startswith('#'):
                k, v = line.split('=', 1)
                env_vars[k.strip()] = v.strip()
    
    try:
        if repo_type == 'monorepo':
            await _generate_monorepo_deployment(analysis, output_dir, env_vars, chat_id, job_id)
        else:
            await _generate_single_service_deployment(analysis, output_dir, env_vars, chat_id, job_id)
        
        # Generate build-and-push.sh script
        _generate_build_script(output_dir)
        
        update_session_field(chat_id, 'data.deployment_config.status', 'completed')
        print("✅ Deployment generation complete")
        
        return str(output_dir)  # Return output directory path
        
    except Exception as e:
        print(f"❌ Deployment generation failed: {e}")
        import traceback
        traceback.print_exc()
        update_session_field(chat_id, 'data.deployment_config.status', 'failed')
        update_session_field(chat_id, 'data.deployment_config.error', str(e))
        raise


def _generate_build_script(output_dir: Path):
    """Generate build-and-push.sh script"""
    script = '''#!/bin/bash
set -e

AWS_REGION=${AWS_REGION:-us-east-1}
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="sysconnect-app"
IMAGE_NAME="app"
IMAGE_TAG="latest"

echo "🐳 Building and pushing Docker image to ECR..."
echo "📍 Region: $AWS_REGION"
echo "📍 Account: $AWS_ACCOUNT_ID"

aws ecr describe-repositories \\
  --repository-names $ECR_REPO \\
  --region $AWS_REGION 2>/dev/null || \\
aws ecr create-repository \\
  --repository-name $ECR_REPO \\
  --region $AWS_REGION

aws ecr get-login-password --region $AWS_REGION | \\
  docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

echo "🔨 Building Docker image..."
docker build -t $IMAGE_NAME:$IMAGE_TAG .

docker tag $IMAGE_NAME:$IMAGE_TAG $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:$IMAGE_TAG

echo "📤 Pushing to ECR..."
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:$IMAGE_TAG

echo "✅ Image pushed successfully!"

read -p "Deploy to AWS? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
  cd cdk
  cdk deploy --require-approval=never
  cd ..
  echo "🚀 Deployment complete!"
fi
'''
    
    script_path = output_dir / "build-and-push.sh"
    script_path.write_text(script)
    script_path.chmod(0o755)  # Make executable
    print(f"✅ Generated build-and-push.sh")


async def _generate_monorepo_deployment(analysis: Dict, output_dir: Path, env_vars: Dict, chat_id: str, job_id: str):
    """Generate deployment for monorepo"""
    services = analysis.get('services', [])
    print(f"📦 Generating monorepo deployment for {len(services)} services")
    
    service_configs = []
    
    for service in services:
        service_name = service.get('name')
        service_path = service.get('path')
        service_type = service.get('type')
        
        print(f"📝 Generating Dockerfile for service: {service_name}")
        
        service_analysis = {
            'tech_stack': service.get('tech_stack', {}),
            'port': service.get('server_config', {}),
            'build_info': service.get('build_system', {}),
            'package_manager': service.get('build_system', {}).get('package_manager', 'pip'),
            'database': service.get('database', {}),
            'entry_point': service.get('server_config', {}).get('entry_point', 'main.py')
        }
        
        try:
            dockerfile_content = generate_dockerfile_from_analysis(service_analysis)
            dockerfile_content = _adjust_dockerfile_for_monorepo(dockerfile_content, service_path)
            
            dockerfile_path = output_dir / f"Dockerfile.{service_name}"
            dockerfile_path.write_text(dockerfile_content)
            
            # For frontend services in production, use port 80 with nginx
            deployment_port = 80 if service_type == 'frontend' else service.get('server_config', {}).get('port', 8000)
            
            service_configs.append({
                'name': service_name,
                'type': service_type,
                'port': deployment_port,
                'path': service_path,
                'dockerfile': f"Dockerfile.{service_name}",
                'container_port': service.get('server_config', {}).get('port', 8000),
                'memory_mib': 512,
                'cpu': 256,
                'needs_database': service.get('database', {}).get('needs_database', False),
                'db_type': service.get('database', {}).get('type', 'postgres')
            })
            
            print(f"✅ Dockerfile for {service_name} saved")
            
        except Exception as e:
            print(f"❌ Failed to generate Dockerfile for {service_name}: {e}")
            raise
    
    print("📝 Generating multi-service CDK infrastructure...")
    cdk_files = cdk_generator.generate_monorepo_cdk(
        chat_id=chat_id,
        services=service_configs,
        env_vars=env_vars
    )
    
    cdk_dir = output_dir / "cdk"
    cdk_dir.mkdir(exist_ok=True)
    for filename, content in cdk_files.items():
        (cdk_dir / filename).write_text(content)
        print(f"  ✅ Created {filename}")
    
    completion_msg = {
        'chat_id': chat_id,
        'message_id': str(uuid4()),
        'type': 'assistant',
        'content': f"""✅ **Monorepo Deployment Generated!**

📁 **Output:** `{output_dir}`

**Generated {len(services)} Dockerfiles:**
{chr(10).join([f"- `Dockerfile.{s['name']}` ({s['type']}, port {s['port']})" for s in service_configs])}

**AWS CDK Infrastructure:**
- Multi-service ECS cluster
- {len(services)} Fargate services
- Application Load Balancer with path routing
- CloudWatch logging

**Deploy:**
```bash
cd {output_dir}/cdk
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cdk bootstrap
cdk deploy
```

🚀 All services will be deployed to AWS ECS!
""",
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'metadata': {'job_id': job_id, 'repo_type': 'monorepo', 'services': len(services)}
    }
    
    user_chat_model.put_item(Item=completion_msg)


async def _generate_single_service_deployment(analysis: Dict, output_dir: Path, env_vars: Dict, chat_id: str, job_id: str):
    """Generate deployment for single service"""
    print("📝 Generating single-service deployment")
    
    primary = analysis.get('primary_service', {})
    
    service_analysis = {
        'tech_stack': primary.get('tech_stack', {}),
        'port': primary.get('server_config', {}),
        'build_info': primary.get('build_system', {}),
        'package_manager': primary.get('build_system', {}).get('package_manager', 'pip'),
        'database': primary.get('database', {}),
        'entry_point': primary.get('server_config', {}).get('entry_point', 'main.py')
    }
    
    dockerfile_content = generate_dockerfile_from_analysis(service_analysis)
    dockerfile_path = output_dir / "Dockerfile"
    dockerfile_path.write_text(dockerfile_content)
    print(f"✅ Generated Dockerfile")
    
    port = primary.get('server_config', {}).get('port', 8000)
    service_type = primary.get('type', 'backend')
    
    service_config = {
        'name': primary.get('name', 'app'),
        'type': service_type,
        'port': port,
        'dockerfile': 'Dockerfile',
        'container_port': port,
        'memory_mib': 512,
        'cpu': 256,
        'needs_database': primary.get('database', {}).get('needs_database', False),
        'database_type': primary.get('database', {}).get('type', 'postgres')
    }
    
    print("📝 Generating CDK infrastructure...")
    cdk_files = cdk_generator.generate_single_service_cdk(
        chat_id=chat_id,
        service=service_config,
        env_vars=env_vars
    )
    
    cdk_dir = output_dir / "cdk"
    cdk_dir.mkdir(exist_ok=True)
    for filename, content in cdk_files.items():
        (cdk_dir / filename).write_text(content)
        print(f"  ✅ Created {filename}")
    
    completion_msg = {
        'chat_id': chat_id,
        'message_id': str(uuid4()),
        'type': 'assistant',
        'content': f"""✅ **Deployment Configuration Generated!**

📁 **Output:** `{output_dir}`

**Generated:**
- Dockerfile (production-ready)
- AWS CDK Infrastructure

**Configuration:**
- Service: {service_config['name']} ({service_config['type']})
- Port: {port}
- Database: {'Yes' if service_config['needs_database'] else 'No'}

**Deploy:**
```bash
cd {output_dir}/cdk
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cdk bootstrap
cdk deploy
```
""",
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'metadata': {'job_id': job_id, 'repo_type': 'single'}
    }
    
    user_chat_model.put_item(Item=completion_msg)


def _adjust_dockerfile_for_monorepo(dockerfile: str, service_path: str) -> str:
    """Adjust COPY commands for monorepo structure"""
    lines = []
    for line in dockerfile.split('\n'):
        if line.strip().startswith('COPY') and not line.strip().startswith('COPY --from'):
            parts = line.split()
            if len(parts) >= 3:
                source = parts[1]
                if not source.startswith(service_path) and not source.startswith('/'):
                    parts[1] = f"{service_path}/{source}"
                line = ' '.join(parts)
        
        if line.strip().startswith('WORKDIR /app'):
            line = f'WORKDIR /app/{service_path}'
        
        lines.append(line)
    
    return '\n'.join(lines)