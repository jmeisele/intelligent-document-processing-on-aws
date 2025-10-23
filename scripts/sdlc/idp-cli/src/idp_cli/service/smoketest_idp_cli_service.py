# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import subprocess
import os
import tempfile
import re
from loguru import logger

class SmokeTestIdpCliService:
    def __init__(self, 
                 cfn_prefix: str,
                 admin_email: str,
                 account_id: str,
                 cwd: str = "../../../"):
        
        self.cfn_prefix = cfn_prefix
        self.admin_email = admin_email
        self.account_id = account_id
        self.cwd = cwd
        self.stack_name = f"{cfn_prefix}-cli"
        
        logger.debug(f"stack_name: {self.stack_name}\ncwd: {cwd}")

    def do_smoketest(self):
        """Run end-to-end smoketest using IDP CLI commands"""
        try:
            logger.info("=== IDP CLI End-to-End Smoketest ===")
            
            # Install IDP CLI
            logger.info("Installing IDP CLI...")
            subprocess.run([
                "pip", "install", "-e", f"{self.cwd}/idp_cli"
            ], check=True, cwd=self.cwd)
            
            # Deploy stack using idp-cli deploy with pattern-2
            logger.info(f"Deploying stack {self.stack_name} with pattern-2...")
            subprocess.run([
                "idp-cli", "deploy",
                "--stack-name", self.stack_name,
                "--admin-email", self.admin_email,
                "--patterns", "pattern-2"
            ], check=True, cwd=self.cwd)
            
            # Use custom batch ID to avoid parsing
            batch_id = "batch-smoketest-cli"
            
            # Run inference using IDP CLI with custom batch ID
            logger.info(f"Running inference with batch ID: {batch_id}...")
            subprocess.run([
                "idp-cli", "run-inference",
                "--stack-name", self.stack_name,
                "--file-path", f"{self.cwd}/samples/lending_package.pdf",
                "--batch-id", batch_id,
                "--monitor"
            ], check=True, cwd=self.cwd)
            
            # Download and verify results
            logger.info(f"Downloading results for batch {batch_id}...")
            with tempfile.TemporaryDirectory() as temp_dir:
                subprocess.run([
                    "idp-cli", "download-results",
                    "--stack-name", self.stack_name,
                    "--batch-id", batch_id,
                    "--output-dir", temp_dir
                ], check=True, cwd=self.cwd)
                
                # Verify results exist and contain expected content
                result_files = os.listdir(temp_dir)
                if not result_files:
                    raise Exception("No results downloaded")
                
                # Check for expected content in results (similar to smoketest_service)
                logger.info("Verifying result content...")
                found_content = False
                for file_name in result_files:
                    file_path = os.path.join(temp_dir, file_name)
                    if os.path.isfile(file_path):
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            if "ANYTOWN, USA 12345" in content:
                                found_content = True
                                break
                
                if not found_content:
                    logger.warning("Expected content 'ANYTOWN, USA 12345' not found in results")
                    
            logger.info("✅ IDP CLI smoketest completed successfully!")
            
            # Always cleanup test deployment
            logger.info(f"Cleaning up deployment {self.stack_name}...")
            subprocess.run([
                "idp-cli", "delete",
                "--stack-name", self.stack_name,
                "--force"
            ], check=True, cwd=self.cwd)
            
            return True
                
        except Exception as e:
            logger.exception(f"Error during IDP CLI smoketest: {str(e)}")
            return False
