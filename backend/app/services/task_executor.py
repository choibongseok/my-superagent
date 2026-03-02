"""
Task Executors for Non-LLM Tasks

This module provides execution engines for different task types:
- DataTransformExecutor: CSV to JSON, data transformations
- ScriptExecutor: Python/Node.js script execution
- APIExecutor: External API calls
"""

import csv
import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime
import uuid

from backend.app.models.task_type import (
    DataTransformTask,
    ScriptTask,
    APITask,
    TaskResult,
    TaskStatus,
    ResourceQuota
)


class TaskExecutor:
    """Base class for task executors"""
    
    def execute(self, task) -> TaskResult:
        """Execute a task and return result"""
        raise NotImplementedError


class DataTransformExecutor(TaskExecutor):
    """Executor for data transformation tasks"""
    
    def execute(self, task: DataTransformTask) -> TaskResult:
        """Execute data transformation task"""
        start_time = time.time()
        task_id = task.task_id or str(uuid.uuid4())
        
        try:
            if task.operation == "csv_to_json":
                result = self._csv_to_json(task)
            elif task.operation == "json_to_csv":
                result = self._json_to_csv(task)
            else:
                raise ValueError(f"Unsupported operation: {task.operation}")
            
            execution_time = time.time() - start_time
            
            return TaskResult(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                result=result,
                execution_time_seconds=execution_time,
                completed_at=datetime.utcnow()
            )
        
        except Exception as e:
            execution_time = time.time() - start_time
            return TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                error=str(e),
                execution_time_seconds=execution_time,
                completed_at=datetime.utcnow()
            )
    
    def _csv_to_json(self, task: DataTransformTask) -> Dict[str, Any]:
        """Convert CSV to JSON"""
        # Read CSV data
        if task.input_file_path:
            with open(task.input_file_path, 'r', encoding='utf-8') as f:
                csv_content = f.read()
        elif task.input_data:
            csv_content = task.input_data
        else:
            raise ValueError("No input data provided")
        
        # Parse CSV
        csv_reader = csv.DictReader(csv_content.splitlines())
        rows = list(csv_reader)
        
        # Convert to JSON
        json_data = json.dumps(rows, indent=2)
        
        # Save to file if output path specified
        if task.output_file_path:
            output_path = Path(task.output_file_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(json_data)
            
            return {
                "output_file": str(output_path),
                "rows_converted": len(rows),
                "columns": list(rows[0].keys()) if rows else []
            }
        
        return {
            "data": json_data,
            "rows_converted": len(rows),
            "columns": list(rows[0].keys()) if rows else []
        }
    
    def _json_to_csv(self, task: DataTransformTask) -> Dict[str, Any]:
        """Convert JSON to CSV"""
        # Read JSON data
        if task.input_file_path:
            with open(task.input_file_path, 'r', encoding='utf-8') as f:
                json_content = f.read()
        elif task.input_data:
            json_content = task.input_data
        else:
            raise ValueError("No input data provided")
        
        # Parse JSON
        data = json.loads(json_content)
        if not isinstance(data, list):
            raise ValueError("JSON data must be an array of objects")
        
        if not data:
            return {"rows_converted": 0, "columns": []}
        
        # Convert to CSV
        fieldnames = list(data[0].keys())
        csv_lines = []
        
        # Write header
        csv_lines.append(','.join(fieldnames))
        
        # Write rows
        for row in data:
            csv_lines.append(','.join(str(row.get(field, '')) for field in fieldnames))
        
        csv_content = '\n'.join(csv_lines)
        
        # Save to file if output path specified
        if task.output_file_path:
            output_path = Path(task.output_file_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(csv_content)
            
            return {
                "output_file": str(output_path),
                "rows_converted": len(data),
                "columns": fieldnames
            }
        
        return {
            "data": csv_content,
            "rows_converted": len(data),
            "columns": fieldnames
        }


class ScriptExecutor(TaskExecutor):
    """Executor for script tasks (Python, Node.js, Bash)"""
    
    def execute(self, task: ScriptTask) -> TaskResult:
        """Execute script task with resource limits"""
        start_time = time.time()
        task_id = task.task_id or str(uuid.uuid4())
        
        try:
            # Create temporary file for script
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix=self._get_script_extension(task.runtime),
                delete=False
            ) as f:
                f.write(task.script_content)
                script_path = f.name
            
            # Determine command
            if task.runtime.startswith('python') or task.runtime == 'python3':
                cmd = [task.runtime if task.runtime == 'python3' else task.runtime, script_path] + task.script_args
            elif task.runtime.startswith('node'):
                cmd = [task.runtime, script_path] + task.script_args
            elif task.runtime == 'bash':
                cmd = ['bash', script_path] + task.script_args
            else:
                raise ValueError(f"Unsupported runtime: {task.runtime}")
            
            # Execute script with timeout
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=task.resource_quota.max_execution_time_seconds,
                env={**task.environment_vars},
                cwd=task.working_directory
            )
            
            execution_time = time.time() - start_time
            
            # Clean up temp file
            Path(script_path).unlink(missing_ok=True)
            
            if result.returncode == 0:
                return TaskResult(
                    task_id=task_id,
                    status=TaskStatus.COMPLETED,
                    result={
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "return_code": result.returncode
                    },
                    execution_time_seconds=execution_time,
                    logs=[result.stdout],
                    completed_at=datetime.utcnow()
                )
            else:
                return TaskResult(
                    task_id=task_id,
                    status=TaskStatus.FAILED,
                    error=f"Script exited with code {result.returncode}: {result.stderr}",
                    execution_time_seconds=execution_time,
                    logs=[result.stdout, result.stderr],
                    completed_at=datetime.utcnow()
                )
        
        except subprocess.TimeoutExpired:
            execution_time = time.time() - start_time
            return TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                error=f"Script execution timed out after {task.resource_quota.max_execution_time_seconds}s",
                execution_time_seconds=execution_time,
                completed_at=datetime.utcnow()
            )
        
        except Exception as e:
            execution_time = time.time() - start_time
            return TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                error=str(e),
                execution_time_seconds=execution_time,
                completed_at=datetime.utcnow()
            )
    
    def _get_script_extension(self, runtime: str) -> str:
        """Get file extension for runtime"""
        if runtime.startswith('python'):
            return '.py'
        elif runtime.startswith('node'):
            return '.js'
        elif runtime == 'bash':
            return '.sh'
        return '.txt'


