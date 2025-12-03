from ollama import AsyncClient
import os
import asyncio
import uuid
import json
from datetime import datetime, timezone
from uuid import uuid4
from pathlib import Path
from chat.models.ChatSessions import update_session_field
from config.dynamo_instance import DynamoDBConnection
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
        yield f"1. Download the files to your repo root\n"
        yield f"2. Run the deployment with:\n"
        yield f"```bash\n"
        yield f"CHAT_ID={chat_id} \\\n"
        yield f"USER_ID={user_id} \\\n"
        yield f"API_URL=http://your-api-server:8000 \\\n"
        yield f"bash build-and-push.sh\n"
        yield f"```\n"
        yield f"3. Your app will be live on AWS ECS!\n"
        yield f"4. Check your dashboard to see deployment\n"
        
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
                
    app_name = repo_data.get('repo', 'MonoApp')
    
    try:
        if repo_type == 'monorepo':
            await _generate_monorepo_deployment(app_name, analysis, output_dir, env_vars, chat_id, job_id)
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
    script = '''
    
#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "🚀 Deploying to AWS..."

# Set region explicitly
export AWS_REGION=us-east-2

# Validate AWS credentials
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) || {
    echo "❌ AWS credentials not configured"
    echo "Run: aws configure"
    exit 1
}

AWS_REGION=${AWS_REGION:-us-east-2}
ECR_REPO=${ECR_REPO:-portfolio}

echo "📍 AWS Account: $AWS_ACCOUNT_ID"
echo "📍 Region: $AWS_REGION"
echo "📍 ECR Repo: $ECR_REPO"
echo ""

# ===== DETECT MONOREPO vs SINGLE SERVICE =====
echo "🔍 Detecting deployment structure..."

# Check if this is a monorepo (multiple Dockerfile.* files in root)
DOCKERFILES=$(find . -maxdepth 1 -name "Dockerfile.*" -type f | sort)
DOCKERFILE_COUNT=$(echo "$DOCKERFILES" | grep -c . || true)

if [ $DOCKERFILE_COUNT -gt 1 ]; then
    echo "📦 Monorepo detected! Found $DOCKERFILE_COUNT services"
    IS_MONOREPO=true
else
    echo "📦 Single service detected"
    IS_MONOREPO=false
    # For single service, check if Dockerfile exists
    if [ -f "Dockerfile" ]; then
        DOCKERFILES="./Dockerfile"
    elif [ -f "client/Dockerfile" ]; then
        DOCKERFILES="./client/Dockerfile"
    else
        echo "❌ No Dockerfile found!"
        exit 1
    fi
fi

# ===== BUILD AND PUSH DOCKER IMAGES =====

declare -A IMAGE_URIS
declare -a SERVICE_NAMES
declare -a SERVICE_PORTS

if [ "$IS_MONOREPO" = true ]; then
    # Monorepo: build each Dockerfile.<service>
    echo ""
    echo "🔨 Building monorepo services..."
    
    while IFS= read -r dockerfile; do
        # Extract service name from Dockerfile.server -> server
        service_name=$(basename "$dockerfile" | sed 's/Dockerfile\.//')
        
        # Determine build context
        if [ -d "$service_name" ]; then
            build_context="$service_name"
        else
            build_context="."
        fi
        
        # Determine port (read from service config if available)
        service_port="8000"
        if [ -f "deployment.config.json" ]; then
            service_port=$(grep -A5 "\"$service_name\"" deployment.config.json | grep "\"port\"" | grep -o '[0-9]*' | head -1 || echo "8000")
        fi
        
        echo ""
        echo "📦 Service: $service_name"
        echo "   📁 Context: $build_context"
        echo "   📄 Dockerfile: $dockerfile"
        echo "   🔌 Port: $service_port"
        
        # Create ECR repo if needed
        SERVICE_ECR_REPO="${ECR_REPO}-${service_name}"
        echo "🔧 Ensuring ECR repository exists: $SERVICE_ECR_REPO"
        aws ecr describe-repositories \
            --repository-names $SERVICE_ECR_REPO \
            --region $AWS_REGION 2>/dev/null || \
        aws ecr create-repository \
            --repository-name $SERVICE_ECR_REPO \
            --region $AWS_REGION >/dev/null
        
        # Build Docker image with amd64 platform
        echo "🔨 Building Docker image for $service_name (amd64)..."
        docker build --platform linux/amd64 \
            -t ${SERVICE_ECR_REPO}:latest \
            -f "$dockerfile" \
            "$build_context"
        
        # Tag for ECR
        IMAGE_URI="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/${SERVICE_ECR_REPO}:latest"
        docker tag ${SERVICE_ECR_REPO}:latest "$IMAGE_URI"
        
        # Push to ECR
        echo "📤 Pushing $service_name to ECR..."
        docker push "$IMAGE_URI"
        
        echo "✅ $service_name image pushed: $IMAGE_URI"
        
        # Store for later use
        IMAGE_URIS["$service_name"]="$IMAGE_URI"
        SERVICE_NAMES+=("$service_name")
        SERVICE_PORTS+=("$service_port")
        
    done <<< "$DOCKERFILES"
    
else
    # Single service: build traditional Dockerfile
    echo ""
    echo "🔨 Building single service..."
    
    # Determine build context
    if [ -f "client/Dockerfile" ]; then
        dockerfile="client/Dockerfile"
        build_context="client"
        service_name="client"
    else
        dockerfile="Dockerfile"
        build_context="."
        service_name="app"
    fi
    
    echo "📄 Dockerfile: $dockerfile"
    echo "📁 Context: $build_context"
    
    # Create ECR repo
    echo "🔧 Ensuring ECR repository exists: $ECR_REPO"
    aws ecr describe-repositories \
        --repository-names $ECR_REPO \
        --region $AWS_REGION 2>/dev/null || \
    aws ecr create-repository \
        --repository-name $ECR_REPO \
        --region $AWS_REGION >/dev/null
    
    # Login to ECR (single time for both mono and single)
    echo "🔐 Logging in to ECR..."
    aws ecr get-login-password --region $AWS_REGION | \
        docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
    
    # Build Docker image
    echo "🔨 Building Docker image (amd64)..."
    docker build --platform linux/amd64 \
        -t $ECR_REPO:latest \
        -f "$dockerfile" \
        "$build_context"
    
    # Tag for ECR
    IMAGE_URI="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:latest"
    docker tag $ECR_REPO:latest "$IMAGE_URI"
    
    # Push to ECR
    echo "📤 Pushing to ECR..."
    docker push "$IMAGE_URI"
    
    echo "✅ Image pushed: $IMAGE_URI"
    
    # Store for later use
    IMAGE_URIS["app"]="$IMAGE_URI"
    SERVICE_NAMES=("app")
    SERVICE_PORTS=("8000")
fi

# ===== LOGIN TO ECR (if monorepo) =====
if [ "$IS_MONOREPO" = true ]; then
    echo ""
    echo "🔐 Logging in to ECR..."
    aws ecr get-login-password --region $AWS_REGION | \
        docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
fi

# ===== DISPLAY SUMMARY =====
echo ""
echo "═════════════════════════════════════════"
echo "✅ All Docker images built and pushed!"
echo "═════════════════════════════════════════"
for service_name in "${SERVICE_NAMES[@]}"; do
    echo "📦 $service_name → ${IMAGE_URIS[$service_name]}"
done
echo "═════════════════════════════════════════"
echo ""

# ===== DEPLOY CDK =====
read -p "Deploy infrastructure to AWS? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "⚙️  Setting up CDK environment..."
    
    # Check if cdk folder exists in root
    if [ -d "cdk" ]; then
        cdk_dir="cdk"
    else
        # Fallback to client/cdk for single service
        cdk_dir="client/cdk"
    fi
    
    if [ ! -d "$cdk_dir" ]; then
        echo "❌ CDK directory not found at $cdk_dir"
        exit 1
    fi
    
    cd "$cdk_dir"
    
    if [ ! -d ".venv" ]; then
        echo "📦 Creating Python virtual environment..."
        python3 -m venv .venv
    fi
    
    # Activate venv
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
    elif [ -f ".venv/Scripts/activate" ]; then
        source .venv/Scripts/activate
    fi
    
    echo "📥 Installing CDK dependencies..."
    pip install -q -r requirements.txt 2>/dev/null || pip install -q aws-cdk-lib constructs
    
    echo "🔧 Bootstrapping CDK..."
    npx aws-cdk bootstrap aws://$AWS_ACCOUNT_ID/$AWS_REGION
    
    # ===== PASS IMAGE URIS TO CDK =====
    echo "🚀 Deploying CDK stack..."
    
    # Build environment variables for CDK
    CDK_CONTEXT=""
    for service_name in "${SERVICE_NAMES[@]}"; do
        image_uri="${IMAGE_URIS[$service_name]}"
        CDK_CONTEXT="$CDK_CONTEXT -c ${service_name}ImageUri=$image_uri"
    done
    
    # Run CDK with image URIs
    CDK_OUTPUT=$(npx aws-cdk deploy \
        --require-approval=never \
        --region $AWS_REGION \
        $CDK_CONTEXT 2>&1)
    
    cd ../..
    echo "✅ Infrastructure deployed!"
    
    # ===== EXTRACT DEPLOYMENT INFO =====
    echo ""
    echo "📊 Extracting deployment information..."
    
    ALB_DNS=$(echo "$CDK_OUTPUT" | grep -oP '(?<=ALBDNSName = ).*' | head -1 || echo "")
    LOG_GROUP=$(echo "$CDK_OUTPUT" | grep -oP '(?<=LogGroupName = ).*' | head -1 || echo "/ecs/$ECR_REPO")
    SERVICE_NAME=$(echo "$CDK_OUTPUT" | grep -oP '(?<=ServiceName = ).*' | head -1 || echo "$ECR_REPO")
    CLUSTER_NAME=$(echo "$CDK_OUTPUT" | grep -oP '(?<=ClusterName = ).*' | head -1 || echo "Cluster")
    
    # Fallback if not found in output
    if [ -z "$ALB_DNS" ]; then
        echo "🔍 Looking up ALB DNS from AWS..."
        ALB_DNS=$(aws elbv2 describe-load-balancers \
            --query "LoadBalancers[0].DNSName" \
            --output text \
            --region $AWS_REGION 2>/dev/null || echo "")
    fi
    
    echo ""
    echo "🎉 CDK Deployment Complete!"
    if [ -n "$ALB_DNS" ]; then
        echo "🌐 App URL: http://$ALB_DNS"
    fi
    echo "📊 Log Group: $LOG_GROUP"
    echo ""
    
    # ===== UPDATE DEPLOYMENT RECORD =====
    
    echo "📝 Registering deployment..."
    
    CHAT_ID=${CHAT_ID:-"default"}
    USER_ID=${USER_ID:-""}
    API_URL=${API_URL:-"http://localhost:8000"}
    
    # Build services array for JSON
    SERVICES_JSON="["
    for i in "${!SERVICE_NAMES[@]}"; do
        service_name="${SERVICE_NAMES[$i]}"
        image_uri="${IMAGE_URIS[$service_name]}"
        port="${SERVICE_PORTS[$i]}"
        
        if [ $i -gt 0 ]; then
            SERVICES_JSON="$SERVICES_JSON,"
        fi
        
        SERVICES_JSON="$SERVICES_JSON{\"name\":\"$service_name\",\"imageUri\":\"$image_uri\",\"port\":$port}"
    done
    SERVICES_JSON="$SERVICES_JSON]"
    
    # Prepare deployment data
    DEPLOYMENT_PAYLOAD=$(cat <<EOF
{
    "chat_id": "$CHAT_ID",
    "user_id": "$USER_ID",
    "app_name": "$ECR_REPO",
    "alb_dns": "$ALB_DNS",
    "alb_arn": "arn:aws:elasticloadbalancing:$AWS_REGION:$AWS_ACCOUNT_ID:loadbalancer/app/*",
    "app_url": "http://$ALB_DNS",
    "ecs_cluster_name": "$CLUSTER_NAME",
    "ecs_service_name": "$SERVICE_NAME",
    "ecr_image_uris": $SERVICES_JSON,
    "log_group_name": "$LOG_GROUP",
    "is_monorepo": $([[ "$IS_MONOREPO" = true ]] && echo "true" || echo "false"),
    "service_count": ${#SERVICE_NAMES[@]},
    "status": "live",
    "deployment_status_reason": "Successfully deployed via CDK"
}
EOF
)
    
    # Call deployment API endpoint
    echo "🔗 Sending deployment info to API..."
    RESPONSE=$(curl -s -X POST "$API_URL/deployments/update-deployment" \
        -H "Content-Type: application/json" \
        -d "$DEPLOYMENT_PAYLOAD")
    
    # Check response
    DEPLOYMENT_STATUS=$(echo "$RESPONSE" | grep -o '"status":[0-9]*' | grep -o '[0-9]*' || echo "0")
    
    if [ "$DEPLOYMENT_STATUS" = "200" ]; then
        echo "✅ Deployment registered in dashboard!"
        DEPLOYMENT_ID=$(echo "$RESPONSE" | grep -o '"deployment_id":"[^"]*' | cut -d'"' -f4)
        if [ -n "$DEPLOYMENT_ID" ]; then
            echo "📋 Deployment ID: $DEPLOYMENT_ID"
        fi
    else
        echo "⚠️  Warning: Could not register deployment (Status: $DEPLOYMENT_STATUS)"
        echo "Make sure API_URL is set: export API_URL=http://localhost:8000"
        echo "API Response: $RESPONSE"
    fi
    
    echo ""
    echo "═════════════════════════════════════════"
    if [ "$IS_MONOREPO" = true ]; then
        echo "🚀 Monorepo deployment complete!"
        echo "📦 Services deployed: ${#SERVICE_NAMES[@]}"
    else
        echo "🚀 Deployment complete!"
    fi
    echo "═════════════════════════════════════════"
    
fi
'''
    
    script_path = output_dir / "deploy.sh"
    script_path.write_text(script)
    script_path.chmod(0o755)  # Make executable
    print(f"✅ Generated build-and-push.sh")


