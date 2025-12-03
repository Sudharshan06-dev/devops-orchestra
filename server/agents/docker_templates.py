from typing import Dict, Optional


class DockerfileTemplates:
    """Production-ready Dockerfile templates"""
    
    @staticmethod
    def react_static(variables: Dict) -> str:
        """React/Vue/Angular static site with nginx server"""
        node_version = variables.get('node_version', '18')
        build_output_dir = variables.get('build_output_dir', 'dist')
        port = variables.get('port', 3000)
        
        return f"""# Stage 1: Build
FROM node:{node_version}-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

RUN npm run build

# Stage 2: Serve with node:serve package
FROM node:{node_version}-alpine

WORKDIR /app

RUN addgroup -g 1001 -S nodejs && \\
    adduser -S nodejs -u 1001

RUN npm install -g serve

COPY --from=builder --chown=nodejs:nodejs /app/{build_output_dir} ./dist

EXPOSE {port}

ENV NODE_ENV=production
ENV PORT={port}

USER nodejs

HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \\
  CMD node -e "require('http').get('http://localhost:{port}/', (r) => {{process.exit(r.statusCode === 200 ? 0 : 1)}})" || exit 1

CMD ["serve", "-s", "dist", "-l", "{port}"]
"""
    
    @staticmethod
    def express_node_api(variables: Dict) -> str:
        """Express.js or generic Node.js API server"""
        node_version = variables.get('node_version', '18')
        port = variables.get('port', 3000)
        start_command = variables.get('start_command', 'npm run start')
        
        return f"""# Stage 1: Dependencies
FROM node:{node_version}-alpine AS deps

WORKDIR /app

COPY package*.json ./
RUN npm ci --production

# Stage 2: Builder
FROM node:{node_version}-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# Stage 3: Runtime
FROM node:{node_version}-alpine

WORKDIR /app

RUN addgroup -g 1001 -S nodejs && \\
    adduser -S nodejs -u 1001

COPY --from=deps --chown=nodejs:nodejs /app/node_modules ./node_modules
COPY --from=builder --chown=nodejs:nodejs /app/package*.json ./
COPY --from=builder --chown=nodejs:nodejs /app . .

EXPOSE {port}

ENV NODE_ENV=production
ENV PORT={port}

USER nodejs

HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \\
  CMD node -e "require('http').get('http://localhost:{port}/health', (r) => {{process.exit(r.statusCode === 200 ? 0 : 1)}})" || exit 1

CMD {_format_command(start_command)}
"""
    
    @staticmethod
    def fastapi_python(variables: Dict) -> str:
        """FastAPI application - Production-ready with Uvicorn"""
        python_version = variables.get('python_version', '3.11')
        port = variables.get('port', 8000)
        entry_point = variables.get('entry_point', 'main')
        
        return f"""FROM python:{python_version}-slim

WORKDIR /app

RUN apt-get update && \\
    apt-get install -y --no-install-recommends \\
        gcc \\
        && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \\
    pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -m -u 1001 appuser && \\
    chown -R appuser:appuser /app

USER appuser

EXPOSE {port}

ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \\
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:{port}/health')" || exit 1

CMD ["uvicorn", "{entry_point}:app", "--host", "0.0.0.0", "--port", "{port}"]
"""
    
    @staticmethod
    def django_python(variables: Dict) -> str:
        """Django application - Production-ready with Gunicorn"""
        python_version = variables.get('python_version', '3.11')
        port = variables.get('port', 8000)
        django_project = variables.get('django_project', 'config')
        
        return f"""FROM python:{python_version}-slim

WORKDIR /app

RUN apt-get update && \\
    apt-get install -y --no-install-recommends \\
        gcc \\
        postgresql-client \\
        && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \\
    pip install --no-cache-dir -r requirements.txt && \\
    pip install --no-cache-dir gunicorn

COPY . .

RUN python manage.py collectstatic --noinput --clear || echo "Static files already collected"

RUN useradd -m -u 1001 appuser && \\
    chown -R appuser:appuser /app

USER appuser

EXPOSE {port}

ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \\
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:{port}/health')" || exit 1

CMD ["gunicorn", "{django_project}.wsgi:application", "--bind", "0.0.0.0:{port}", "--workers", "4"]
"""
    
    @staticmethod
    def flask_python(variables: Dict) -> str:
        """Flask application - Production-ready with Gunicorn"""
        python_version = variables.get('python_version', '3.11')
        port = variables.get('port', 5000)
        entry_point = variables.get('entry_point', 'app')
        
        return f"""FROM python:{python_version}-slim

WORKDIR /app

RUN apt-get update && \\
    apt-get install -y --no-install-recommends \\
        gcc \\
        && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \\
    pip install --no-cache-dir -r requirements.txt && \\
    pip install --no-cache-dir gunicorn

COPY . .

RUN useradd -m -u 1001 appuser && \\
    chown -R appuser:appuser /app

USER appuser

EXPOSE {port}

ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \\
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:{port}/health')" || exit 1

CMD ["gunicorn", "{entry_point}:app", "--bind", "0.0.0.0:{port}", "--workers", "4"]
"""


