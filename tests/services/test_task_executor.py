"""
Tests for Non-LLM Task Types and Executors
"""

import pytest
import json
import tempfile
from pathlib import Path

from backend.app.models.task_type import (
    DataTransformTask,
    ScriptTask,
    TaskCategory,
    TaskStatus,
    ResourceQuota
)
from backend.app.services.task_executor import (
    DataTransformExecutor,
    ScriptExecutor,
    GitHubRepoCloner,
    TaskExecutorFactory
)


class TestDataTransformTask:
    """Tests for DataTransformTask model"""
    
    def test_csv_to_json_task_creation(self):
        """Test creating a CSV to JSON task"""
        task = DataTransformTask(
            name="Convert CSV to JSON",
            operation="csv_to_json",
            input_format="csv",
            output_format="json",
            input_data="name,age,city\nAlice,30,NYC\nBob,25,LA"
        )
        
        assert task.category == TaskCategory.DATA_TRANSFORM
        assert task.operation == "csv_to_json"
        assert task.input_format == "csv"
        assert task.output_format == "json"
    
    def test_invalid_operation(self):
        """Test that invalid operation raises error"""
        with pytest.raises(ValueError):
            DataTransformTask(
                name="Invalid Task",
                operation="invalid_operation",
                input_format="csv",
                output_format="json"
            )


class TestScriptTask:
    """Tests for ScriptTask model"""
    
    def test_python_script_task_creation(self):
        """Test creating a Python script task"""
        task = ScriptTask(
            name="Hello World Script",
            runtime="python3",
            script_content="print('Hello, World!')",
            resource_quota=ResourceQuota(max_execution_time_seconds=10)
        )
        
        assert task.category == TaskCategory.SCRIPT
        assert task.runtime == "python3"
        assert task.resource_quota.max_execution_time_seconds == 10
    
    def test_invalid_runtime(self):
        """Test that invalid runtime raises error"""
        with pytest.raises(ValueError):
            ScriptTask(
                name="Invalid Script",
                runtime="invalid_runtime",
                script_content="print('test')"
            )


class TestDataTransformExecutor:
    """Tests for DataTransformExecutor"""
    
    def test_csv_to_json_conversion(self):
        """Test CSV to JSON conversion"""
        csv_data = "name,age,city\nAlice,30,NYC\nBob,25,LA"
        
        task = DataTransformTask(
            name="CSV to JSON Test",
            operation="csv_to_json",
            input_format="csv",
            output_format="json",
            input_data=csv_data
        )
        
        executor = DataTransformExecutor()
        result = executor.execute(task)
        
        assert result.status == TaskStatus.COMPLETED
        assert result.result["rows_converted"] == 2
        assert result.result["columns"] == ["name", "age", "city"]
        assert result.execution_time_seconds is not None
    
    def test_csv_to_json_with_file_output(self):
        """Test CSV to JSON conversion with file output"""
        csv_data = "product,price,quantity\nApple,1.50,100\nBanana,0.75,150"
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "output.json"
            
            task = DataTransformTask(
                name="CSV to JSON File Test",
                operation="csv_to_json",
                input_format="csv",
                output_format="json",
                input_data=csv_data,
                output_file_path=str(output_file)
            )
            
            executor = DataTransformExecutor()
            result = executor.execute(task)
            
            assert result.status == TaskStatus.COMPLETED
            assert output_file.exists()
            
            # Verify file content
            with open(output_file, 'r') as f:
                data = json.load(f)
            
            assert len(data) == 2
            assert data[0]["product"] == "Apple"
            assert data[1]["price"] == "0.75"
    
    def test_json_to_csv_conversion(self):
        """Test JSON to CSV conversion"""
        json_data = json.dumps([
            {"name": "Alice", "age": "30", "city": "NYC"},
            {"name": "Bob", "age": "25", "city": "LA"}
        ])
        
        task = DataTransformTask(
            name="JSON to CSV Test",
            operation="json_to_csv",
            input_format="json",
            output_format="csv",
            input_data=json_data
        )
        
        executor = DataTransformExecutor()
        result = executor.execute(task)
        
        assert result.status == TaskStatus.COMPLETED
        assert result.result["rows_converted"] == 2
        assert result.result["columns"] == ["name", "age", "city"]
    
    def test_empty_csv_handling(self):
        """Test handling of empty CSV"""
        task = DataTransformTask(
            name="Empty CSV Test",
            operation="csv_to_json",
            input_format="csv",
            output_format="json",
            input_data="name,age,city"
        )
        
        executor = DataTransformExecutor()
        result = executor.execute(task)
        
        assert result.status == TaskStatus.COMPLETED
        assert result.result["rows_converted"] == 0
    
    def test_missing_input_data(self):
        """Test error handling for missing input data"""
        task = DataTransformTask(
            name="Missing Data Test",
            operation="csv_to_json",
            input_format="csv",
            output_format="json"
        )
        
        executor = DataTransformExecutor()
        result = executor.execute(task)
        
        assert result.status == TaskStatus.FAILED
        assert "No input data provided" in result.error


