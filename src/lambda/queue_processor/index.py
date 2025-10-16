# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3
import json
import os
from datetime import datetime, timezone
from botocore.exceptions import ClientError
import logging
from typing import Dict, Any, Tuple
from idp_common.models import Document, Status
from idp_common.docs_service import create_document_service
from aws_xray_sdk.core import xray_recorder, patch_all

patch_all()

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
logging.getLogger('idp_common.bedrock.client').setLevel(os.environ.get("BEDROCK_LOG_LEVEL", "INFO"))
# Get LOG_LEVEL from environment variable with INFO as default

sfn = boto3.client('stepfunctions')
dynamodb = boto3.resource('dynamodb')
document_service = create_document_service()
concurrency_table = dynamodb.Table(os.environ['CONCURRENCY_TABLE'])
state_machine_arn = os.environ['STATE_MACHINE_ARN']
MAX_CONCURRENT = int(os.environ.get('MAX_CONCURRENT', '5'))
COUNTER_ID = 'workflow_counter'

def update_counter(increment: bool = True) -> bool:
    """
    Update the concurrency counter
    
    Args:
        increment: Whether to increment (True) or decrement (False) the counter
        
    Returns:
        bool: True if update successful, False if at limit
        
    Raises:
        ClientError: If DynamoDB operation fails
    """
    logger.info(f"Updating counter: increment={increment}, max={MAX_CONCURRENT}")
    try:
        update_args = {
            'Key': {'counter_id': COUNTER_ID},
            'UpdateExpression': 'ADD active_count :inc',
            'ExpressionAttributeValues': {
                ':inc': 1 if increment else -1,
                ':max': MAX_CONCURRENT
            },
            'ReturnValues': 'UPDATED_NEW'
        }
        
        if increment:
            update_args['ConditionExpression'] = 'active_count < :max'
        
        logger.info(f"Counter update args: {update_args}")
        response = concurrency_table.update_item(**update_args)
        logger.info(f"Counter update response: {response}")
        return True
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            logger.warning("Concurrency limit reached")
            return False
        logger.error(f"Error updating counter: {e}")
        raise

def start_workflow(document: Document) -> Dict[str, Any]:
    """
    Start Step Functions workflow
    
    Args:
        document: The Document object to process
        
    Returns:
        Dict containing execution details
        
    Raises:
        ClientError: If Step Functions operation fails
    """
    # Update document status and timing
    document.status = Status.RUNNING
    document.start_time = datetime.now(timezone.utc).isoformat()
    
    # Compress document for Step Functions to handle large documents
    working_bucket = os.environ.get('WORKING_BUCKET')
    if working_bucket:
        # Use document compression (always compress with default 0KB threshold)
        compressed_document = document.serialize_document(working_bucket, "workflow_start", logger)
        logger.info(f"Document compressed for Step Functions workflow (always compress)")
    else:
        # Fallback to direct document dict if no working bucket
        compressed_document = document.to_dict()
        logger.warning("No WORKING_BUCKET configured, sending uncompressed document to workflow")
    
    event = {
        "document": compressed_document
    }

    logger.info(f"Starting workflow for document (size: {len(json.dumps(event, default=str))} chars)")
    
    try:
        execution = sfn.start_execution(
            stateMachineArn=state_machine_arn,
            input=json.dumps(event)
        )
        
        # Set workflow execution ARN and start_time in the document
        document.workflow_execution_arn = execution.get('executionArn', '')
        document.start_time = datetime.now(timezone.utc).isoformat()
        
        logger.info(f"Workflow started: {execution.get('executionArn', '')}")
        return execution
    except Exception as e:
        logger.error(f"Error starting workflow: {str(e)}")
        # Ensure we have a default workflow_execution_arn to avoid None errors
        document.workflow_execution_arn = document.workflow_execution_arn or ''
        raise

def process_message(record: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Process a single SQS message
    
    Args:
        record: The SQS message record
        
    Returns:
        Tuple of (success, message_id)
        
    Note: This function handles its own errors and returns success/failure
    """
    message = record['body']
    message_id = record['messageId']
    
    try:
        # Handle both compressed and uncompressed documents
        working_bucket = os.environ.get('WORKING_BUCKET')
        message_data = json.loads(message)
        document = Document.load_document(message_data, working_bucket, logger)
        object_key = document.input_key
        logger.info(f"Processing message {message_id} for object {object_key}")

        # Add X-Ray annotations
        xray_recorder.put_annotation('document_id', document.id)
        logger.info(f"X-Ray annotations added to segment 'queue_processor': document_id={document.id}")

        # Try to increment counter
        if not update_counter(increment=True):
            logger.warning(f"Concurrency limit reached for {object_key}")
            return False, message_id
        
        try:
            # Start workflow with the document
            execution = start_workflow(document)
            
            # Update document status in document service
            updated_doc = document_service.update_document(document)
            logger.info(f"Document updated: {updated_doc}")
            
            return True, message_id
            
        except Exception as e:
            logger.error(f"Error processing {object_key}: {str(e)}", exc_info=True)
            # Decrement counter on failure
            try:
                update_counter(increment=False)
            except Exception as counter_error:
                logger.error(f"Failed to decrement counter: {counter_error}", exc_info=True)
            return False, message_id
            
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in message {message_id}: {str(e)}")
        return False, message_id
        
    except KeyError as e:
        logger.error(f"Missing required field in message {message_id}: {str(e)}")
        return False, message_id
        
    except Exception as e:
        logger.error(f"Unexpected error processing message {message_id}: {str(e)}", exc_info=True)
        return False, message_id

@xray_recorder.capture('queue_processor')
def handler(event, context):
    logger.info(f"Processing event: {json.dumps(event)}")
    logger.info(f"Processing batch of {len(event['Records'])} messages")
    
    failed_message_ids = []
    
    for record in event['Records']:
        success, message_id = process_message(record)
        if not success:
            failed_message_ids.append(message_id)
    
    return {
        "batchItemFailures": [
            {"itemIdentifier": message_id} for message_id in failed_message_ids
        ]
    }