class GitHubRepoCloner(TaskExecutor):
    """Specialized executor for cloning GitHub repositories"""
    
    def execute(self, repo_url: str, target_dir: str, branch: str = "main") -> TaskResult:
        """Clone a GitHub repository"""
        start_time = time.time()
        task_id = str(uuid.uuid4())
        
        try:
            # Ensure target directory exists
            target_path = Path(target_dir)
            target_path.mkdir(parents=True, exist_ok=True)
            
            # Clone repository
            cmd = ['git', 'clone', '--branch', branch, '--depth', '1', repo_url, str(target_path)]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            execution_time = time.time() - start_time
            
            if result.returncode == 0:
                # Get repository info
                repo_name = repo_url.rstrip('/').split('/')[-1].replace('.git', '')
                
                return TaskResult(
                    task_id=task_id,
                    status=TaskStatus.COMPLETED,
                    result={
                        "repo_url": repo_url,
                        "repo_name": repo_name,
                        "branch": branch,
                        "target_dir": str(target_path),
                        "cloned_successfully": True
                    },
                    execution_time_seconds=execution_time,
                    output_file_paths=[str(target_path)],
                    logs=[result.stdout],
                    completed_at=datetime.utcnow()
                )
            else:
                return TaskResult(
                    task_id=task_id,
                    status=TaskStatus.FAILED,
                    error=f"Git clone failed: {result.stderr}",
                    execution_time_seconds=execution_time,
                    logs=[result.stdout, result.stderr],
                    completed_at=datetime.utcnow()
                )
        
        except subprocess.TimeoutExpired:
            execution_time = time.time() - start_time
            return TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                error="Repository cloning timed out after 5 minutes",
                execution_time_seconds=execution_time,
                completed_at=datetime.utcnow()
            )
        
        except Exception as e:
            execution_time = time.time() - start_time
            return TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                error=str(e),
                execution_time_seconds=execution_time,
                completed_at=datetime.utcnow()
            )


class TaskExecutorFactory:
    """Factory for creating task executors"""
    
    @staticmethod
    def get_executor(task) -> TaskExecutor:
        """Get appropriate executor for task type"""
        if isinstance(task, DataTransformTask):
            return DataTransformExecutor()
        elif isinstance(task, ScriptTask):
            return ScriptExecutor()
        else:
            raise ValueError(f"No executor available for task type: {type(task)}")