class TestScriptExecutor:
    """Tests for ScriptExecutor"""
    
    def test_python_hello_world(self):
        """Test executing a simple Python script"""
        task = ScriptTask(
            name="Python Hello World",
            runtime="python3",
            script_content="print('Hello from Python!')"
        )
        
        executor = ScriptExecutor()
        result = executor.execute(task)
        
        assert result.status == TaskStatus.COMPLETED
        assert "Hello from Python!" in result.result["stdout"]
        assert result.result["return_code"] == 0
    
    def test_python_with_args(self):
        """Test Python script with arguments"""
        task = ScriptTask(
            name="Python with Args",
            runtime="python3",
            script_content="""
import sys
print(f"Arguments: {sys.argv[1:]}")
""",
            script_args=["arg1", "arg2", "arg3"]
        )
        
        executor = ScriptExecutor()
        result = executor.execute(task)
        
        assert result.status == TaskStatus.COMPLETED
        assert "arg1" in result.result["stdout"]
        assert "arg2" in result.result["stdout"]
    
    def test_python_with_env_vars(self):
        """Test Python script with environment variables"""
        task = ScriptTask(
            name="Python with Env",
            runtime="python3",
            script_content="""
import os
print(f"MY_VAR={os.environ.get('MY_VAR')}")
""",
            environment_vars={"MY_VAR": "test_value"}
        )
        
        executor = ScriptExecutor()
        result = executor.execute(task)
        
        assert result.status == TaskStatus.COMPLETED
        assert "MY_VAR=test_value" in result.result["stdout"]
    
    def test_python_script_failure(self):
        """Test handling of Python script failure"""
        task = ScriptTask(
            name="Python Failure",
            runtime="python3",
            script_content="raise Exception('Test error')"
        )
        
        executor = ScriptExecutor()
        result = executor.execute(task)
        
        assert result.status == TaskStatus.FAILED
        assert result.error is not None
        assert "Script exited with code" in result.error
    
    def test_script_timeout(self):
        """Test script execution timeout"""
        task = ScriptTask(
            name="Python Timeout",
            runtime="python3",
            script_content="""
import time
time.sleep(10)
print('This should not print')
""",
            resource_quota=ResourceQuota(max_execution_time_seconds=1)
        )
        
        executor = ScriptExecutor()
        result = executor.execute(task)
        
        assert result.status == TaskStatus.FAILED
        assert "timed out" in result.error.lower()
    
    def test_bash_script(self):
        """Test executing a Bash script"""
        task = ScriptTask(
            name="Bash Echo",
            runtime="bash",
            script_content="echo 'Hello from Bash!'"
        )
        
        executor = ScriptExecutor()
        result = executor.execute(task)
        
        assert result.status == TaskStatus.COMPLETED
        assert "Hello from Bash!" in result.result["stdout"]


class TestGitHubRepoCloner:
    """Tests for GitHubRepoCloner"""
    
    def test_clone_small_repo(self):
        """Test cloning a small public repository"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cloner = GitHubRepoCloner()
            result = cloner.execute(
                repo_url="https://github.com/octocat/Hello-World.git",
                target_dir=str(Path(tmpdir) / "hello-world"),
                branch="master"
            )
            
            # Note: This test will fail if GitHub is unreachable
            # In a real environment, we'd mock the git command
            if result.status == TaskStatus.COMPLETED:
                assert result.result["cloned_successfully"] is True
                assert "Hello-World" in result.result["repo_name"]
                assert result.result["branch"] == "master"
    
    def test_clone_invalid_repo(self):
        """Test handling of invalid repository URL"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cloner = GitHubRepoCloner()
            result = cloner.execute(
                repo_url="https://github.com/invalid/repo-does-not-exist-12345.git",
                target_dir=str(Path(tmpdir) / "invalid"),
                branch="main"
            )
            
            assert result.status == TaskStatus.FAILED
            assert "Git clone failed" in result.error


class TestTaskExecutorFactory:
    """Tests for TaskExecutorFactory"""
    
    def test_get_data_transform_executor(self):
        """Test getting DataTransformExecutor"""
        task = DataTransformTask(
            name="Test Task",
            operation="csv_to_json",
            input_format="csv",
            output_format="json"
        )
        
        executor = TaskExecutorFactory.get_executor(task)
        assert isinstance(executor, DataTransformExecutor)
    
    def test_get_script_executor(self):
        """Test getting ScriptExecutor"""
        task = ScriptTask(
            name="Test Script",
            runtime="python3",
            script_content="print('test')"
        )
        
        executor = TaskExecutorFactory.get_executor(task)
        assert isinstance(executor, ScriptExecutor)


class TestIntegrationScenarios:
    """Integration tests for real-world scenarios"""
    
    def test_csv_processing_pipeline(self):
        """Test a complete CSV processing pipeline"""
        # Step 1: Convert CSV to JSON
        csv_data = """product,price,quantity
Apple,1.50,100
Banana,0.75,150
Orange,2.00,75"""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "products.json"
            
            task1 = DataTransformTask(
                name="CSV to JSON",
                operation="csv_to_json",
                input_format="csv",
                output_format="json",
                input_data=csv_data,
                output_file_path=str(json_file)
            )
            
            executor = DataTransformExecutor()
            result1 = executor.execute(task1)
            
            assert result1.status == TaskStatus.COMPLETED
            assert json_file.exists()
            
            # Step 2: Process JSON with Python script
            task2 = ScriptTask(
                name="Process JSON",
                runtime="python3",
                script_content=f"""
import json

with open('{json_file}', 'r') as f:
    data = json.load(f)

total_value = sum(float(item['price']) * int(item['quantity']) for item in data)
print(f"Total inventory value: ${{total_value:.2f}}")
"""
            )
            
            result2 = ScriptExecutor().execute(task2)
            
            assert result2.status == TaskStatus.COMPLETED
            assert "Total inventory value:" in result2.result["stdout"]