def _format_command(cmd: str) -> str:
    """Format command for Docker CMD"""
    if isinstance(cmd, str):
        if ' ' in cmd:
            parts = cmd.split()
            return str(parts)
        return f'["{cmd}"]'
    return str(cmd)


class DockerfileGenerator:
    """Select and generate production-ready Dockerfile"""
    
    def __init__(self, repo_analysis: Dict):
        """Initialize with repo analysis data"""
        self.analysis = repo_analysis
        self.templates = DockerfileTemplates()
    
    def generate(self) -> str:
        """
        Main entry point - select template and generate Dockerfile
        """
        template_func = self._select_template()
        variables = self._prepare_variables()
        dockerfile = template_func(variables)
        
        print(f"✅ Generated Dockerfile using: {template_func.__name__}")
        return dockerfile
    
    def _select_template(self):
        """Select appropriate template based on tech stack - FIX FOR MONOREPO"""
        
        service = self.analysis.get('primary_service', {})
        if not service:
            service = self.analysis
        
        tech_stack = service.get('tech_stack', {})
                
        # CRITICAL FIX: Check 'runtime' field first (not 'language')
        language = (tech_stack.get('runtime') or 
                   tech_stack.get('language', 'node')).lower()
        
        frameworks = tech_stack.get('frameworks', [])
        
        print(f"🔍 Detected: {language} | Frameworks: {frameworks}")
        print(f"📦 Service: {service.get('name', 'unknown')}")
        
        # PYTHON stack
        if language == 'python':
            if 'fastapi' in frameworks:
                return self.templates.fastapi_python
            elif 'django' in frameworks:
                return self.templates.django_python
            elif 'flask' in frameworks:
                return self.templates.flask_python
            else:
                return self.templates.fastapi_python
        
        # NODE.js stack
        elif language == 'node' or language == 'javascript':
            if any(fw in frameworks for fw in ['react', 'vue', 'angular', 'nuxt', 'svelte']):
                return self.templates.react_static
            elif 'express' in frameworks:
                return self.templates.express_node_api
            else:
                return self.templates.express_node_api
        
        # Fallback
        print(f"⚠️  Unknown runtime: {language}, defaulting to FastAPI")
        return self.templates.fastapi_python
    
    def _prepare_variables(self) -> Dict:
        """Extract variables from repo analysis"""
        
        service = self.analysis.get('primary_service', {})
        if not service:
            service = self.analysis
        
        tech_stack = service.get('tech_stack', {})
        build_info = service.get('build_system', {})
        server_config = service.get('server_config', {})
        
        port = server_config.get('port', 8000)
        
        node_version = self._detect_version('node', tech_stack)
        python_version = self._detect_version('python', tech_stack)
        
        return {
            'node_version': node_version,
            'python_version': python_version,
            'port': port,
            'build_output_dir': build_info.get('output_dir', 'dist'),
            'start_command': build_info.get('start_command', 'npm run start'),
            'entry_point': service.get('entry_points', ['main'])[0].replace('.py', ''),
        }
    
    def _detect_version(self, runtime: str, tech_stack: Dict) -> str:
        """Detect runtime version from tech_stack"""
        
        version_str = tech_stack.get('version', '')
        
        if runtime == 'node':
            if version_str:
                return version_str.replace('node', '').strip()
            return '18'
        
        elif runtime == 'python':
            if version_str:
                return version_str.replace('python', '').strip()
            return '3.11'
        
        return '18'


def generate_dockerfile_from_analysis(repo_analysis: Dict) -> str:
    """
    Generate production-ready Dockerfile from repo analysis
    
    Args:
        repo_analysis: Output from deterministic_repo_analyzer
    
    Returns:
        Complete Dockerfile content as string
    """
    generator = DockerfileGenerator(repo_analysis)
    return generator.generate()