async def _generate_monorepo_deployment(app_name: str, analysis: Dict, output_dir: Path, env_vars: Dict, chat_id: str, job_id: str):
    """Generate deployment for monorepo"""
    services = analysis.get('services', [])
    print(f"📦 Generating monorepo deployment for {len(services)} services")
    
    service_configs = []
    
    placeholder_ecr_uri = {}
    
    for service in services:
        service_name = service.get('name')
        service_path = service.get('path')
        service_type = service.get('type')
        
        print(f"📝 Generating Dockerfile for service: {service_name}")
        
        service_analysis = {
            'tech_stack': service.get('tech_stack', {}),
            'port': service.get('server_config', {}),
            'build_info': service.get('build_system', {}),
            'server_config': service.get('server_config', {}),
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
            
            placeholder_ecr_uri[service_name] = f"{{AWS_ACCOUNT_ID}}.dkr.ecr.{{AWS_REGION}}.amazonaws.com/{app_name} - {service_name}:latest"
            
        except Exception as e:
            print(f"❌ Failed to generate Dockerfile for {service_name}: {e}")
            raise
    
    print("📝 Generating multi-service CDK infrastructure...")
    
    cdk_files = cdk_generator.generate_monorepo_cdk(
        chat_id=chat_id,
        services=service_configs,
        ecr_image_uris=placeholder_ecr_uri,
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
        'server_config': primary.get('server_config', {}),
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
    app_name = primary.get('name', 'app')
    
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
    
    placeholder_ecr_uri = f"{{AWS_ACCOUNT_ID}}.dkr.ecr.{{AWS_REGION}}.amazonaws.com/{app_name}:latest"


    cdk_files = cdk_generator.generate_single_service_cdk(
        chat_id=chat_id,
        service=service_config,
        ecr_image_uri=placeholder_ecr_uri,
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