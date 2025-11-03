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
from typing import Optional, Dict, List, Tuple
import re

OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL')
OLLAMA_CHAT_MODEL = os.getenv('OLLAMA_CHAT_MODEL')
DEPLOYMENT_OUTPUT_DIR = os.getenv("DEPLOYMENT_OUTPUT_DIR", "./generated_deployments")

ollama_client = AsyncClient(host=OLLAMA_BASE_URL)
user_chat_model = DynamoDBConnection.get_instance().get_table()


# --------------------------- STRUCTURED REPO ANALYSIS --------------------------- #
class RepoAnalyzer:
    """Structured analysis of repository to prevent hallucinations"""
    
    def __init__(self, repo_context: dict):
        self.repo_url = repo_context.get('repo_url', '')
        self.files = repo_context.get('files', [])
        self.full_analysis = repo_context.get('full_analysis', '')
        self.dependencies = repo_context.get('dependencies', {})
        
    def analyze(self) -> Dict:
        """Perform deterministic analysis of the repository"""
        return {
            'tech_stack': self._detect_tech_stack(),
            'port': self._detect_port(),
            'database': self._detect_database(),
            'package_manager': self._detect_package_manager(),
            'build_info': self._extract_build_info(),
            'entry_point': self._detect_entry_point(),
            'static_files': self._detect_static_files()
        }
    
    def _detect_tech_stack(self) -> Dict:
        """Detect technology stack with confidence levels"""
        analysis_lower = self.full_analysis.lower()
        
        # Node.js detection
        has_package_json = 'package.json' in analysis_lower
        has_node_modules = 'node_modules' in analysis_lower
        has_npm_lock = 'package-lock.json' in analysis_lower
        has_yarn_lock = 'yarn.lock' in analysis_lower
        
        # Python detection
        has_requirements = 'requirements.txt' in analysis_lower
        has_pipfile = 'pipfile' in analysis_lower
        has_setup_py = 'setup.py' in analysis_lower
        
        # Java detection
        has_pom = 'pom.xml' in analysis_lower
        has_gradle = 'build.gradle' in analysis_lower
        
        # Framework detection
        frameworks = {
            'react': 'react' in analysis_lower,
            'vue': 'vue' in analysis_lower,
            'angular': 'angular' in analysis_lower,
            'next': 'next' in analysis_lower or 'nextjs' in analysis_lower,
            'express': 'express' in analysis_lower,
            'fastapi': 'fastapi' in analysis_lower,
            'django': 'django' in analysis_lower,
            'flask': 'flask' in analysis_lower,
            'spring': 'spring' in analysis_lower
        }
        
        detected_frameworks = [k for k, v in frameworks.items() if v]
        
        # Determine primary tech stack
        if has_package_json:
            primary = 'node'
            confidence = 'high' if has_npm_lock or has_yarn_lock else 'medium'
        elif has_requirements or has_pipfile:
            primary = 'python'
            confidence = 'high' if has_requirements else 'medium'
        elif has_pom or has_gradle:
            primary = 'java'
            confidence = 'high'
        else:
            primary = 'unknown'
            confidence = 'low'
        
        return {
            'primary': primary,
            'confidence': confidence,
            'frameworks': detected_frameworks,
            'has_typescript': 'tsconfig.json' in analysis_lower
        }
    
    def _detect_port(self) -> Dict:
        """Detect port with multiple strategies"""
        ports = []
        analysis = self.full_analysis
        
        # Strategy 1: Look for explicit PORT environment variable mentions
        port_patterns = [
            r'PORT[:\s=]+(\d{4,5})',
            r'port[:\s=]+(\d{4,5})',
            r'listen\((\d{4,5})\)',
            r'\.listen\([\'\"]?(\d{4,5})[\'\"]?\)',
        ]
        
        for pattern in port_patterns:
            matches = re.findall(pattern, analysis, re.IGNORECASE)
            ports.extend([int(m) for m in matches if 1000 <= int(m) <= 65535])
        
        # Strategy 2: Framework defaults
        tech = self._detect_tech_stack()
        framework_defaults = {
            'react': 3000,
            'next': 3000,
            'vue': 8080,
            'angular': 4200,
            'express': 3000,
            'fastapi': 8000,
            'django': 8000,
            'flask': 5000,
            'spring': 8080
        }
        
        for framework in tech['frameworks']:
            if framework in framework_defaults:
                ports.append(framework_defaults[framework])
        
        # Strategy 3: Tech stack defaults
        if tech['primary'] == 'node':
            ports.append(3000)
        elif tech['primary'] == 'python':
            ports.append(8000)
        elif tech['primary'] == 'java':
            ports.append(8080)
        
        # Return most common port or first detected
        if ports:
            from collections import Counter
            most_common = Counter(ports).most_common(1)[0][0]
            return {
                'port': most_common,
                'confidence': 'high' if len(set(ports)) == 1 else 'medium',
                'all_detected': list(set(ports))
            }
        
        return {'port': 8000, 'confidence': 'low', 'all_detected': []}
    
    def _detect_database(self) -> Dict:
        """Detect database requirements"""
        analysis_lower = self.full_analysis.lower()
        
        databases = {
            'postgres': any(term in analysis_lower for term in ['postgres', 'postgresql', 'pg']),
            'mysql': 'mysql' in analysis_lower,
            'mongodb': any(term in analysis_lower for term in ['mongo', 'mongoose']),
            'redis': 'redis' in analysis_lower,
            'dynamodb': 'dynamodb' in analysis_lower
        }
        
        # ORM detection
        orms = {
            'sequelize': 'sequelize' in analysis_lower,
            'typeorm': 'typeorm' in analysis_lower,
            'prisma': 'prisma' in analysis_lower,
            'sqlalchemy': 'sqlalchemy' in analysis_lower,
            'mongoose': 'mongoose' in analysis_lower
        }
        
        detected_dbs = [k for k, v in databases.items() if v]
        detected_orms = [k for k, v in orms.items() if v]
        
        needs_db = len(detected_dbs) > 0 or len(detected_orms) > 0
        
        # Determine primary database
        db_priority = ['postgres', 'mysql', 'mongodb', 'redis', 'dynamodb']
        primary_db = next((db for db in db_priority if db in detected_dbs), None)
        
        return {
            'needs_database': needs_db,
            'databases': detected_dbs,
            'orms': detected_orms,
            'primary': primary_db,
            'confidence': 'high' if detected_dbs else ('medium' if detected_orms else 'none')
        }
    
    def _detect_package_manager(self) -> str:
        """Detect package manager"""
        analysis_lower = self.full_analysis.lower()
        
        if 'yarn.lock' in analysis_lower:
            return 'yarn'
        elif 'pnpm-lock.yaml' in analysis_lower:
            return 'pnpm'
        elif 'package-lock.json' in analysis_lower:
            return 'npm'
        elif 'pipfile.lock' in analysis_lower:
            return 'pipenv'
        elif 'poetry.lock' in analysis_lower:
            return 'poetry'
        elif 'requirements.txt' in analysis_lower:
            return 'pip'
        elif 'pom.xml' in analysis_lower:
            return 'maven'
        elif 'build.gradle' in analysis_lower:
            return 'gradle'
        
        return 'npm'  # Default
    
    def _extract_build_info(self) -> Dict:
        """Extract build commands and scripts"""
        # This would ideally parse package.json scripts
        # For now, return sensible defaults based on tech stack
        tech = self._detect_tech_stack()
        
        if tech['primary'] == 'node':
            if 'next' in tech['frameworks']:
                return {
                    'build_command': 'npm run build',
                    'start_command': 'npm start',
                    'install_command': 'npm ci --production'
                }
            elif 'react' in tech['frameworks'] or 'vue' in tech['frameworks']:
                return {
                    'build_command': 'npm run build',
                    'start_command': 'npx serve -s build',
                    'install_command': 'npm ci --production',
                    'needs_serve': True
                }
            else:
                return {
                    'build_command': 'npm run build',
                    'start_command': 'node server.js',
                    'install_command': 'npm ci --production'
                }
        elif tech['primary'] == 'python':
            return {
                'build_command': None,
                'start_command': self._detect_python_start_command(tech),
                'install_command': 'pip install -r requirements.txt'
            }
        
        return {}
    
    def _detect_python_start_command(self, tech: Dict) -> str:
        """Detect Python application start command"""
        if 'fastapi' in tech['frameworks']:
            return 'uvicorn main:app --host 0.0.0.0 --port 8000'
        elif 'django' in tech['frameworks']:
            return 'gunicorn myproject.wsgi:application --bind 0.0.0.0:8000'
        elif 'flask' in tech['frameworks']:
            return 'gunicorn app:app --bind 0.0.0.0:5000'
        return 'python main.py'
    
    def _detect_entry_point(self) -> str:
        """Detect application entry point"""
        analysis = self.full_analysis.lower()
        
        # Common entry points
        entry_points = [
            'server.js', 'index.js', 'app.js', 'main.js',
            'src/server.js', 'src/index.js', 'src/app.js',
            'main.py', 'app.py', 'server.py', 'wsgi.py',
            'manage.py'
        ]
        
        for entry in entry_points:
            if entry in analysis:
                return entry
        
        return 'index.js'  # Default
    
    def _detect_static_files(self) -> Optional[str]:
        """Detect if there's a static files directory"""
        analysis = self.full_analysis.lower()
        
        static_dirs = ['public', 'static', 'dist', 'build', 'assets']
        for dir_name in static_dirs:
            if f'/{dir_name}/' in analysis or f'{dir_name}/' in analysis:
                return dir_name
        
        return None


