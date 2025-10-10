# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Batch Processor Module

Handles batch document upload and processing through SQS queue.
"""

import boto3
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional
import logging
from botocore.exceptions import ClientError

from .manifest_parser import parse_manifest
from .stack_info import StackInfo

logger = logging.getLogger(__name__)


class BatchProcessor:
    """Processes batches of documents for IDP pipeline"""
    
    def __init__(self, stack_name: str, config_path: Optional[str] = None, region: Optional[str] = None):
        """
        Initialize batch processor
        
        Args:
            stack_name: Name of the CloudFormation stack
            config_path: Optional path to configuration YAML
            region: AWS region (optional)
        """
        self.stack_name = stack_name
        self.config_path = config_path
        self.region = region
        
        # Initialize AWS clients
        self.s3 = boto3.client('s3', region_name=region)
        self.dynamodb = boto3.resource('dynamodb', region_name=region)
        
        # Get stack resources
        stack_info = StackInfo(stack_name, region)
        if not stack_info.validate_stack():
            raise ValueError(f"Stack '{stack_name}' is not in a valid state for operations")
        
        self.resources = stack_info.get_resources()
        logger.info(f"Initialized batch processor for stack: {stack_name}")
    
    def process_batch(
        self,
        manifest_path: str,
        steps: str = 'all',
        output_prefix: str = 'cli-batch'
    ) -> Dict:
        """
        Process batch of documents from manifest
        
        Args:
            manifest_path: Path to manifest file (CSV or JSON)
            steps: Comma-separated list of steps to execute, or 'all'
            output_prefix: Prefix for output organization
        
        Returns:
            Dictionary with batch processing results:
                - batch_id: Unique batch identifier
                - document_ids: List of document IDs
                - uploaded: Number of documents uploaded
                - queued: Number of messages sent to queue
                - failed: Number of failures
        """
        logger.info(f"Processing batch from manifest: {manifest_path}")
        
        # Generate unique batch ID
        batch_id = self._generate_batch_id(output_prefix)
        logger.info(f"Batch ID: {batch_id}")
        
        # Parse manifest
        documents = parse_manifest(manifest_path)
        logger.info(f"Found {len(documents)} documents in manifest")
        
        # Process each document
        results = {
            'batch_id': batch_id,
            'document_ids': [],
            'uploaded': 0,
            'queued': 0,
            'failed': 0,
            'manifest_path': manifest_path,
            'output_prefix': output_prefix,
            'steps': steps,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        for doc in documents:
            try:
                # Handle document upload/reference
                # S3 upload automatically triggers EventBridge -> QueueSender -> SQS
                s3_key = self._process_document(doc, batch_id)
                
                results['document_ids'].append(s3_key)  # Use s3_key as document_id for tracking
                results['queued'] += 1
                
                if doc['type'] == 'local':
                    results['uploaded'] += 1
                    
            except Exception as e:
                logger.error(f"Failed to process document {doc.get('document_id', 'unknown')}: {e}")
                results['failed'] += 1
        
        # Store batch metadata
        self._store_batch_metadata(batch_id, results)
        
        logger.info(f"Batch processing complete: {results['queued']} queued, {results['failed']} failed")
        return results
    
    def _generate_batch_id(self, prefix: str) -> str:
        """Generate unique batch ID"""
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
        unique_id = uuid.uuid4().hex[:8]
        return f"{prefix}-{timestamp}-{unique_id}"
    
    def _process_document(self, doc: Dict, batch_id: str) -> str:
        """
        Process a single document (upload or reference)
        
        Args:
            doc: Document specification from manifest
            batch_id: Batch identifier
        
        Returns:
            S3 key for the document
        """
        if doc['type'] == 'local':
            # Upload local file to InputBucket
            s3_key = self._upload_local_file(doc, batch_id)
            logger.info(f"Uploaded {doc['document_id']} to {s3_key}")
            return s3_key
        elif doc['type'] == 's3-key':
            # Document already in InputBucket, validate it exists
            s3_key = doc['path']
            self._validate_s3_key(s3_key)
            logger.info(f"Referenced existing {doc['document_id']} at {s3_key}")
            return s3_key
        else:
            raise ValueError(f"Unknown document type: {doc['type']}")
    
    def _upload_local_file(self, doc: Dict, batch_id: str) -> str:
        """Upload local file to S3 InputBucket"""
        local_path = doc['path']
        document_id = doc['document_id']
        
        # Construct S3 key: batch_id/document_id/filename
        filename = Path(local_path).name
        s3_key = f"{batch_id}/{document_id}/{filename}"
        
        # Upload file
        input_bucket = self.resources['InputBucket']
        self.s3.upload_file(
            Filename=local_path,
            Bucket=input_bucket,
            Key=s3_key
        )
        
        return s3_key
    
    def _validate_s3_key(self, s3_key: str):
        """Validate that S3 key exists in InputBucket"""
        input_bucket = self.resources['InputBucket']
        
        try:
            self.s3.head_object(Bucket=input_bucket, Key=s3_key)
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                raise ValueError(f"Document not found in InputBucket: {s3_key}")
            raise
    
    def _store_batch_metadata(self, batch_id: str, results: Dict):
        """Store batch metadata for later retrieval"""
        # Store in S3 for persistence
        output_bucket = self.resources['OutputBucket']
        metadata_key = f"cli-batches/{batch_id}/metadata.json"
        
        self.s3.put_object(
            Bucket=output_bucket,
            Key=metadata_key,
            Body=json.dumps(results, indent=2),
            ContentType='application/json'
        )
        
        logger.debug(f"Stored batch metadata at s3://{output_bucket}/{metadata_key}")
    
    def get_batch_info(self, batch_id: str) -> Optional[Dict]:
        """
        Retrieve batch metadata
        
        Args:
            batch_id: Batch identifier
        
        Returns:
            Batch metadata dictionary or None if not found
        """
        output_bucket = self.resources['OutputBucket']
        metadata_key = f"cli-batches/{batch_id}/metadata.json"
        
        try:
            response = self.s3.get_object(Bucket=output_bucket, Key=metadata_key)
            metadata = json.loads(response['Body'].read())
            return metadata
        except self.s3.exceptions.NoSuchKey:
            logger.warning(f"Batch metadata not found: {batch_id}")
            return None
        except Exception as e:
            logger.error(f"Error retrieving batch metadata: {e}")
            return None
    
    def list_batches(self, limit: int = 10) -> List[Dict]:
        """
        List recent batch jobs
        
        Args:
            limit: Maximum number of batches to return
        
        Returns:
            List of batch metadata dictionaries
        """
        output_bucket = self.resources['OutputBucket']
        prefix = "cli-batches/"
        
        try:
            response = self.s3.list_objects_v2(
                Bucket=output_bucket,
                Prefix=prefix,
                Delimiter='/'
            )
            
            # Get batch directories
            batch_prefixes = [
                p['Prefix'] for p in response.get('CommonPrefixes', [])
            ]
            
            # Sort by name (which includes timestamp) - most recent first
            batch_prefixes = sorted(batch_prefixes, reverse=True)[:limit]
            
            # Load metadata for each batch
            batches = []
            for batch_prefix in batch_prefixes:
                batch_id = batch_prefix.rstrip('/').split('/')[-1]
                batch_info = self.get_batch_info(batch_id)
                if batch_info:
                    batches.append(batch_info)
            
            return batches
            
        except Exception as e:
            logger.error(f"Error listing batches: {e}")
            return []
