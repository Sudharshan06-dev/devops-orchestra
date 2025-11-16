from typing import Dict, Optional


class DockerfileTemplates:
    """Production-ready Dockerfile templates"""
    
    @staticmethod
    def react_static(variables: Dict) -> str:
        """
        React/Vue/Angular static site with nginx server
        Multi-stage: build → serve with 'serve' package
        """
        node_version = variables.get('node_version', '18')
        build_output_dir = variables.get('build_output_dir', 'dist')
        port = variables.get('port', 3000)
        
        return f"""# Stage 1: Build
FROM node:{node_version}-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./
RUN npm ci

# Copy source code
COPY . .

# Build application
RUN npm run build

# Stage 2: Serve with node:serve package
FROM node:{node_version}-alpine

WORKDIR /app

# Create nodejs user FIRST (before copying files)
RUN addgroup -g 1001 -S nodejs && \\
    adduser -S nodejs -u 1001

# Install serve globally
RUN npm install -g serve

# Copy built assets from builder with correct ownership
COPY --from=builder --chown=nodejs:nodejs /app/{build_output_dir} ./dist

EXPOSE {port}

# Set environment variables
ENV NODE_ENV=production
ENV PORT={port}

# Switch to non-root user
USER nodejs

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \\
  CMD node -e "require('http').get('http://localhost:{port}/', (r) => {{process.exit(r.statusCode === 200 ? 0 : 1)}})" || exit 1

# Start serve on specified port
CMD ["serve", "-s", "dist", "-l", "{port}"]
"""
    
    @staticmethod
    def nextjs_static(variables: Dict) -> str:
        """
        Next.js static export with serve package
        For statically exported Next.js apps
        """
        node_version = variables.get('node_version', '18')
        port = variables.get('port', 3000)
        
        return f"""# Stage 1: Build
FROM node:{node_version}-alpine AS builder

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm ci

# Copy source
COPY . .

# Build Next.js app (static export)
RUN npm run build

# Stage 2: Serve
FROM node:{node_version}-alpine

WORKDIR /app

# Create nodejs user FIRST
RUN addgroup -g 1001 -S nodejs && \\
    adduser -S nodejs -u 1001

# Install serve globally
RUN npm install -g serve

# Copy build output from builder with correct ownership
COPY --from=builder --chown=nodejs:nodejs /app/out ./out

EXPOSE {port}

ENV NODE_ENV=production
ENV PORT={port}

USER nodejs

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \\
  CMD node -e "require('http').get('http://localhost:{port}/', (r) => {{process.exit(r.statusCode === 200 ? 0 : 1)}})" || exit 1

CMD ["serve", "-s", "out", "-l", "{port}"]
"""
    
    @staticmethod
    def nextjs_ssr(variables: Dict) -> str:
        """
        Next.js with server-side rendering
        Requires server.js or similar entry point
        """
        node_version = variables.get('node_version', '18')
        port = variables.get('port', 3000)
        
        return f"""# Stage 1: Dependencies
FROM node:{node_version}-alpine AS deps

WORKDIR /app

COPY package*.json ./
RUN npm ci --production

# Stage 2: Build
FROM node:{node_version}-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

ENV NODE_ENV production
ENV NEXT_TELEMETRY_DISABLED 1

RUN npm run build

# Stage 3: Runtime
FROM node:{node_version}-alpine

WORKDIR /app

ENV NODE_ENV production
ENV NEXT_TELEMETRY_DISABLED 1
ENV PORT {port}
ENV HOSTNAME "0.0.0.0"

# Create nodejs user FIRST
RUN addgroup -g 1001 -S nodejs && \\
    adduser -S nodejs -u 1001

# Copy dependencies and build output
COPY --from=deps --chown=nodejs:nodejs /app/node_modules ./node_modules
COPY --from=builder --chown=nodejs:nodejs /app/.next ./.next
COPY --from=builder --chown=nodejs:nodejs /app/public ./public
COPY --from=builder --chown=nodejs:nodejs /app/package*.json ./

EXPOSE {port}

USER nodejs

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \\
  CMD node -e "require('http').get('http://localhost:{port}/', (r) => {{process.exit(r.statusCode === 200 ? 0 : 1)}})" || exit 1

CMD ["npm", "run", "start"]
"""
    
    @staticmethod
    def express_node_api(variables: Dict) -> str:
        """
        Express.js or generic Node.js API server
        Multi-stage build with proper user permissions
        """
        node_version = variables.get('node_version', '18')
        port = variables.get('port', 3000)
        start_command = variables.get('start_command', 'npm run start')
        has_typescript = variables.get('has_typescript', False)
        
        build_step = """
# Build TypeScript if present
RUN npm run build
""" if has_typescript else ""
        
        return f"""# Stage 1: Dependencies
FROM node:{node_version}-alpine AS deps

WORKDIR /app

COPY package*.json ./
RUN npm ci --production

# Stage 2: Build (if TypeScript)
FROM node:{node_version}-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
{build_step}

# Stage 3: Runtime
FROM node:{node_version}-alpine

WORKDIR /app

# Create nodejs user FIRST
RUN addgroup -g 1001 -S nodejs && \\
    adduser -S nodejs -u 1001

# Copy dependencies from deps stage
COPY --from=deps --chown=nodejs:nodejs /app/node_modules ./node_modules

# Copy application files
COPY --chown=nodejs:nodejs package*.json ./
COPY --chown=nodejs:nodejs . .

EXPOSE {port}

ENV NODE_ENV=production
ENV PORT={port}

USER nodejs

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \\
  CMD node -e "require('http').get('http://localhost:{port}/health', (r) => {{process.exit(r.statusCode === 200 ? 0 : 1)}})" || exit 1

CMD {_format_command(start_command)}
"""
    
    @staticmethod
    def fastapi_python(variables: Dict) -> str:
        """
        FastAPI application
        Production-ready with Uvicorn
        """
        python_version = variables.get('python_version', '3.11')
        port = variables.get('port', 8000)
        entry_point = variables.get('entry_point', 'main')
        
        return f"""FROM python:{python_version}-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \\
    apt-get install -y --no-install-recommends \\
        gcc \\
        && rm -rf /var/lib/apt/lists/*

# Copy requirements first (better caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \\
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1001 appuser && \\
    chown -R appuser:appuser /app

USER appuser

EXPOSE {port}

ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \\
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:{port}/health')" || exit 1

CMD ["uvicorn", "{entry_point}:app", "--host", "0.0.0.0", "--port", "{port}"]
"""
    
    @staticmethod
    def django_python(variables: Dict) -> str:
        """
        Django application
        Production-ready with Gunicorn
        """
        python_version = variables.get('python_version', '3.11')
        port = variables.get('port', 8000)
        django_project = variables.get('django_project', 'config')
        
        return f"""FROM python:{python_version}-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \\
    apt-get install -y --no-install-recommends \\
        gcc \\
        postgresql-client \\
        && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \\
    pip install --no-cache-dir -r requirements.txt && \\
    pip install --no-cache-dir gunicorn

# Copy application
COPY . .

# Collect static files (if applicable)
RUN python manage.py collectstatic --noinput --clear || echo "Static files already collected or not needed"

# Create non-root user
RUN useradd -m -u 1001 appuser && \\
    chown -R appuser:appuser /app

USER appuser

EXPOSE {port}

ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \\
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:{port}/health')" || exit 1

CMD ["gunicorn", "{django_project}.wsgi:application", "--bind", "0.0.0.0:{port}", "--workers", "4", "--timeout", "60"]
"""
    
    @staticmethod
    def flask_python(variables: Dict) -> str:
        """
        Flask application
        Production-ready with Gunicorn
        """
        python_version = variables.get('python_version', '3.11')
        port = variables.get('port', 5000)
        entry_point = variables.get('entry_point', 'app')
        
        return f"""FROM python:{python_version}-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \\
    apt-get install -y --no-install-recommends \\
        gcc \\
        && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \\
    pip install --no-cache-dir -r requirements.txt && \\
    pip install --no-cache-dir gunicorn

# Copy application
COPY . .

# Create non-root user
RUN useradd -m -u 1001 appuser && \\
    chown -R appuser:appuser /app

USER appuser

EXPOSE {port}

ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \\
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:{port}/health')" || exit 1

CMD ["gunicorn", "{entry_point}:app", "--bind", "0.0.0.0:{port}", "--workers", "4", "--timeout", "60"]
"""
    
    @staticmethod
    def generic_python(variables: Dict) -> str:
        """Generic Python application (fallback)"""
        python_version = variables.get('python_version', '3.11')
        port = variables.get('port', 8000)
        
        return f"""FROM python:{python_version}-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \\
    apt-get install -y --no-install-recommends \\
        gcc \\
        curl \\
        && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip && \\
    pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create non-root user
RUN useradd -m -u 1001 appuser && \\
    chown -R appuser:appuser /app

USER appuser

EXPOSE {port}

ENV PYTHONUNBUFFERED=1

# Health check (generic - may need adjustment)
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \\
  CMD curl -f http://localhost:{port}/ || exit 1

CMD ["python", "main.py"]
"""