# --------------------------- ENTRY POINT --------------------------- #
async def deployment_generator(repo_context: dict = None, chat_id: str = "default", user_id: int = None):
    job_id = str(uuid.uuid4())
    update_session_field(chat_id, 'data.deployment_config.job_id', job_id)
    update_session_field(chat_id, 'data.deployment_config.status', 'generating')

    asyncio.create_task(
        _generate_deployment_in_background(job_id, repo_context, chat_id, user_id)
    )

    yield f"🚀 **Generating Deployment Configuration...**\n\n"
    yield f"📋 Job ID: `{job_id}`\n\n"
    
    # Analyze repo first
    analyzer = RepoAnalyzer(repo_context)
    analysis = analyzer.analyze()
    
    yield f"📦 Detected: **{analysis['tech_stack']['primary'].upper()}** application"
    if analysis['tech_stack']['frameworks']:
        yield f" with {', '.join(analysis['tech_stack']['frameworks'])}"
    yield f"\n🔌 Port: **{analysis['port']['port']}**\n"
    
    yield f"\n📝 Creating:\n- Dockerfile (optimized for {analysis['tech_stack']['primary']})\n"
    yield f"- AWS CDK (Python) with ECS Fargate\n- Application Load Balancer"
    
    if analysis['database']['needs_database']:
        yield f"\n- RDS Database ({analysis['database']['primary'] or 'auto-detected'})"
    
    yield f"\n\n⏱️ Estimated time: 3-5 minutes...\n"


