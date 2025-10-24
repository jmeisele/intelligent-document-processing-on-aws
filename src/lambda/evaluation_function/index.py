# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Lambda function for evaluating document extraction results.

This module provides a lambda handler that evaluates document extraction results by comparing
them against baseline results using the EvaluationService from idp_common.
"""

import json
import os
import logging
import time
import boto3
from enum import Enum
from typing import Dict, Any, Optional

from idp_common import get_config, evaluation
from idp_common.models import Document, Status
from idp_common.docs_service import create_document_service

# Environment variables
BASELINE_BUCKET = os.environ.get('BASELINE_BUCKET')
REPORTING_BUCKET = os.environ.get('REPORTING_BUCKET')
SAVE_REPORTING_FUNCTION_NAME = os.environ.get('SAVE_REPORTING_FUNCTION_NAME', 'SaveReportingData')

# Set up logging
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Create document service
document_service = create_document_service()

# Define evaluation status constants
class EvaluationStatus(Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    NO_BASELINE = "NO_BASELINE"

def update_document_evaluation_status(document: Document, status: EvaluationStatus) -> Document:
    """
    Update document evaluation status via document service
    
    Args:
        document: The Document object to update
        status: The evaluation status
        
    Returns:
        The updated Document object
        
    Raises:
        DocumentServiceError: If the operation fails
    """
    document.status = Status.COMPLETED
    document.evaluation_status = status.value
    logger.info(f"Updating document via document service: {document.input_key} with status: {status.value}")
    return document_service.update_document(document)

def extract_document_from_event(event: Dict[str, Any]) -> Optional[Document]:
    """
    Extract document from Lambda event (state machine format)
    
    Args:
        event: Lambda event containing document data
        
    Returns:
        Document object or None if not found
        
    Raises:
        ValueError: If document cannot be extracted from event
    """
    try:
        # State machine format: event['document'] contains the document data
        document_data = event.get('document')
        
        if not document_data:
            raise ValueError("No document data found in event")
                       
        # Get document from state machine format
        working_bucket = os.environ.get('WORKING_BUCKET')
        document = Document.load_document(document_data, working_bucket, logger)
        logger.info(f"Successfully loaded document with {len(document.pages)} pages and {len(document.sections)} sections")
        return document
    except Exception as e:
        logger.error(f"Error extracting document from event: {str(e)}")
        raise ValueError(f"Failed to extract document from event: {str(e)}")

def load_baseline_document(document_key: str) -> Optional[Document]:
    """
    Load baseline document from S3
    
    Args:
        document_key: The document key to load
        
    Returns:
        Document object or None if no baseline is found
        
    Raises:
        ValueError: If baseline document cannot be loaded
    """
    try:
        logger.info(f"Loading baseline document for {document_key} from {BASELINE_BUCKET}")
        
        expected_document = Document.from_s3(
            bucket=BASELINE_BUCKET, 
            input_key=document_key
        )
        
        # Check if the expected document has meaningful data
        if not expected_document.sections:
            logger.warning(f"No baseline data found for {document_key} in {BASELINE_BUCKET} (empty document)")
            return None
            
        # Baseline data exists and is valid
        logger.info(f"Successfully loaded expected (baseline) document with {len(expected_document.pages)} pages and {len(expected_document.sections)} sections")
        return expected_document
        
    except Exception as e:
        logger.error(f"Error loading baseline document: {str(e)}")
        raise ValueError(f"Failed to load baseline document: {str(e)}")



def create_response(status_code: int, message: str, additional_data: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Create a standardized response
    
    Args:
        status_code: HTTP status code
        message: Response message
        additional_data: Optional additional data to include in response
        
    Returns:
        Formatted response dictionary
    """
    response = {
        'statusCode': status_code,
        'body': json.dumps({
            'message': message,
            **(additional_data or {})
        })
    }
    return response

