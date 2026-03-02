"""
Workflow Executor Service
Executes workflow templates with variable substitution and conditional logic
"""
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.models.workflow_template import WorkflowTemplate, WorkflowExecution


class WorkflowExecutor:
    """Executes workflow templates"""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def execute_workflow(
        self,
        execution_id: int,
        template: WorkflowTemplate,
        input_variables: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a workflow template with given variables"""
        
        execution = self.db.query(WorkflowExecution).filter(WorkflowExecution.id == execution_id).first()
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")
        
        execution.status = "running"
        self.db.commit()
        
        results = {}
        
        try:
            # Execute each step in order
            for idx, step in enumerate(template.steps):
                execution.current_step = idx + 1
                self.db.commit()
                
                # Check dependencies
                if step.get("depends_on"):
                    for dep_step_id in step["depends_on"]:
                        if dep_step_id not in results:
                            raise Exception(f"Step {step['id']} depends on {dep_step_id} which hasn't run yet")
                
                # Evaluate condition if present
                if step.get("condition"):
                    condition_result = self._evaluate_condition(step["condition"], input_variables, results)
                    if not condition_result:
                        results[step["id"]] = {"skipped": True, "reason": "Condition not met"}
                        continue
                
                # Substitute variables in inputs
                step_inputs = self._substitute_variables(step.get("inputs", {}), input_variables, results)
                
                # Execute step based on agent type
                step_result = await self._execute_step(step["agent_type"], step_inputs, execution.user_id)
                results[step["id"]] = step_result
                
                # Update execution results
                execution.results = results
                self.db.commit()
            
            # Mark as completed
            execution.status = "completed"
            execution.completed_at = datetime.utcnow()
            self.db.commit()
            
            return results
            
        except Exception as e:
            execution.status = "failed"
            execution.error_message = str(e)
            execution.completed_at = datetime.utcnow()
            self.db.commit()
            raise
    
    def _substitute_variables(
        self,
        inputs: Dict[str, Any],
        input_variables: Dict[str, Any],
        results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Substitute {{variable}} placeholders in inputs"""
        
        def substitute_value(value: Any) -> Any:
            if isinstance(value, str):
                # Replace {{variable_name}} with actual value
                pattern = r'\{\{([^}]+)\}\}'
                matches = re.findall(pattern, value)
                
                for match in matches:
                    parts = match.strip().split('.')
                    
                    # Check if it's a step result reference (e.g., step1.result)
                    if len(parts) > 1 and parts[0] in results:
                        step_id = parts[0]
                        nested_value = results[step_id]
                        for part in parts[1:]:
                            if isinstance(nested_value, dict):
                                nested_value = nested_value.get(part)
                            else:
                                break
                        value = value.replace(f"{{{{{match}}}}}", str(nested_value))
                    
                    # Otherwise, it's an input variable
                    elif parts[0] in input_variables:
                        value = value.replace(f"{{{{{match}}}}}", str(input_variables[parts[0]]))
                
                return value
            
            elif isinstance(value, dict):
                return {k: substitute_value(v) for k, v in value.items()}
            
            elif isinstance(value, list):
                return [substitute_value(item) for item in value]
            
            return value
        
        return {k: substitute_value(v) for k, v in inputs.items()}
    
    def _evaluate_condition(
        self,
        condition: str,
        input_variables: Dict[str, Any],
        results: Dict[str, Any]
    ) -> bool:
        """Evaluate a conditional expression"""
        
        # Simple condition evaluation (can be enhanced with a proper parser)
        # Example: "{{step1.success}} == true"
        
        # Substitute variables
        condition = self._substitute_variables({"cond": condition}, input_variables, results)["cond"]
        
        # Evaluate simple comparisons
        try:
            # Warning: Using eval is dangerous in production. This is a simplified implementation.
            # In production, use a safe expression evaluator like pyparsing or a custom DSL
            return eval(condition, {"__builtins__": {}}, {})
        except Exception:
            return False
    
    async def _execute_step(
        self,
        agent_type: str,
        inputs: Dict[str, Any],
        user_id: str
    ) -> Dict[str, Any]:
        """Execute a single workflow step"""
        
        # This is a placeholder. In production, this would call actual agent services
        # For now, return mock results
        
        if agent_type == "research":
            return {
                "success": True,
                "data": f"Research results for: {inputs.get('query', 'unknown')}",
                "sources": ["source1.com", "source2.com"],
            }
        
        elif agent_type == "sheets":
            return {
                "success": True,
                "spreadsheet_id": "mock_spreadsheet_123",
                "url": "https://docs.google.com/spreadsheets/d/mock_spreadsheet_123",
            }
        
        elif agent_type == "docs":
            return {
                "success": True,
                "document_id": "mock_doc_456",
                "url": "https://docs.google.com/document/d/mock_doc_456",
            }
        
        elif agent_type == "slides":
            return {
                "success": True,
                "presentation_id": "mock_slides_789",
                "url": "https://docs.google.com/presentation/d/mock_slides_789",
            }
        
        else:
            return {
                "success": False,
                "error": f"Unknown agent type: {agent_type}",
            }