# --------------------------- MAIN LOGIC --------------------------- #
async def _generate_deployment_in_background(job_id: str, repo_context: dict, chat_id: str, user_id: int):
    print(f'🔨 Starting deployment generation: {job_id}, {chat_id}, {user_id}')

    # Analyze repository structure
    analyzer = RepoAnalyzer(repo_context)
    repo_analysis = analyzer.analyze()
    print(f"📊 Repo Analysis: {json.dumps(repo_analysis, indent=2)}")

    # Load .env
    env_file_path = Path(f"./user_uploads/{user_id}/{chat_id}/.env")
    env_vars_dict = {}
    if env_file_path.exists():
        for line in env_file_path.read_text().splitlines():
            if line and '=' in line and not line.strip().startswith('#'):
                k, v = line.split('=', 1)
                env_vars_dict[k.strip()] = v.strip()
    print(f"✅ Loaded {len(env_vars_dict)} environment variables")

    output_dir = Path(DEPLOYMENT_OUTPUT_DIR) / job_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # === STEP 1: Dockerfile ===
    dockerfile_content = await _generate_dockerfile_with_llm(repo_context, env_vars_dict, repo_analysis)
    _validate_dockerfile(dockerfile_content, repo_analysis)
    dockerfile_path = output_dir / "Dockerfile"
    dockerfile_path.write_text(dockerfile_content)
    print(f"✅ Dockerfile saved at {dockerfile_path}")

    # === STEP 2: CDK ===
    cdk_result = await _generate_cdk_with_llm(repo_context, env_vars_dict, chat_id, job_id, repo_analysis)
    cdk_files = cdk_result.get('files', {})
    detected_port = cdk_result.get('port', repo_analysis['port']['port'])
    needs_db = cdk_result.get('needs_database', repo_analysis['database']['needs_database'])
    db_type = cdk_result.get('db_type', None)
    method = cdk_result.get('method', 'unknown')

    cdk_dir = output_dir / "cdk"
    cdk_dir.mkdir(exist_ok=True)
    for filename, content in cdk_files.items():
        (cdk_dir / filename).write_text(content)

    update_session_field(chat_id, 'data.deployment_config', {
        'status': 'completed',
        'job_id': job_id,
        'dockerfile_path': str(dockerfile_path),
        'cdk_path': str(cdk_dir),
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'port': detected_port,
        'needs_database': needs_db,
        'db_type': db_type,
        'generation_method': method,
        'env_vars_count': len(env_vars_dict),
        'repo_analysis': repo_analysis
    })

    completion_msg = _build_completion_message(chat_id, user_id, job_id, output_dir, cdk_files,
                                               repo_context, detected_port, needs_db, method)
    user_chat_model.put_item(Item=completion_msg)
    print("✅ Deployment generation complete")