def handler(event, context):
    """
    Lambda function handler
    
    Args:
        event: Lambda event
        context: Lambda context
        
    Returns:
        Document in state machine format: {'document': document.serialize_document()}
    """
    actual_document = None
    start_time = time.time()
    working_bucket = os.environ.get('WORKING_BUCKET')
    
    try:
        logger.info(f"Starting evaluation process")
        
        # Extract document from event
        actual_document = extract_document_from_event(event)
        
        # Load configuration and check if evaluation is enabled
        config = get_config()
        evaluation_enabled = config.get('evaluation', {}).get('enabled', True)
        
        if not evaluation_enabled:
            logger.info("Evaluation is disabled in configuration, skipping evaluation")
            # Return document unchanged
            return {'document': actual_document.serialize_document(working_bucket, 'evaluation')}
        
        # Set document status to EVALUATING before processing
        actual_document.status = Status.EVALUATING
        document_service.update_document(actual_document)
        
        # Update document evaluation status to RUNNING
        update_document_evaluation_status(actual_document, EvaluationStatus.RUNNING)
        
        # Load baseline document
        expected_document = load_baseline_document(actual_document.input_key)
        
        # If no baseline document is found, update status and exit
        if not expected_document:
            actual_document = update_document_evaluation_status(actual_document, EvaluationStatus.NO_BASELINE)
            logger.info("Evaluation skipped - no baseline data available")
            return {'document': actual_document.serialize_document(working_bucket, 'evaluation')}
        
        # Create evaluation service
        evaluation_service = evaluation.EvaluationService(config=config)
        
        # Run evaluation
        logger.info(f"Starting evaluation for document {actual_document.id}")
        evaluated_document = evaluation_service.evaluate_document(
            actual_document=actual_document,
            expected_document=expected_document,
            store_results=True
        )
        
        # Check for evaluation errors
        if evaluated_document.errors:
            error_msg = f"Evaluation encountered errors: {evaluated_document.errors}"
            logger.error(error_msg)
            evaluated_document = update_document_evaluation_status(evaluated_document, EvaluationStatus.FAILED)
            return {'document': evaluated_document.serialize_document(working_bucket, 'evaluation')}
       
        # Save evaluation results to reporting bucket for analytics using the SaveReportingData Lambda
        try:
            logger.info(f"Saving evaluation results to {REPORTING_BUCKET} by calling Lambda {SAVE_REPORTING_FUNCTION_NAME}")
            lambda_client = boto3.client('lambda')
            lambda_response = lambda_client.invoke(
                FunctionName=SAVE_REPORTING_FUNCTION_NAME,
                InvocationType='RequestResponse',
                Payload=json.dumps({
                    'document': evaluated_document.to_dict(),
                    'reporting_bucket': REPORTING_BUCKET,
                    'data_to_save': ['evaluation_results']
                })
            )
            
            # Check the response
            response_payload = json.loads(lambda_response['Payload'].read().decode('utf-8'))
            if response_payload.get('statusCode') != 200:
                logger.warning(f"SaveReportingData Lambda returned non-200 status: {response_payload}")
            else:
                logger.info("SaveReportingData Lambda executed successfully")
        except Exception as e:
            logger.error(f"Error invoking SaveReportingData Lambda: {str(e)}")
            # Continue execution - don't fail the entire function if reporting fails
        
        # Update document evaluation status to COMPLETED
        evaluated_document = update_document_evaluation_status(evaluated_document, EvaluationStatus.COMPLETED)
        logger.info(f"Evaluation process completed successfully in {time.time() - start_time:.2f} seconds")
        
        # Return document in state machine format
        return {'document': evaluated_document.serialize_document(working_bucket, 'evaluation')}
    
    except Exception as e:
        error_msg = f"Error in lambda_handler: {str(e)}"
        logger.error(error_msg)
        
        # Update document status to FAILED if we have the document
        if actual_document:
            try:
                actual_document = update_document_evaluation_status(actual_document, EvaluationStatus.FAILED)
                return {'document': actual_document.serialize_document(working_bucket, 'evaluation')}
            except Exception as update_error:
                logger.error(f"Failed to update evaluation status: {str(update_error)}")
        
        # Re-raise exception to let Step Functions handle the error
        raise
