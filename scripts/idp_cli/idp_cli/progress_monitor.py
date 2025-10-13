# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Progress Monitor Module

Monitors batch processing progress by querying document status via LookupFunction.
"""

import boto3
import json
from typing import List, Dict, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ProgressMonitor:
    """Monitors document processing progress"""
    
    def __init__(self, stack_name: str, resources: Dict[str, str]):
        """
        Initialize progress monitor
        
        Args:
            stack_name: Name of the CloudFormation stack
            resources: Dictionary of stack resources
        """
        self.stack_name = stack_name
        self.resources = resources
        self.lambda_client = boto3.client('lambda')
        self.lookup_function = resources.get('LookupFunctionName', '')
        
        if not self.lookup_function:
            raise ValueError("LookupFunctionName not found in stack resources")
    
    def get_batch_status(self, document_ids: List[str]) -> Dict:
        """
        Get status of all documents in batch
        
        Args:
            document_ids: List of document IDs to check
        
        Returns:
            Dictionary with status summary:
                - completed: List of completed documents
                - running: List of running documents
                - queued: List of queued documents
                - failed: List of failed documents
                - all_complete: Boolean indicating if all documents are finished
                - total: Total number of documents
        """
        logger.debug(f"Checking status for {len(document_ids)} documents")
        
        status_summary = {
            'completed': [],
            'running': [],
            'queued': [],
            'failed': [],
            'all_complete': False,
            'total': len(document_ids)
        }
        
        for doc_id in document_ids:
            try:
                status = self.get_document_status(doc_id)
                status_value = status['status']
                
                if status_value == 'COMPLETED':
                    status_summary['completed'].append(status)
                elif status_value == 'FAILED':
                    status_summary['failed'].append(status)
                elif status_value in ['RUNNING', 'CLASSIFYING', 'EXTRACTING', 'ASSESSING', 'SUMMARIZING', 'EVALUATING']:
                    # Treat all processing states as RUNNING
                    status_summary['running'].append(status)
                else:
                    # QUEUED, UNKNOWN, or other states
                    status_summary['queued'].append(status)
                    
            except Exception as e:
                logger.error(f"Error getting status for {doc_id}: {e}")
                # Treat as queued if we can't determine status
                status_summary['queued'].append({
                    'document_id': doc_id,
                    'status': 'UNKNOWN',
                    'error': str(e)
                })
        
        # Check if all complete
        finished = len(status_summary['completed']) + len(status_summary['failed'])
        status_summary['all_complete'] = (finished == len(document_ids))
        
        return status_summary
    
    def get_document_status(self, doc_id: str) -> Dict:
        """
        Get detailed status of a single document
        
        Args:
            doc_id: Document identifier (object key)
        
        Returns:
            Dictionary with document status information
        """
        try:
            # Invoke LookupFunction Lambda
            payload_request = {'object_key': doc_id}
            
            response = self.lambda_client.invoke(
                FunctionName=self.lookup_function,
                InvocationType='RequestResponse',
                Payload=json.dumps(payload_request)
            )
            
            # Parse response
            payload = response['Payload'].read()
            result = json.loads(payload)
            
            # Handle Lambda error
            if response.get('FunctionError'):
                logger.error(f"Lambda error for {doc_id}: {result}")
                return {
                    'document_id': doc_id,
                    'status': 'ERROR',
                    'error': result.get('errorMessage', 'Unknown error')
                }
            
            # Extract status information (note: Lambda returns lowercase 'status')
            status = result.get('status', 'UNKNOWN')
            
            doc_status = {
                'document_id': doc_id,
                'status': status,
                'workflow_arn': result.get('WorkflowExecutionArn', ''),
                'start_time': result.get('StartTime', ''),
                'end_time': result.get('EndTime', ''),
                'duration': result.get('Duration', 0)
            }
            
            # Add status-specific fields
            if status == 'RUNNING':
                doc_status['current_step'] = result.get('CurrentStep', 'Unknown')
            elif status == 'FAILED':
                doc_status['error'] = result.get('Error', 'Unknown error')
                doc_status['failed_step'] = result.get('FailedStep', 'Unknown')
            elif status == 'COMPLETED':
                doc_status['num_sections'] = result.get('NumSections', 0)
            
            return doc_status
            
        except Exception as e:
            logger.error(f"Error querying document status for {doc_id}: {e}")
            return {
                'document_id': doc_id,
                'status': 'ERROR',
                'error': str(e)
            }
    
    def get_recent_completions(self, status_data: Dict, limit: int = 5) -> List[Dict]:
        """
        Get most recent completions
        
        Args:
            status_data: Status data from get_batch_status
            limit: Maximum number to return
        
        Returns:
            List of recently completed documents
        """
        completed = status_data.get('completed', [])
        
        # Sort by end_time (most recent first)
        sorted_completed = sorted(
            completed,
            key=lambda x: x.get('end_time', ''),
            reverse=True
        )
        
        return sorted_completed[:limit]
    
    def calculate_statistics(self, status_data: Dict) -> Dict:
        """
        Calculate batch statistics
        
        Args:
            status_data: Status data from get_batch_status
        
        Returns:
            Dictionary with statistics
        """
        total = status_data['total']
        completed = len(status_data['completed'])
        failed = len(status_data['failed'])
        running = len(status_data['running'])
        queued = len(status_data['queued'])
        
        # Calculate average duration for completed documents
        durations = [
            doc.get('duration', 0) 
            for doc in status_data['completed'] 
            if doc.get('duration', 0) > 0
        ]
        
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        # Calculate completion percentage
        finished = completed + failed
        completion_pct = (finished / total * 100) if total > 0 else 0
        
        # Calculate success rate
        success_rate = (completed / finished * 100) if finished > 0 else 0
        
        return {
            'total': total,
            'completed': completed,
            'failed': failed,
            'running': running,
            'queued': queued,
            'completion_percentage': completion_pct,
            'success_rate': success_rate,
            'avg_duration_seconds': avg_duration,
            'all_complete': status_data['all_complete']
        }
    
    def get_failed_documents(self, status_data: Dict) -> List[Dict]:
        """
        Get list of failed documents with error details
        
        Args:
            status_data: Status data from get_batch_status
        
        Returns:
            List of failed documents with error information
        """
        failed = status_data.get('failed', [])
        
        return [
            {
                'document_id': doc['document_id'],
                'error': doc.get('error', 'Unknown error'),
                'failed_step': doc.get('failed_step', 'Unknown')
            }
            for doc in failed
        ]
