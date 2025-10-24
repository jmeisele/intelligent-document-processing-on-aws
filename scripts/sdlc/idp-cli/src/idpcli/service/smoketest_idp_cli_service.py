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
            idp_cli_path = os.path.join(self.cwd, "idp_cli")
            subprocess.run([
                "pip", "install", "-e", "."
            ], check=True, cwd=idp_cli_path)
            
            # Deploy stack using idp-cli deploy
            logger.info(f"Deploying stack {self.stack_name}...")
            # Use pattern-2 specifically for CLI smoketest
            subprocess.run([
                "idp-cli", "deploy",
                "--stack-name", self.stack_name,
                "--pattern", "pattern-2",
                "--admin-email", self.admin_email,
                "--wait"
            ], check=True, cwd=self.cwd)
            
            # Use custom batch ID to avoid parsing
            batch_id = "batch-smoketest-cli"
            
            # Run inference using IDP CLI with custom batch ID
            logger.info(f"Running inference with batch ID: {batch_id}...")
            samples_path = "samples/"
            subprocess.run([
                "idp-cli", "run-inference",
                "--stack-name", self.stack_name,
                "--dir", samples_path,
                "--file-pattern", "lending_package.pdf",
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
                logger.info("Verifying result content...")
                
                # Look for result.json file in page 1 (Pattern 2 structure)
                result_path = os.path.join(temp_dir, batch_id, "lending_package.pdf", "pages", "1", "result.json")
                if not os.path.exists(result_path):
                    raise Exception("Expected result.json file not found in results")
                
                with open(result_path, 'r', encoding='utf-8') as f:
                    import json
                    result_data = json.load(f)
                    if "ANYTOWN, USA 12345" not in result_data.get("text", ""):
                        raise Exception("Expected content 'ANYTOWN, USA 12345' not found in result.json")
                    
            logger.info("✅ IDP CLI smoketest completed successfully!")
            return True
                
        except Exception as e:
            logger.exception(f"Error during IDP CLI smoketest: {str(e)}")
            return False
        finally:
            # Always cleanup test deployment regardless of success/failure
            try:
                logger.info(f"Cleaning up deployment {self.stack_name}...")
                subprocess.run([
                    "idp-cli", "delete",
                    "--stack-name", self.stack_name,
                    "--force"
                ], check=True, cwd=self.cwd)
                logger.info("✅ Cleanup completed successfully!")
            except Exception as cleanup_error:
                logger.error(f"Failed to cleanup deployment {self.stack_name}: {cleanup_error}")