# TODO ERROR HERE PLEASE CHECK HERE CORRECTLY
async def _generate_dockerfile_with_llm(repo_context: dict, env_vars: dict, repo_analysis: Dict) -> str:
    """Generate Dockerfile with structured analysis and fallback handling."""

    # Extract structured context
    tech = repo_analysis['tech_stack']['primary']
    frameworks = repo_analysis['tech_stack']['frameworks']
    port = repo_analysis['port']['port']
    build_info = repo_analysis['build_info']
    package_manager = repo_analysis['package_manager']
    has_typescript = repo_analysis['tech_stack']['has_typescript']

    # Commands
    install_cmd = build_info.get('install_command', 'npm ci --production')
    build_cmd = build_info.get('build_command', 'npm run build')
    start_cmd = build_info.get('start_command', 'node index.js')

    # Prompt
    prompt = f"""You are a DevOps engineer creating a production-ready Dockerfile.

STRICT REQUIREMENTS - DO NOT DEVIATE:

Technology Stack:
- Primary: {tech.upper()}
- Frameworks: {', '.join(frameworks) if frameworks else 'None detected'}
- Package Manager: {package_manager}
- Port: {port}
- TypeScript: {has_typescript}

Commands to use:
- Install: {install_cmd}
- Build: {build_cmd}
- Start: {start_cmd}

Base Image:
- Node.js → node:18-alpine
- Python → python:3.11-slim
- Java → eclipse-temurin:17-jdk-alpine (builder), eclipse-temurin:17-jre-alpine (runtime)

Required Dockerfile structure:
1. Use multi-stage build if build step exists
2. Install dependencies first
3. Copy only required code
4. EXPOSE {port}
5. Add HEALTHCHECK
6. Run as non-root user
7. Exclude node_modules, .git, .env, *.md

DO NOT:
- Mix tech stacks
- Hallucinate frameworks
- Use deprecated base images
- Copy unnecessary files
- Run as root user

Output must start with FROM. No markdown, no explanations.
"""

    try:
        response = await ollama_client.chat(
            model=OLLAMA_CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            stream=False,
            options={"temperature": 0.05, "num_predict": 3000}
        )

        raw_content = response["message"]["content"]
        print('\n🔍 Raw LLM Output:\n', raw_content)

        # Step 1: Remove markdown fencing
        if "```dockerfile" in raw_content.lower():
            raw_content = raw_content.split("```dockerfile", 1)[-1]
        elif "```" in raw_content:
            raw_content = raw_content.split("```", 1)[-1]
        
        content = raw_content.strip()

        # Step 2: Remove hallucinated content after `EXPOSE`
        cleaned_lines = []
        for line in content.splitlines():
            if any(term in line.lower() for term in ["endpoints:", "example.com", "http", "https", "GET", "POST", "action", "=>"]):
                break
            cleaned_lines.append(line)
        content = "\n".join(cleaned_lines).strip()

        # Step 3: Remove leading blank lines
        while content.startswith('\n') or content.startswith('\r') or content.startswith(" "):
            content = content.lstrip('\n\r ')

        # Step 4: Check Dockerfile starts correctly
        if not content.startswith("FROM"):
            raise ValueError("🚨 Invalid LLM response — Dockerfile must start with FROM")

        print('\n✅ Cleaned Dockerfile Content:\n', content)
        return content

    except Exception as e:
        print(f"❌ LLM Dockerfile generation failed: {e}")
        return _generate_dockerfile_template(tech, port, build_info, package_manager)


