import json
import re
from typing import Dict, List, Optional


class DeterministicRepoAnalyzer:
    """Extract facts without LLM - pure logic-based analysis"""
    
    def __init__(self, tree: list, files_content: dict):
        self.tree = tree
        self.files = files_content
        self.file_paths = [item['path'] for item in tree if item['type'] == 'blob']
        self.project_root = ''
    
    def analyze(self) -> Dict:
        """Main analysis orchestrator - supports monorepo and single service"""
        
        # Detect if this is a monorepo
        services = self._detect_services()
        
        if len(services) > 1:
            # Monorepo - return all services
            return {
                'repo_type': 'monorepo',
                'services': services,
                'primary_service': services[0],  # First one as primary
            }
        elif len(services) == 1:
            # Single service - flatten structure
            service = services[0]
            return {
                'repo_type': 'single',
                'tech_stack': service['tech_stack'],
                'build_system': service['build_system'],
                'server_config': service['server_config'],
                'database': service['database'],
                'environment': service['environment'],
                'entry_points': service['entry_points'],
            }
        else:
            # No services found - unknown
            return {
                'repo_type': 'unknown',
                'tech_stack': {'runtime': 'unknown', 'frameworks': []},
            }
        
    def _detect_services(self) -> List[Dict]:
        """
        Detect all services in the repo (supports monorepo).
        Returns a list of service configurations.
        """
        services = []
        
        # Find all package.json files
        pkg_files = self._find_all_package_json()
        
        # Find all requirements.txt files
        req_files = self._find_all_requirements_txt()
        
        # Find standalone Python files
        py_files = self._find_all_python_files()
        
        # Process Node.js services
        for pkg, path in pkg_files:
            service = self._analyze_node_service(pkg, path)
            if service:
                services.append(service)
        
        # Process Python services with requirements.txt
        for req_content, path in req_files:
            service = self._analyze_python_service(req_content, path)
            if service:
                services.append(service)
        
        # Process standalone Python files (no requirements.txt)
        if not req_files and py_files:
            for py_content, path in py_files:
                service = self._analyze_python_file(py_content, path)
                if service:
                    services.append(service)
                    break  # Only take first main Python file
        
        # Sort services: backend first, then frontend
        services.sort(key=lambda s: (
            0 if s['type'] == 'backend' else 1,
            s['path'].count('/')  # Prefer shallower paths
        ))
        
        return services
    
    def _find_all_package_json(self) -> List[tuple]:
        """Find all package.json files (excluding node_modules)"""
        results = []
        
        for path in self.files.keys():
            if path.endswith('package.json') and 'node_modules' not in path:
                try:
                    pkg = json.loads(self.files[path])
                    results.append((pkg, path))
                except json.JSONDecodeError:
                    continue
        
        return results
    
    def _find_all_requirements_txt(self) -> List[tuple]:
        """Find all requirements.txt files"""
        results = []
        
        for path in self.files.keys():
            if path.endswith('requirements.txt'):
                results.append((self.files[path], path))
        
        return results
    
    def _find_all_python_files(self) -> List[tuple]:
        """Find main Python files that might indicate a Python project"""
        results = []
        
        # Main Python entry points
        python_entry_files = ['main.py', 'app.py', 'server.py', 'api.py', 'run.py']
        
        for path in self.files.keys():
            filename = path.split('/')[-1]
            if filename in python_entry_files:
                results.append((self.files[path], path))
        
        return results
        
    def _analyze_node_service(self, pkg: Dict, path: str) -> Optional[Dict]:
        """Analyze a Node.js service from package.json"""
        
        deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}
        scripts = pkg.get('scripts', {})
        
        # Skip if no real dependencies (likely a placeholder)
        if len(deps) < 2:
            return None
        
        # Detect type and frameworks
        frameworks = []
        service_type = 'unknown'
        
        # Frontend frameworks
        if 'react' in deps or 'react-dom' in deps:
            frameworks.append('react')
            service_type = 'frontend'
        if '@angular/core' in deps:
            frameworks.append('angular')
            service_type = 'frontend'
        if 'vue' in deps:
            frameworks.append('vue')
            service_type = 'frontend'
        if 'next' in deps:
            frameworks.append('next')
            service_type = 'fullstack'
        
        # Backend frameworks
        if 'express' in deps:
            frameworks.append('express')
            service_type = 'backend'
        if 'fastify' in deps:
            frameworks.append('fastify')
            service_type = 'backend'
        if '@nestjs/core' in deps:
            frameworks.append('nestjs')
            service_type = 'backend'
        if 'koa' in deps:
            frameworks.append('koa')
            service_type = 'backend'
        
        # Determine service name from path
        service_name = self._extract_service_name(path)
        
        # Build system
        has_build = 'build' in scripts
        build_cmd = scripts.get('build', 'npm run build') if has_build else None
        
        # Detect output directory
        output_dir = 'build'
        if build_cmd:
            if 'dist' in build_cmd:
                output_dir = 'dist'
            elif 'vite' in build_cmd:
                output_dir = 'dist'
        
        # Port detection
        port = self._detect_port_for_service(path, frameworks, service_type)
        
        # Entry point
        entry_point = pkg.get('main', 'index.js')
        service_path = path.replace('/package.json', '')
        if service_path and not entry_point.startswith(service_path):
            entry_point = f"{service_path}/{entry_point}" if service_path else entry_point
        
        # Database
        db_info = self._detect_db_from_deps(deps)
        
        # Start command
        start_cmd = scripts.get('start', 'node index.js')
        if service_type == 'frontend' and has_build:
            start_cmd = 'npx serve -s dist'
        
        return {
            'name': service_name or pkg.get('name', 'unknown'),
            'type': service_type,
            'path': service_path or '.',
            'tech_stack': {
                'runtime': 'node',
                'version': self._extract_node_version(pkg),
                'frameworks': frameworks,
                'frontend': frameworks[0] if service_type == 'frontend' else None,
                'backend': frameworks[0] if service_type == 'backend' else None,
            },
            'build_system': {
                'needs_build': has_build,
                'build_command': build_cmd,
                'start_command': start_cmd,
                'dev_command': scripts.get('dev'),
                'output_dir': output_dir if has_build else None,
                'serve_static': service_type == 'frontend' and has_build,
                'package_manager': self._detect_package_manager(),
            },
            'server_config': {
                'port': port,
                'entry_point': entry_point,
                'port_source': 'framework_default',
            },
            'database': db_info,
            'environment': self._extract_env_from_path(service_path),
            'entry_points': [entry_point],
        }
    
    def _analyze_python_service(self, req_content: str, path: str) -> Optional[Dict]:
        """Analyze a Python service from requirements.txt"""
        
        req_lower = req_content.lower()
        
        # Detect frameworks
        frameworks = []
        service_type = 'backend'
        
        if 'fastapi' in req_lower:
            frameworks.append('fastapi')
            port = 8000
            start_cmd = 'uvicorn main:app --host 0.0.0.0 --port 8000'
        elif 'django' in req_lower:
            frameworks.append('django')
            port = 8000
            start_cmd = 'gunicorn app.wsgi:application --bind 0.0.0.0:8000'
        elif 'flask' in req_lower:
            frameworks.append('flask')
            port = 5000
            start_cmd = 'gunicorn app:app --bind 0.0.0.0:5000'
        else:
            port = 8000
            start_cmd = 'python main.py'
        
        # Service name from path
        service_name = self._extract_service_name(path)
        service_path = path.replace('/requirements.txt', '')
        
        # Database detection
        db_type = None
        orm = None
        if 'psycopg2' in req_lower or 'asyncpg' in req_lower:
            db_type = 'postgres'
        elif 'pymysql' in req_lower or 'mysqlclient' in req_lower:
            db_type = 'mysql'
        elif 'pymongo' in req_lower:
            db_type = 'mongodb'
        
        if 'sqlalchemy' in req_lower:
            orm = 'sqlalchemy'
        elif 'django' in req_lower:
            orm = 'django-orm'
        
        return {
            'name': service_name or 'python-service',
            'type': service_type,
            'path': service_path or '.',
            'tech_stack': {
                'runtime': 'python',
                'version': '3.11',
                'frameworks': frameworks,
                'frontend': None,
                'backend': frameworks[0] if frameworks else None,
            },
            'build_system': {
                'needs_build': False,
                'start_command': start_cmd,
                'package_manager': 'pip',
            },
            'server_config': {
                'port': port,
                'entry_point': f"{service_path}/main.py" if service_path else 'main.py',
                'port_source': 'framework_default',
            },
            'database': {
                'needs_database': db_type is not None,
                'type': db_type,
                'orm': orm,
            },
            'environment': self._extract_env_from_path(service_path),
            'entry_points': ['main.py'],
        }
    
    def _analyze_python_file(self, py_content: str, path: str) -> Optional[Dict]:
        """
        Analyze a standalone Python file when no requirements.txt exists.
        Detect frameworks from imports in the code.
        """
        
        py_lower = py_content.lower()
        
        # Detect frameworks from imports
        frameworks = []
        service_type = 'backend'
        port = 8000
        filename = path.split('/')[-1]
        start_cmd = f'python {filename}'
        
        if 'from fastapi' in py_lower or 'import fastapi' in py_lower:
            frameworks.append('fastapi')
            port = 8000
            start_cmd = f'uvicorn {filename.replace(".py", "")}:app --host 0.0.0.0 --port 8000'
        elif 'from flask' in py_lower or 'import flask' in py_lower:
            frameworks.append('flask')
            port = 5000
            start_cmd = f'python {filename}'
        elif 'from django' in py_lower or 'import django' in py_lower:
            frameworks.append('django')
            port = 8000
            start_cmd = 'python manage.py runserver'
        elif 'import streamlit' in py_lower or 'streamlit as st' in py_lower:
            frameworks.append('streamlit')
            port = 8501
            start_cmd = f'streamlit run {filename}'
        elif 'import gradio' in py_lower:
            frameworks.append('gradio')
            port = 7860
            start_cmd = f'python {filename}'
        
        # If no framework detected, it's a generic Python script
        if not frameworks:
            frameworks.append('python-script')
        
        # Service name from path
        service_name = self._extract_service_name(path)
        service_path = '/'.join(path.split('/')[:-1]) if '/' in path else '.'
        
        # Database detection from imports
        db_type = None
        orm = None
        if 'import psycopg2' in py_lower or 'import asyncpg' in py_lower:
            db_type = 'postgres'
        elif 'import pymongo' in py_lower:
            db_type = 'mongodb'
        elif 'import pymysql' in py_lower or 'import mysqldb' in py_lower:
            db_type = 'mysql'
        
        if 'import sqlalchemy' in py_lower or 'from sqlalchemy' in py_lower:
            orm = 'sqlalchemy'
        
        return {
            'name': service_name or 'python-app',
            'type': service_type,
            'path': service_path,
            'tech_stack': {
                'runtime': 'python',
                'version': '3.11',
                'frameworks': frameworks,
                'frontend': None,
                'backend': frameworks[0] if frameworks else None,
            },
            'build_system': {
                'needs_build': False,
                'start_command': start_cmd,
                'package_manager': 'pip',
            },
            'server_config': {
                'port': port,
                'entry_point': path,
                'port_source': 'framework_default',
            },
            'database': {
                'needs_database': db_type is not None,
                'type': db_type,
                'orm': orm,
            },
            'environment': self._extract_env_from_path(service_path),
            'entry_points': [path],
        }
        
    def _extract_service_name(self, path: str) -> str:
        """Extract service name from path"""
        parts = path.split('/')
        
        # Remove filename
        if parts[-1] in ['package.json', 'requirements.txt']:
            parts = parts[:-1]
        
        if len(parts) > 0:
            return parts[-1] if parts[-1] else (parts[-2] if len(parts) > 1 else 'app')
        
        return 'app'
    
    def _detect_port_for_service(self, path: str, frameworks: List[str], service_type: str) -> int:
        """Detect port based on service type and frameworks"""
        
        # Check for port in code files
        service_dir = path.replace('/package.json', '')
        code_files = [
            f'{service_dir}/server.js',
            f'{service_dir}/index.js',
            f'{service_dir}/src/server.js',
            f'{service_dir}/src/index.js',
            f'{service_dir}/app.js',
        ]
        
        for file_path in code_files:
            if file_path in self.files:
                content = self.files[file_path]
                patterns = [
                    r'\.listen\((\d+)\)',
                    r'PORT\s*=\s*(\d+)',
                    r'port\s*:\s*(\d+)',
                ]
                for pattern in patterns:
                    match = re.search(pattern, content)
                    if match:
                        return int(match.group(1))
        
        # Framework defaults
        if service_type == 'backend':
            if 'express' in frameworks or 'fastify' in frameworks:
                return 5000
            elif 'nestjs' in frameworks:
                return 3000
        elif service_type == 'frontend':
            if 'react' in frameworks or 'vue' in frameworks:
                return 3000
            elif 'angular' in frameworks:
                return 4200
        
        return 3000  # Default
    
    def _detect_db_from_deps(self, deps: Dict) -> Dict:
        """Detect database from dependencies"""
        db_type = None
        orm = None
        
        if 'pg' in deps or 'postgres' in deps:
            db_type = 'postgres'
        elif 'mysql2' in deps or 'mysql' in deps:
            db_type = 'mysql'
        elif 'mongodb' in deps or 'mongoose' in deps:
            db_type = 'mongodb'
        
        if 'prisma' in deps:
            orm = 'prisma'
        elif 'typeorm' in deps:
            orm = 'typeorm'
        elif 'sequelize' in deps:
            orm = 'sequelize'
        elif 'mongoose' in deps:
            orm = 'mongoose'
        
        return {
            'needs_database': db_type is not None,
            'type': db_type,
            'orm': orm,
        }
    
    def _extract_node_version(self, pkg: Dict) -> str:
        """Extract Node version from package.json"""
        engines = pkg.get('engines', {})
        if 'node' in engines:
            match = re.search(r'(\d+)', engines['node'])
            return match.group(1) if match else '18'
        return '18'
    
    def _detect_package_manager(self) -> str:
        """Detect package manager"""
        if self._find_file('yarn.lock'):
            return 'yarn'
        elif self._find_file('pnpm-lock.yaml'):
            return 'pnpm'
        elif self._find_file('package-lock.json'):
            return 'npm'
        return 'npm'
    
    def _extract_env_from_path(self, service_path: str) -> Dict:
        """Extract environment variables for a service"""
        required_vars = []
        
        # Look for .env.example in service directory
        env_paths = [
            f'{service_path}/.env.example',
            '.env.example',
        ] if service_path else ['.env.example']
        
        for env_path in env_paths:
            if env_path in self.files:
                for line in self.files[env_path].split('\n'):
                    line = line.strip()
                    if '=' in line and not line.startswith('#'):
                        var_name = line.split('=')[0].strip()
                        required_vars.append(var_name)
                
                return {
                    'required_vars': required_vars,
                    'has_env_example': True,
                }
        
        return {
            'required_vars': [],
            'has_env_example': False,
        }
    
    def _find_file(self, filename: str) -> Optional[str]:
        """Find a file by name, checking multiple locations"""
        # Check exact match first
        if filename in self.files:
            return filename
        
        # Check in subdirectories
        for path in self.files.keys():
            if path.endswith('/' + filename) or path == filename:
                return path
        
        return None