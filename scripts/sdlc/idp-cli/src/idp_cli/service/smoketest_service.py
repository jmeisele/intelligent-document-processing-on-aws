# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from idp_cli.util.cfn_util import CfnUtil
from idp_cli.util.path_util import PathUtil
from idp_cli.util.s3_util import S3Util
import time
import json
import os
import concurrent.futures
from loguru import logger

class SmokeTestService():
    def __init__(self, 
                 stack_name_prefix: str, 
                 file_path: str, 
                 verify_string: str):
        
        self.stack_name_prefix = stack_name_prefix
        self.stack_names = [f"{stack_name_prefix}-p1", f"{stack_name_prefix}-p2"]
        self.file_path = file_path
        self.verify_string = verify_string

        logger.debug(f"stack_names: {self.stack_names}\nfile_path: {file_path}\nverify_string: [{verify_string}]")

    def do_smoketest(self):
        """Run smoke test on both patterns in parallel"""
        def test_single_stack(stack_name):
            """Test a single stack"""
            try:
                logger.info(f"Starting smoke test for {stack_name}")
                return self._test_stack(stack_name)
            except Exception as e:
                logger.error(f"Smoke test failed for {stack_name}: {e}")
                return False
        
        # Run tests in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = {executor.submit(test_single_stack, stack_name): stack_name for stack_name in self.stack_names}
            
            results = {}
            for future in concurrent.futures.as_completed(futures):
                stack_name = futures[future]
                results[stack_name] = future.result()
        
        success = all(results.values())
        if success:
            logger.info("All smoke tests passed!")
        else:
            logger.error(f"Some smoke tests failed: {results}")
        
        return success

    def _test_stack(self, stack_name):
        """Test a single stack"""
        logger.debug(f"Getting bucket names for stack: {stack_name}")
        outputs = CfnUtil.get_stack_outputs(stack_name=stack_name)

        input_bucket_name = outputs["S3InputBucketName"]
        output_bucket_name = outputs["S3OutputBucketName"]
        logger.debug(f"Retrieved bucket names - Input: {input_bucket_name}, Output: {output_bucket_name}")
        
        # Upload test file
        file_key = self._upload_testfile(input_bucket_name)
        logger.debug(f"Uploaded test file: {file_key}")
        
        # Wait for processing
        logger.debug("Waiting for processing to complete...")
        folder_key = self._wait_for_processing(file_key, output_bucket_name)
        logger.debug("Processing completed!")
        
        # Verify result
        self._verify_result(folder_key, output_bucket_name)
        logger.debug(f"Smoke test completed successfully for {stack_name}!")
        
        return True

    def _upload_testfile(self, input_bucket_name):
        file_key = os.path.basename(self.file_path)
        logger.debug(f"Loading test file from: {self.file_path}")
        
        with open(self.file_path, 'rb') as f:
            file_bytes = f.read()
        
        logger.debug(f"Loaded {len(file_bytes)} bytes from test file")
        
        logger.debug(f"Uploading test file to bucket: {input_bucket_name}, key: {file_key}")
        S3Util.put_bytes(
            bytes_data=file_bytes,
            bucket_name=input_bucket_name,
            key=file_key 
        )
        logger.debug(f"Successfully uploaded test file")
        return file_key
        
    def _wait_for_processing(self, file_key, output_bucket_name):
        max_attempts = 100
        wait_seconds = 10
        
        logger.debug(f"Waiting for processing, checking for folder: {file_key}/ in bucket: {output_bucket_name}")
        
        for attempt in range(max_attempts):
            try:
                logger.debug(f"Attempt {attempt+1}/{max_attempts} to check for folder")
                
                response = S3Util.list_objects(
                    bucket_name=output_bucket_name,
                    prefix=f"{file_key}/",
                    max_keys=1
                )

                logger.debug(response)
                
                if response.get('Contents'):
                    logger.debug(f"Successfully found folder: {file_key}/")
                    return file_key
                    
            except Exception as e:
                logger.debug(f"Waiting for processing... Attempt {attempt+1}/{max_attempts}. Error: {str(e)}")
            
            logger.debug(f"Sleeping for {wait_seconds} seconds before next attempt")
            time.sleep(wait_seconds)
        
        logger.error(f"Processing timed out after {max_attempts * wait_seconds} seconds")
        raise TimeoutError(f"Processing timed out after {max_attempts * wait_seconds} seconds")

    def _verify_result(self, folder_key, output_bucket_name):
        logger.debug("Waiting in case the file needs time to write...")
        time.sleep(20)
        logger.debug("Verifying processing result")
        
        object_path = f"{folder_key}/pages/0/result.json"
        logger.debug(f"Looking for result file at: s3://{output_bucket_name}/{object_path}")
        
        try:
            result_json = S3Util.get_json(bucket_name=output_bucket_name, object_name=object_path)
            
            if not result_json:
                logger.error(f"Result file not found at: s3://{output_bucket_name}/{object_path}")
                raise ValueError(f"Result file not found")
            
            if "pages" not in result_json:
                logger.error("Missing 'pages' property in result JSON")
                raise ValueError("Missing 'pages' property in result JSON")
            
            if self.verify_string not in result_json["pages"][0]["representation"]["markdown"]:
                logger.error(f"Text content does not contain expected string: '{self.verify_string}'")
                logger.debug(f"Actual text starts with: '{result_json['pages'][0]['representation']['markdown'][:100]}...'")
                raise ValueError("Text content does not contain expected verification string")
            
            logger.debug("Smoke test verification passed!")
            return True
            
        except Exception as e:
            logger.error(f"Verification failed: {str(e)}")
            raise