def _generate_dockerfile_template(tech: str, port: int, build_info: Dict, package_manager: str) -> str:
    """Fallback template-based Dockerfile generation"""
    
    if tech == 'node':
        if build_info.get('needs_serve'):
            # Static site (React, Vue)
            return f"""# Build stage
FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Production stage
FROM node:18-alpine
WORKDIR /app
RUN npm install -g serve
COPY --from=builder /app/build ./build
EXPOSE {port}
USER node
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s \\
  CMD node -e "require('http').get('http://localhost:{port}', (r) => {{process.exit(r.statusCode === 200 ? 0 : 1)}})"
CMD ["serve", "-s", "build", "-l", "{port}"]
"""
        else:
            # Node.js server
            return f"""FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --production
COPY . .
EXPOSE {port}
USER node
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s \\
  CMD node -e "require('http').get('http://localhost:{port}', (r) => {{process.exit(r.statusCode === 200 ? 0 : 1)}})"
CMD ["node", "server.js"]
"""
    
    elif tech == 'python':
        return f"""FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE {port}
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s \\
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:{port}')"
CMD {build_info.get('start_command', 'python main.py').split()}
"""
    
    return f"""FROM alpine:latest
WORKDIR /app
COPY . .
EXPOSE {port}
CMD ["echo", "Unsupported tech stack"]
"""


