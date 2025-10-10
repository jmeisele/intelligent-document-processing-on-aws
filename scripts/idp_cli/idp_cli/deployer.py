# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Deployer Module

Handles CloudFormation stack deployment from CLI.
"""

import boto3
import time
from typing import Dict, Optional, List
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class StackDeployer:
    """Manages CloudFormation stack deployment"""
    
    def __init__(self, region: Optional[str] = None):
        """
        Initialize stack deployer
        
        Args:
            region: AWS region (optional)
        """
        self.region = region
        self.cfn = boto3.client('cloudformation', region_name=region)
    
    def deploy_stack(
        self,
        stack_name: str,
        template_path: Optional[str] = None,
        template_url: Optional[str] = None,
        parameters: Dict[str, str] = None,
        wait: bool = False
    ) -> Dict:
        """
        Deploy CloudFormation stack
        
        Args:
            stack_name: Name for the stack
            template_path: Path to local CloudFormation template (optional)
            template_url: URL to CloudFormation template in S3 (optional)
            parameters: Stack parameters
            wait: Whether to wait for stack creation to complete
        
        Returns:
            Dictionary with deployment result
        """
        logger.info(f"Deploying stack: {stack_name}")
        
        if not template_path and not template_url:
            raise ValueError("Either template_path or template_url must be provided")
        
        # Determine template source
        if template_url:
            logger.info(f"Using template URL: {template_url}")
            template_param = {'TemplateURL': template_url}
        else:
            # Read template from local file
            template_body = self._read_template(template_path)
            template_param = {'TemplateBody': template_body}
        
        # Convert parameters dict to CloudFormation format
        cfn_parameters = [
            {'ParameterKey': k, 'ParameterValue': v}
            for k, v in (parameters or {}).items()
        ]
        
        # Check if stack exists
        stack_exists = self._stack_exists(stack_name)
        
        try:
            if stack_exists:
                logger.info(f"Stack {stack_name} exists - updating")
                response = self.cfn.update_stack(
                    StackName=stack_name,
                    **template_param,
                    Parameters=cfn_parameters,
                    Capabilities=['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM', 'CAPABILITY_AUTO_EXPAND']
                )
                operation = 'UPDATE'
            else:
                logger.info(f"Creating new stack: {stack_name}")
                response = self.cfn.create_stack(
                    StackName=stack_name,
                    **template_param,
                    Parameters=cfn_parameters,
                    Capabilities=['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM', 'CAPABILITY_AUTO_EXPAND'],
                    OnFailure='ROLLBACK'
                )
                operation = 'CREATE'
            
            result = {
                'stack_name': stack_name,
                'stack_id': response.get('StackId', ''),
                'operation': operation,
                'status': 'INITIATED'
            }
            
            if wait:
                result = self._wait_for_completion(stack_name, operation)
            
            return result
            
        except self.cfn.exceptions.AlreadyExistsException:
            raise ValueError(f"Stack {stack_name} already exists. Use --update flag to update.")
        except Exception as e:
            logger.error(f"Error deploying stack: {e}")
            raise
    
    def _read_template(self, template_path: str) -> str:
        """Read CloudFormation template file"""
        template_file = Path(template_path)
        
        if not template_file.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")
        
        return template_file.read_text()
    
    def _stack_exists(self, stack_name: str) -> bool:
        """Check if stack exists"""
        try:
            self.cfn.describe_stacks(StackName=stack_name)
            return True
        except self.cfn.exceptions.ClientError as e:
            if 'does not exist' in str(e):
                return False
            raise
    
    def _wait_for_completion(self, stack_name: str, operation: str) -> Dict:
        """
        Wait for stack operation to complete
        
        Args:
            stack_name: Stack name
            operation: CREATE or UPDATE
        
        Returns:
            Dictionary with final status
        """
        logger.info(f"Waiting for {operation} to complete...")
        
        complete_statuses = {
            'CREATE': ['CREATE_COMPLETE', 'CREATE_FAILED', 'ROLLBACK_COMPLETE', 'ROLLBACK_FAILED'],
            'UPDATE': ['UPDATE_COMPLETE', 'UPDATE_FAILED', 'UPDATE_ROLLBACK_COMPLETE', 'UPDATE_ROLLBACK_FAILED']
        }
        
        success_statuses = {
            'CREATE': ['CREATE_COMPLETE'],
            'UPDATE': ['UPDATE_COMPLETE']
        }
        
        target_statuses = complete_statuses[operation]
        success_set = success_statuses[operation]
        
        while True:
            try:
                response = self.cfn.describe_stacks(StackName=stack_name)
                stacks = response.get('Stacks', [])
                
                if not stacks:
                    raise ValueError(f"Stack {stack_name} not found")
                
                stack = stacks[0]
                status = stack.get('StackStatus', '')
                
                logger.info(f"Stack status: {status}")
                
                if status in target_statuses:
                    # Operation complete
                    is_success = status in success_set
                    
                    result = {
                        'stack_name': stack_name,
                        'operation': operation,
                        'status': status,
                        'success': is_success,
                        'outputs': self._get_stack_outputs(stack)
                    }
                    
                    if not is_success:
                        result['error'] = self._get_stack_failure_reason(stack_name)
                    
                    return result
                
                # Wait before next check
                time.sleep(10)
                
            except Exception as e:
                logger.error(f"Error waiting for stack: {e}")
                raise
    
    def _get_stack_outputs(self, stack: Dict) -> Dict[str, str]:
        """Extract stack outputs as dictionary"""
        outputs = {}
        for output in stack.get('Outputs', []):
            key = output.get('OutputKey', '')
            value = output.get('OutputValue', '')
            outputs[key] = value
        return outputs
    
    def _get_stack_failure_reason(self, stack_name: str) -> str:
        """Get failure reason from stack events"""
        try:
            response = self.cfn.describe_stack_events(StackName=stack_name)
            events = response.get('StackEvents', [])
            
            # Find first failed event
            for event in events:
                status = event.get('ResourceStatus', '')
                if 'FAILED' in status:
                    reason = event.get('ResourceStatusReason', 'Unknown')
                    resource = event.get('LogicalResourceId', 'Unknown')
                    return f"{resource}: {reason}"
            
            return "Unknown failure reason"
        except Exception as e:
            return str(e)
    
    def get_stack_events(self, stack_name: str, limit: int = 20) -> List[Dict]:
        """
        Get recent stack events
        
        Args:
            stack_name: Stack name
            limit: Maximum number of events to return
        
        Returns:
            List of event dictionaries
        """
        try:
            response = self.cfn.describe_stack_events(StackName=stack_name)
            events = response.get('StackEvents', [])[:limit]
            
            return [
                {
                    'timestamp': event.get('Timestamp', ''),
                    'resource': event.get('LogicalResourceId', ''),
                    'status': event.get('ResourceStatus', ''),
                    'reason': event.get('ResourceStatusReason', '')
                }
                for event in events
            ]
        except Exception as e:
            logger.error(f"Error getting stack events: {e}")
            return []


def build_parameters(
    pattern: str,
    admin_email: str,
    max_concurrent: int = 100,
    log_level: str = 'INFO',
    enable_hitl: str = 'false',
    pattern_config: Optional[str] = None,
    custom_config: Optional[str] = None,
    additional_params: Optional[Dict[str, str]] = None
) -> Dict[str, str]:
    """
    Build CloudFormation parameters dictionary
    
    Args:
        pattern: IDP pattern (pattern-1, pattern-2, pattern-3)
        admin_email: Admin user email
        max_concurrent: Maximum concurrent workflows
        log_level: Logging level
        enable_hitl: Enable HITL (true/false)
        pattern_config: Pattern configuration preset
        custom_config: Custom configuration S3 URI
        additional_params: Additional parameters as dict
    
    Returns:
        Dictionary of parameter key-value pairs
    """
    # Map pattern names to CloudFormation values
    pattern_map = {
        'pattern-1': 'Pattern1 - Packet or Media processing with Bedrock Data Automation (BDA)',
        'pattern-2': 'Pattern2 - Packet processing with Textract and Bedrock',
        'pattern-3': 'Pattern3 - Packet processing with Textract, SageMaker(UDOP), and Bedrock'
    }
    
    parameters = {
        'AdminEmail': admin_email,
        'IDPPattern': pattern_map.get(pattern, pattern),
        'MaxConcurrentWorkflows': str(max_concurrent),
        'LogLevel': log_level,
        'EnableHITL': enable_hitl
    }
    
    # Add pattern-specific configuration
    if pattern_config:
        if pattern == 'pattern-1':
            parameters['Pattern1Configuration'] = pattern_config
        elif pattern == 'pattern-2':
            parameters['Pattern2Configuration'] = pattern_config
        elif pattern == 'pattern-3':
            parameters['Pattern3Configuration'] = pattern_config
    
    # Add custom config if provided
    if custom_config:
        parameters['CustomConfigPath'] = custom_config
    
    # Add any additional parameters
    if additional_params:
        parameters.update(additional_params)
    
    return parameters
