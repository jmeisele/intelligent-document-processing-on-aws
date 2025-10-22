# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import boto3
import concurrent.futures
from typing import Any, Dict, Optional
from botocore.exceptions import ClientError
from idp_cli.util.cfn_util import CfnUtil
from idp_cli.util.s3_util import S3Util
from loguru import logger

class UninstallService():
    def __init__(self, stack_name_prefix: str,
                 account_id: str,
                 cfn_prefix: Optional[str] = "idp-dev"):
        self.stack_name_prefix = stack_name_prefix
        self.account_id = account_id
        self.cfn_prefix = cfn_prefix 
        self.region = os.environ.get('AWS_REGION', 'us-east-1')
        self.install_bucket_name = f"{self.cfn_prefix}-{self.account_id}-{self.region}"
        self.stack_names = [f"{stack_name_prefix}-pattern1", f"{stack_name_prefix}-pattern2"]
        logger.debug(f"stack_names: {self.stack_names}\naccount_id: {account_id}\ncfn_prefix: {cfn_prefix}\nregion:{self.region}")

    def uninstall(self):
        """Uninstall both pattern stacks in parallel"""
        def uninstall_single_stack(stack_name):
            """Uninstall a single stack completely"""
            try:
                logger.info(f"Starting uninstall of stack: {stack_name}")
                
                # Get outputs and buckets for this stack
                outputs = CfnUtil.get_stack_outputs(stack_name=stack_name)
                
                # Delete the stack first
                CfnUtil.delete_stack(stack_name=stack_name, wait=True)
                logger.info(f"Successfully deleted stack: {stack_name}")
                
                # Collect and delete buckets for this stack
                bucket_keys = [
                    "S3LoggingBucket",
                    "S3WebUIBucket", 
                    "S3EvaluationBaselineBucketName",
                    "S3InputBucketName",
                    "S3OutputBucketName",
                ]
                
                stack_buckets = []
                for key in bucket_keys:
                    if key in outputs:
                        stack_buckets.append(outputs[key])
                
                # Delete buckets for this stack
                for bucket_name in stack_buckets:
                    try:
                        S3Util.delete_bucket(bucket_name=bucket_name)
                        logger.info(f"Deleted bucket: {bucket_name}")
                    except Exception as e:
                        logger.error(f"Error deleting bucket {bucket_name}: {e}")
                
                return True
                
            except Exception as e:
                if "does not exist" in str(e):
                    logger.info(f"Stack {stack_name} does not exist, skipping")
                    return True
                else:
                    logger.error(f"Error uninstalling stack {stack_name}: {e}")
                    return False
        
        # Uninstall both stacks in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = {executor.submit(uninstall_single_stack, stack_name): stack_name for stack_name in self.stack_names}
            
            results = {}
            for future in concurrent.futures.as_completed(futures):
                stack_name = futures[future]
                results[stack_name] = future.result()
        
        # Delete shared install bucket
        try:
            S3Util.delete_bucket(bucket_name=self.install_bucket_name)
        except Exception as e:
            logger.error(f"Error deleting install bucket {self.install_bucket_name}: {e}")
        
        # Clean up pattern-specific resources
        for stack_name in self.stack_names:
            self.delete_service_role_stack(stack_name)
            self.delete_permission_boundary_policy(stack_name)
        
        success = all(results.values())
        if success:
            logger.info("Both patterns uninstalled successfully!")
        else:
            logger.error(f"Some patterns failed to uninstall: {results}")
        
        return success

    def delete_service_role_stack(self, stack_name):
        """Delete the CloudFormation service role stack if it exists"""
        service_role_stack_name = f"{stack_name}-cloudformation-service-role"
        
        try:
            logger.info(f"Attempting to delete service role stack: {service_role_stack_name}")
            response = CfnUtil.delete_stack(stack_name=service_role_stack_name, wait=True)
            logger.info(f"Successfully deleted service role stack: {service_role_stack_name}")
            logger.debug(response)
        except Exception as e:
            if "does not exist" in str(e):
                logger.debug(f"Service role stack {service_role_stack_name} does not exist, skipping")
            else:
                logger.error(f"Failed to delete service role stack {service_role_stack_name}: {e}")

    def delete_permission_boundary_policy(self, stack_name):
        """Delete the permission boundary policy if it exists"""
        policy_name = f"{stack_name}-IDPPermissionBoundary"
        
        try:
            iam = boto3.client('iam')
            policy_arn = f"arn:aws:iam::{self.account_id}:policy/{policy_name}"
            
            logger.info(f"Attempting to delete permission boundary policy: {policy_arn}")
            iam.delete_policy(PolicyArn=policy_arn)
            logger.info(f"Successfully deleted permission boundary policy: {policy_arn}")
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchEntity':
                logger.debug(f"Permission boundary policy {policy_name} does not exist, skipping")
            elif e.response['Error']['Code'] == 'DeleteConflict':
                logger.warning(f"Permission boundary policy {policy_name} is still attached to resources, skipping deletion")
            else:
                logger.error(f"Failed to delete permission boundary policy {policy_name}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error deleting permission boundary policy {policy_name}: {e}")