def _validate_dockerfile(dockerfile: str, repo_analysis: Dict):
    """Validate generated Dockerfile against repo analysis"""
    tech = repo_analysis['tech_stack']['primary']
    frameworks = repo_analysis['tech_stack']['frameworks']
    
    dockerfile_lower = dockerfile.lower()
    
    print('dockerfile_lower', dockerfile_lower)
    
    # Check 1: Correct base image for tech stack
    if tech == 'node':
        if 'python' in dockerfile_lower and 'node' not in dockerfile_lower:
            raise ValueError(f"❌ Invalid Dockerfile: Uses Python base for Node.js project")
        if not any(img in dockerfile_lower for img in ['node:', 'alpine']):
            raise ValueError(f"❌ Invalid Dockerfile: Missing Node.js base image")
    
    elif tech == 'python':
        if 'node' in dockerfile_lower and 'python' not in dockerfile_lower:
            raise ValueError(f"❌ Invalid Dockerfile: Uses Node.js base for Python project")
        if 'python:' not in dockerfile_lower:
            raise ValueError(f"❌ Invalid Dockerfile: Missing Python base image")
    
    # Check 2: No framework hallucinations
    hallucinated_frameworks = ['django', 'flask', 'fastapi', 'express', 'nest', 'spring']
    for fw in hallucinated_frameworks:
        if fw in dockerfile_lower and fw not in frameworks and fw not in repo_analysis['full_analysis'].lower():
            print(f"⚠️  Warning: Dockerfile mentions '{fw}' but it wasn't detected in repo")
    
    # Check 3: Port is exposed
    port = repo_analysis['port']['port']
    if f'expose {port}' not in dockerfile_lower and f'expose\n{port}' not in dockerfile_lower:
        print(f"⚠️  Warning: Dockerfile doesn't expose port {port}")
    
    # Check 4: Has FROM statement
    if not dockerfile.strip().startswith('FROM') and 'from ' not in dockerfile_lower[:50]:
        raise ValueError("❌ Invalid Dockerfile: Must start with FROM")
    
    print("✅ Dockerfile validation passed")


# --------------------------- CDK --------------------------- #
async def _generate_cdk_with_llm(repo_context: dict, env_vars: dict, chat_id: str, 
                                 job_id: str, repo_analysis: Dict):
    """Generate CDK with structured analysis"""
    
    port = repo_analysis['port']['port']
    needs_db = repo_analysis['database']['needs_database']
    db_type = repo_analysis['database']['primary']
    
    if db_type == 'postgres':
        db_type = 'POSTGRES'
    elif db_type == 'mysql':
        db_type = 'MYSQL'
    else:
        db_type = 'POSTGRES'  # Default

    prompt = f"""Generate AWS CDK Python code for ECS Fargate deployment.

**VERIFIED PROJECT INFO:**
- Tech Stack: {repo_analysis['tech_stack']['primary'].upper()}
- Frameworks: {', '.join(repo_analysis['tech_stack']['frameworks'])}
- Port: {port}
- Database: {needs_db} ({db_type if needs_db else 'None'})
- Environment Variables: {len(env_vars)} vars

**REQUIRED OUTPUT - 4 FILES EXACTLY:**

=== BEGIN FILE: app.py ===
#!/usr/bin/env python3
import os
import aws_cdk as cdk
from infrastructure_stack import InfrastructureStack

app = cdk.App()
InfrastructureStack(app, "Stack", stack_name="app-{chat_id}-stack",
    env=cdk.Environment(
        account=os.getenv('CDK_DEFAULT_ACCOUNT'),
        region=os.getenv('CDK_DEFAULT_REGION', 'us-east-1')
    )
)
app.synth()
=== END FILE: app.py ===

=== BEGIN FILE: infrastructure_stack.py ===
[Generate complete ECS Fargate stack with:
- VPC with public/private subnets
- ECS Cluster
- Fargate Service with ALB
- Task Definition (container port {port})
- Security Groups
- {f"RDS {db_type} database with security group" if needs_db else "No database"}
- CloudWatch Logs
- Environment variables from task definition
]
=== END FILE: infrastructure_stack.py ===

=== BEGIN FILE: requirements.txt ===
aws-cdk-lib==2.100.0
constructs>=10.0.0,<11.0.0
=== END FILE: requirements.txt ===

=== BEGIN FILE: cdk.json ===
{{"app": "python3 app.py", "context": {{}}}}
=== END FILE: cdk.json ===

OUTPUT: Only the 4 files with exact markers. No extra text.
"""

    try:
        response = await ollama_client.chat(
            model=OLLAMA_CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            stream=False,
            options={"temperature": 0.05, "num_predict": 8000}
        )

        content = response["message"]["content"]
        files = _parse_cdk_files(content)
        
        if not files or len(files) < 4:
            print("⚠️  LLM CDK generation incomplete, using fallback")
            files = _get_complete_default_stack(chat_id, port, env_vars, needs_db, db_type)
            method = "fallback"
        else:
            method = "llm"
            print(f"✅ LLM generated {len(files)} CDK files")

    except Exception as e:
        print(f"❌ LLM CDK generation failed: {e}")
        files = _get_complete_default_stack(chat_id, port, env_vars, needs_db, db_type)
        method = "fallback"

    return {
        "files": files,
        "port": port,
        "needs_database": needs_db,
        "db_type": db_type,
        "method": method
    }