def _format_command(cmd: str) -> str:
    """Format command for Docker CMD - handle strings vs arrays"""
    if isinstance(cmd, str):
        # If it's a simple command, format as array
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
        
        Args:
            repo_analysis: From deterministic_repo_analyzer
        
        Returns:
            Complete production-ready Dockerfile as string
        """
        # Step 1: Select template
        template_func = self._select_template()
        
        # Step 2: Prepare variables
        variables = self._prepare_variables()
        
        # Step 3: Generate
        dockerfile = template_func(variables)
        
        print(f"✅ Generated Dockerfile using: {template_func.__name__}")
        return dockerfile
    
    def _select_template(self):
        """Select appropriate template based on tech stack"""
        
        tech_stack = self.analysis.get('tech_stack', {})
        language = tech_stack.get('language', 'node').lower()
        frameworks = tech_stack.get('frameworks', [])
        
        print(f"🔍 Detected: {language} | Frameworks: {frameworks}")
        
        # Node.js stack
        if language == 'node' or language == 'javascript':
            if 'next' in frameworks:
                # Check if it's static export or SSR
                build_info = self.analysis.get('build_info', {})
                build_cmd = build_info.get('build_command', '').lower()
                if 'export' in build_cmd or 'static' in build_cmd:
                    return self.templates.nextjs_static
                return self.templates.nextjs_ssr
            
            elif any(fw in frameworks for fw in ['react', 'vue', 'angular', 'nuxt', 'svelte']):
                return self.templates.react_static
            
            elif 'express' in frameworks:
                return self.templates.express_node_api
            
            else:
                # Default to Express for unknown Node.js apps
                return self.templates.express_node_api
        
        # Python stack
        elif language == 'python':
            if 'fastapi' in frameworks:
                return self.templates.fastapi_python
            elif 'django' in frameworks:
                return self.templates.django_python
            elif 'flask' in frameworks:
                return self.templates.flask_python
            else:
                # Default to FastAPI for Python
                return self.templates.generic_python
        
        # Fallback
        print(f"⚠️  Unknown tech stack: {language}, defaulting to Express")
        return self.templates.express_node_api
    
    def _prepare_variables(self) -> Dict:
        """Extract variables from repo analysis"""
        
        tech_stack = self.analysis.get('tech_stack', {})
        build_info = self.analysis.get('build_info', {})
        language = tech_stack.get('language', 'node').lower()
        
        port = self.analysis.get('port', {}).get('port', 3000)
        
        # Node.js versions
        node_version = self._detect_version('node')
        python_version = self._detect_version('python')
        
        # Build output directory
        build_output_dir = self._detect_build_output_dir()
        
        # Commands
        build_command = build_info.get('build_command', 'npm run build')
        start_command = build_info.get('start_command', 'npm run start')
        
        return {
            'node_version': node_version,
            'python_version': python_version,
            'port': port,
            'build_output_dir': build_output_dir,
            'build_command': build_command,
            'start_command': start_command,
            'has_typescript': tech_stack.get('has_typescript', False),
            'entry_point': self.analysis.get('entry_point', 'main'),
            'django_project': self._detect_django_project(),
        }
    
    def _detect_version(self, runtime: str) -> str:
        """Detect runtime version"""
        
        version = self.analysis.get('tech_stack', {}).get('version', '')
        
        if runtime == 'node':
            if version.startswith('node'):
                return version.replace('node', '')
            return '18'  # Default
        
        elif runtime == 'python':
            if version.startswith('python'):
                return version.replace('python', '')
            return '3.11'  # Default
        
        return '18'
    
    def _detect_build_output_dir(self) -> str:
        """Detect build output directory"""
        
        analysis = self.analysis.get('full_analysis', '').lower()
        
        # Check for specific patterns
        if '.next' in analysis:
            return '.next'
        elif 'build' in analysis:
            return 'build'
        elif 'dist' in analysis:
            return 'dist'
        
        # Default by framework
        frameworks = self.analysis.get('tech_stack', {}).get('frameworks', [])
        if 'react' in frameworks or 'vue' in frameworks:
            return 'build'
        elif 'next' in frameworks:
            return '.next'
        
        return 'dist'
    
    def _detect_django_project(self) -> Optional[str]:
        """Detect Django project name"""
        
        analysis = self.analysis.get('full_analysis', '')
        
        if 'manage.py' in analysis:
            # Try to find wsgi.py references
            import re
            match = re.search(r'(\w+)\.wsgi', analysis)
            if match:
                return match.group(1)
        
        return 'config'


def generate_dockerfile_from_analysis(repo_analysis: Dict) -> str:
    """
    Generate production-ready Dockerfile from repo analysis
    
    Main entry point for integration with deployment_generator
    
    Args:
        repo_analysis: Output from deterministic_repo_analyzer
    
    Returns:
        Complete Dockerfile content as string
    
    Example:
        dockerfile_content = generate_dockerfile_from_analysis(analysis)
        with open('Dockerfile', 'w') as f:
            f.write(dockerfile_content)
    """
    generator = DockerfileGenerator(repo_analysis)
    return generator.generate()