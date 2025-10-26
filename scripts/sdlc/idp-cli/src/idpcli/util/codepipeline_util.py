# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3
import time
import re
from loguru import logger

class CodePipelineUtil:
    @staticmethod
    @staticmethod
    def wait_for_pipeline_execution(pipeline_name, execution_id=None, initial_wait_seconds=10, poll_interval_seconds=30, max_wait_minutes=90):
        """
        Monitors a CodePipeline execution until completion.
        
        Args:
            pipeline_name (str): The name of the CodePipeline to monitor
            initial_wait_seconds (int): Time to wait initially for the pipeline to start
            poll_interval_seconds (int): Time between status checks
            max_wait_minutes (int): Maximum time to wait for pipeline completion
            
        Returns:
            None
            
        Raises:
            Exception: If the pipeline execution fails or times out
        """
        client = boto3.client('codepipeline')
        
        # Get the execution ID to track
        if execution_id:
            target_execution_id = execution_id
            logger.info(f"Monitoring provided execution: {target_execution_id}")
        else:
            # Wait initially to ensure the pipeline has started
            logger.info(f"Waiting {initial_wait_seconds} seconds for pipeline '{pipeline_name}' to start...")
            time.sleep(initial_wait_seconds)
            
            # Get the latest execution ID to track the correct execution
            try:
                response = client.list_pipeline_executions(pipelineName=pipeline_name, maxResults=1)
                executions = response.get('pipelineExecutionSummaries', [])
                if not executions:
                    raise Exception(f"No executions found for pipeline '{pipeline_name}'")
                
                target_execution_id = executions[0]['pipelineExecutionId']
                logger.info(f"Monitoring execution: {target_execution_id}")
            except Exception as e:
                raise Exception(f"Failed to get pipeline execution ID: {str(e)}")
        
        start_time = time.time()
        max_wait_seconds = max_wait_minutes * 60
        
        while True:
            # Check if we've exceeded the maximum wait time
            elapsed_time = time.time() - start_time
            if elapsed_time > max_wait_seconds:
                raise Exception(f"Pipeline '{pipeline_name}' execution timed out after {max_wait_minutes} minutes")
            
            # Get the specific execution status
            try:
                response = client.get_pipeline_execution(
                    pipelineName=pipeline_name,
                    pipelineExecutionId=target_execution_id
                )
                
                execution = response.get('pipelineExecution', {})
                status = execution.get('status', 'Unknown')
                
                logger.info(f"Pipeline '{pipeline_name}' execution {target_execution_id} status: {status}")
                
                if status == 'Succeeded':
                    logger.success(f"Pipeline '{pipeline_name}' execution completed successfully!")
                    return
                elif status == 'Failed':
                    failure_reason = execution.get('statusReason', 'No reason provided')
                    message = f"Pipeline '{pipeline_name}' execution failed: {failure_reason}"
                    logger.error(message)
                    raise Exception(message)
                elif status in ['InProgress', 'Stopping']:
                    # Pipeline is still running, continue monitoring
                    pass
                elif status == 'Stopped':
                    message = f"Pipeline '{pipeline_name}' execution was stopped"
                    logger.error(message)
                    raise Exception(message)
                elif status == 'Superseded':
                    logger.info(f"Pipeline '{pipeline_name}' execution was superseded but continues running in parallel mode")
                    # Continue monitoring - superseded executions still run to completion in parallel mode
                else:
                    logger.warning(f"Unknown pipeline status: {status}")
                
                # Wait before checking again
                time.sleep(poll_interval_seconds)
                
            except Exception as e:
                if "not found" in str(e).lower():
                    raise Exception(f"Pipeline '{pipeline_name}' not found")
                else:
                    raise e

    @staticmethod
    def get_pipeline_logs(pipeline_name, execution_id=None, stage_name=None, action_name=None, max_lines=1024):
        """
        Retrieves the last specified number of lines from CodePipeline logs.
        
        Args:
            pipeline_name (str): The name of the CodePipeline
            execution_id (str, optional): Specific execution ID to get logs for. If None, gets the latest execution.
            stage_name (str, optional): Specific stage to get logs for. If None, gets logs from all stages.
            action_name (str, optional): Specific action to get logs for. If None, gets logs from all actions.
            max_lines (int): Maximum number of log lines to retrieve (default: 1024)
            
        Returns:
            dict: A dictionary containing logs organized by stage and action
            
        Raises:
            Exception: If there's an error retrieving the logs
        """
        client = boto3.client('codepipeline')
        logs_client = boto3.client('logs')
        
        try:
            # Get the latest execution ID if not provided
            if not execution_id:
                response = client.list_pipeline_executions(pipelineName=pipeline_name, maxResults=1)
                executions = response.get('pipelineExecutionSummaries', [])
                if not executions:
                    return {"error": f"No executions found for pipeline '{pipeline_name}'"}
                execution_id = executions[0]['pipelineExecutionId']
                logger.info(f"Using latest execution ID: {execution_id}")
            
            # Get pipeline state to find all stages and actions
            pipeline_state = client.get_pipeline_state(name=pipeline_name)
            stages = pipeline_state.get('stageStates', [])
            
            logs_by_stage = {}
            
            # Filter stages if stage_name is provided
            if stage_name:
                stages = [s for s in stages if s.get('stageName') == stage_name]
            
            for stage in stages:
                current_stage_name = stage.get('stageName')
                actions = stage.get('actionStates', [])
                
                # Filter actions if action_name is provided
                if action_name:
                    actions = [a for a in actions if a.get('actionName') == action_name]
                
                stage_logs = {}
                
                for action in actions:
                    current_action_name = action.get('actionName')
                    action_execution = action.get('latestExecution', {})
                    
                    # Check if this action has execution details
                    if action_execution and 'externalExecutionUrl' in action_execution:
                        url = action_execution['externalExecutionUrl']
                        
                        # Check if this is a CodeBuild URL
                        is_codebuild = 'codebuild' in url.lower()
                        
                        if is_codebuild:
                            try:
                                # Extract build ID from URL
                                # Handle different URL formats
                                build_id = None
                                
                                # Format: https://console.aws.amazon.com/codebuild/home?region=us-east-1#/builds/app-sdlc:43e0beb4-67d3-4a34-9035-b53472a59491/view/new
                                pattern1 = r'/builds/([^/]+)/view/'
                                # Format: https://console.aws.amazon.com/codebuild/home?region=us-east-1#/builds/app-sdlc:43e0beb4-67d3-4a34-9035-b53472a59491
                                pattern2 = r'/builds/([^/]+)(?:/|\$)'
                                # Format: https://us-east-1.console.aws.amazon.com/codesuite/codebuild/123456789012/projects/project-name/build/project-name:b1234567-89ab-cdef-0123-456789abcdef/
                                pattern3 = r'/build/([^/]+)(?:/|\$)'
                                
                                for pattern in [pattern1, pattern2, pattern3]:
                                    match = re.search(pattern, url)
                                    if match:
                                        build_id = match.group(1)
                                        logger.info(f"Extracted build ID from URL: {build_id}")
                                        break
                                
                                if not build_id:
                                    logger.warning(f"Could not extract build ID from URL: {url}")
                                    stage_logs[current_action_name] = [
                                        f"Could not extract build ID from URL: {url}",
                                        "Please check the URL format and update the extraction logic."
                                    ]
                                    continue
                                
                                # Get the CloudWatch log group and stream for this build
                                codebuild = boto3.client('codebuild')
                                build_info = codebuild.batch_get_builds(ids=[build_id])
                                
                                if build_info['builds']:
                                    build = build_info['builds'][0]
                                    log_group = build.get('logs', {}).get('groupName')
                                    log_stream = build.get('logs', {}).get('streamName')
                                    
                                    if log_group and log_stream:
                                        # Get the logs from CloudWatch
                                        log_events = logs_client.get_log_events(
                                            logGroupName=log_group,
                                            logStreamName=log_stream,
                                            limit=max_lines,
                                            startFromHead=False  # Get the most recent logs
                                        )
                                        
                                        # Extract the log messages
                                        log_lines = [event['message'] for event in log_events.get('events', [])]
                                        stage_logs[current_action_name] = log_lines[-max_lines:] if log_lines else ["No log events found."]
                                    else:
                                        stage_logs[current_action_name] = ["No CloudWatch logs found for this build."]
                                else:
                                    stage_logs[current_action_name] = [f"No build information found for build ID: {build_id}"]
                            except Exception as e:
                                logger.error(f"Error retrieving CodeBuild logs: {str(e)}")
                                stage_logs[current_action_name] = [
                                    f"Error retrieving logs: {str(e)}",
                                    f"URL: {url}",
                                    "Try accessing the logs directly through the AWS Console."
                                ]
                        else:
                            stage_logs[current_action_name] = [
                                f"Logs available at: {url}",
                                "Direct log retrieval not supported for this action type."
                            ]
                    else:
                        stage_logs[current_action_name] = ["No logs available for this action."]
                
                logs_by_stage[current_stage_name] = stage_logs
            
            return logs_by_stage
            
        except Exception as e:
            logger.error(f"Error retrieving pipeline logs: {str(e)}")
            raise Exception(f"Failed to retrieve logs for pipeline '{pipeline_name}': {str(e)}")
        
    @staticmethod
    def get_stage_logs(pipeline_name, stage_name, execution_id=None, max_lines=1024):
        """
        Retrieves and extracts log messages for a specific pipeline stage.
        
        Args:
            pipeline_name (str): The name of the CodePipeline
            stage_name (str): The name of the stage to extract logs from
            execution_id (str, optional): Specific execution ID to get logs for. If None, gets the latest execution.
            max_lines (int): Maximum number of log lines to retrieve (default: 1024)
            
        Returns:
            list: A list of log messages from all actions in the specified stage
            
        Raises:
            KeyError: If the specified stage is not found in the logs
            Exception: If there's an error retrieving the logs
        """
        # Get logs for the pipeline
        logs_by_stage = CodePipelineUtil.get_pipeline_logs(
            pipeline_name=pipeline_name,
            execution_id=execution_id,
            stage_name=stage_name,  # We can filter at the API level
            max_lines=max_lines
        )
        
        if stage_name not in logs_by_stage:
            raise KeyError(f"Stage '{stage_name}' not found in logs. Available stages: {', '.join(logs_by_stage.keys())}")
        
        stage_logs = logs_by_stage[stage_name]
        all_logs = []
        
        # Collect logs from all actions in the stage
        for action_name, logs in stage_logs.items():
            # Add a header for the action
            all_logs.append(f"=== {action_name} ===")
            all_logs.extend(logs)
            all_logs.append("")  # Add a blank line between actions
        
        return all_logs

    @staticmethod
    def get_execution_id_by_version(pipeline_name, version_id, wait_seconds=30):
        """Get execution ID by matching S3 version ID"""
        import time
        client = boto3.client('codepipeline')
        
        if not version_id:
            raise Exception("Version ID is required")
        
        retry_count = 10
        
        for attempt in range(retry_count):
            # Initial wait of 1 minute, then use wait_seconds for subsequent attempts
            sleep_time = 60 if attempt == 0 else wait_seconds
            time.sleep(sleep_time)
            
            response = client.list_pipeline_executions(pipelineName=pipeline_name, maxResults=10)
            executions = response.get('pipelineExecutionSummaries', [])
            
            for execution in executions:
                source_revisions = execution.get('sourceRevisions', [])
                if source_revisions and source_revisions[0].get('revisionId') == version_id:
                    logger.info(f"Found execution {execution['pipelineExecutionId']} for version {version_id}")
                    return execution['pipelineExecutionId']
            
            if attempt < retry_count - 1:
                logger.info(f"Version {version_id} not found, retrying... (attempt {attempt + 1}/{retry_count})")
        
        raise Exception(f"No execution found for version ID {version_id}")