# --------------------------- PARSING --------------------------- #
def _parse_cdk_files(output: str) -> dict:
    """Parse files from LLM output"""
    pattern = r'=== BEGIN FILE:\s*(.*?)\s*===\n(.*?)\n=== END FILE:.*?==='
    matches = re.findall(pattern, output, re.DOTALL)
    files = {}
    for name, content in matches:
        filename = name.strip()
        files[filename] = content.strip()
    return files


# --------------------------- FALLBACK CDK TEMPLATES --------------------------- #
def _get_complete_default_stack(chat_id, port, env_vars, needs_db, db_type):
    """Template-based CDK generation as fallback"""
    return {
        'app.py': _generate_app_py(chat_id),
        'infrastructure_stack.py': _generate_infrastructure_stack(chat_id, port, env_vars, needs_db, db_type),
        'requirements.txt': _generate_requirements(),
        'cdk.json': _generate_cdk_json()
    }


def _generate_app_py(chat_id):
    return f"""#!/usr/bin/env python3
import os
import aws_cdk as cdk
from infrastructure_stack import InfrastructureStack

app = cdk.App()
InfrastructureStack(
    app,
    "InfrastructureStack",
    stack_name="app-{chat_id}-stack",
    env=cdk.Environment(
        account=os.getenv('CDK_DEFAULT_ACCOUNT'),
        region=os.getenv('CDK_DEFAULT_REGION', 'us-east-1')
    )
)
app.synth()
"""


def _generate_infrastructure_stack(chat_id, port, env_vars, needs_db, db_type):
    db_config = ""
    db_env_vars = ""
    
    if needs_db:
        db_config = f"""
        # RDS Database
        db_security_group = ec2.SecurityGroup(
            self, "DBSecurityGroup",
            vpc=vpc,
            description="Security group for RDS database",
            allow_all_outbound=True
        )
        
        db_instance = rds.DatabaseInstance(
            self, "Database",
            engine=rds.DatabaseInstanceEngine.{db_type.lower()}(
                version=rds.{'PostgresEngineVersion.VER_15' if db_type == 'POSTGRES' else 'MysqlEngineVersion.VER_8_0_35'}
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.BURSTABLE3,
                ec2.InstanceSize.SMALL
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[db_security_group],
            multi_az=False,
            allocated_storage=20,
            max_allocated_storage=100,
            database_name="appdb",
            deletion_protection=False,
            removal_policy=RemovalPolicy.DESTROY
        )
        
        # Allow ECS tasks to connect to database
        db_security_group.add_ingress_rule(
            peer=service_security_group,
            connection=ec2.Port.tcp(3306 if '{db_type}' == 'MYSQL' else 5432),
            description="Allow ECS tasks to connect to database"
        )
"""
        
        db_env_vars = f"""
                "DB_HOST": ecs.Secret.from_secrets_manager(db_instance.secret, field="host"),
                "DB_PORT": ecs.Secret.from_secrets_manager(db_instance.secret, field="port"),
                "DB_NAME": ecs.Secret.from_secrets_manager(db_instance.secret, field="dbname"),
                "DB_USER": ecs.Secret.from_secrets_manager(db_instance.secret, field="username"),
                "DB_PASSWORD": ecs.Secret.from_secrets_manager(db_instance.secret, field="password"),
"""

    env_vars_config = "\n                ".join([f'"{k}": "{v}",' for k, v in env_vars.items()])

    return f"""from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_elasticloadbalancingv2 as elbv2,
    aws_logs as logs,
    RemovalPolicy,
    Duration
)
{"from aws_cdk import aws_rds as rds" if needs_db else ""}
from constructs import Construct

class InfrastructureStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # VPC with public and private subnets
        vpc = ec2.Vpc(
            self, "AppVpc",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24
                )
            ]
        )

        # ECS Cluster
        cluster = ecs.Cluster(
            self, "AppCluster",
            vpc=vpc,
            container_insights=True
        )

        # Security Group for ECS Service
        service_security_group = ec2.SecurityGroup(
            self, "ServiceSecurityGroup",
            vpc=vpc,
            description="Security group for ECS service",
            allow_all_outbound=True
        )
        {db_config}
        # CloudWatch Logs
        log_group = logs.LogGroup(
            self, "AppLogGroup",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY
        )

        # Fargate Service with ALB
        fargate_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "FargateService",
            cluster=cluster,
            cpu=512,
            memory_limit_mib=1024,
            desired_count=2,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset("."),
                container_port={port},
                environment={{
                    {env_vars_config}
                }},
                secrets={{{db_env_vars}
                }},
                log_driver=ecs.LogDrivers.aws_logs(
                    stream_prefix="app",
                    log_group=log_group
                )
            ),
            public_load_balancer=True,
            security_groups=[service_security_group],
            assign_public_ip=False
        )

        # Health check configuration
        fargate_service.target_group.configure_health_check(
            path="/",
            healthy_http_codes="200-399",
            interval=Duration.seconds(30),
            timeout=Duration.seconds(5),
            healthy_threshold_count=2,
            unhealthy_threshold_count=3
        )

        # Auto Scaling
        scaling = fargate_service.service.auto_scale_task_count(
            min_capacity=1,
            max_capacity=10
        )
        
        scaling.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=70,
            scale_in_cooldown=Duration.seconds(60),
            scale_out_cooldown=Duration.seconds(60)
        )
"""


def _generate_requirements():
    return """aws-cdk-lib==2.100.0
constructs>=10.0.0,<11.0.0"""


def _generate_cdk_json():
    return """{
  "app": "python3 app.py",
  "watch": {
    "include": ["**"],
    "exclude": [
      "README.md",
      "cdk*.json",
      "**/__pycache__",
      "**/*.egg-info"
    ]
  },
  "context": {
    "@aws-cdk/core:checkSecretUsage": true,
    "@aws-cdk/aws-lambda:recognizeLayerVersion": true,
    "@aws-cdk/core:stackRelativeExports": true
  }
}"""


# --------------------------- COMPLETION MESSAGE --------------------------- #
def _build_completion_message(chat_id, user_id, job_id, output_dir, cdk_files,
                              repo_context, detected_port, needs_db, method):
    """Build completion message for database"""
    return {
        'chat_id': chat_id,
        'message_id': str(uuid4()),
        'type': 'assistant',
        'content': f"""✅ **Deployment Configuration Generated Successfully!**

📁 **Output Directory:** `{output_dir}`

**Generated Files:**
- ✅ Dockerfile (production-ready)
- ✅ AWS CDK Infrastructure ({len(cdk_files)} files)

**Configuration Details:**
- 🔌 Port: `{detected_port}`
- 🗄️ Database: `{'Yes (' + ('RDS ' if needs_db else '') + ')' if needs_db else 'No'}`
- 🎯 Generation Method: `{method}`

**Next Steps:**
1. Review the generated Dockerfile
2. Configure AWS credentials (`aws configure`)
3. Deploy: `cd {output_dir}/cdk && cdk deploy`

**CDK Commands:**
```bash
cd {output_dir}/cdk
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cdk bootstrap  # First time only
cdk deploy
```

Need help? Check the deployment guide or ask me! 🚀
""",
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'metadata': {
            'job_id': job_id,
            'generation_method': method
        }
    }