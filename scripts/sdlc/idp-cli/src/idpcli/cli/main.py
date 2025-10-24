# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import sys
from idpcli.service.install_service import InstallService
from idpcli.util.codepipeline_util import CodePipelineUtil
import typer
from idpcli.service.uninstall_service import UninstallService
from idpcli.service.smoketest_service import SmokeTestService
from idpcli.service.smoketest_idp_cli_service import SmokeTestIdpCliService
from dotenv import load_dotenv

from loguru import logger

load_dotenv()

app = typer.Typer()

@app.callback()
def callback():
    """
    Awesome Portal Gun
    """


@app.command()
def install(
    account_id: str = typer.Option(..., "--account-id", help="AWS Account ID"),
    cfn_prefix: str = typer.Option("idp-dev", "--cfn-prefix", help="An identifier to prefix the stack"),
    admin_email: str = typer.Option(..., "--admin-email", help="The admin email"),
    cwd: str = typer.Option("./", "--cwd", help="Current working directory"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug mode"),
    publish: bool = typer.Option(True, "--publish", help="Control publishing"),
    deploy: bool = typer.Option(True, "--deploy", help="Control deployment")
):
    """
    Install IDP Accelerator
    """
    typer.echo(f"Installing with account_id: {account_id}, cwd: {cwd}, debug: {debug}")
    service = InstallService(account_id=account_id, cfn_prefix=cfn_prefix, cwd=cwd, debug=debug)
    if publish:
        service.publish()
    
    if deploy:
        all_patterns_succeeded = service.install(admin_email=admin_email)
        if all_patterns_succeeded:
            typer.echo("Install Complete!")
        else:
            typer.echo("Install failed!", err=True)
            sys.exit(1)


@app.command()
def uninstall(
    stack_name_prefix: str = typer.Option(..., "--stack-name-prefix", help="Prefix of the stacks to uninstall"),
    account_id: str = typer.Option(..., "--account-id", help="AWS Account ID"),
    cfn_prefix: str = typer.Option("idp-dev", "--cfn-prefix", help="An identifier to prefix the stack")
):
    """
    Uninstall IDP Accelerator
    """
    try:
        typer.echo(f"Uninstalling stacks with prefix: {stack_name_prefix}")

        service = UninstallService(stack_name_prefix=stack_name_prefix, account_id=account_id, cfn_prefix=cfn_prefix)

        all_patterns_succeeded = service.uninstall()
        
        if all_patterns_succeeded:
            typer.echo("Uninstall Complete!")
        else:
            typer.echo("Uninstall failed!", err=True)
            sys.exit(1)
    except Exception as e:
        logger.exception(f"Error during uninstall process: {str(e)}")
        typer.echo(f"Uninstall failed: {str(e)}", err=True)
        sys.exit(1)


@app.command()
def smoketest(
    stack_name_prefix: str = typer.Option("idp-Stack", "--stack-name-prefix", help="Prefix of the deployed stacks to test"),
    file_path: str = typer.Option("../../../samples/lending_package.pdf", "--file-path", help="Path to the test file"),
    verify_string: str = typer.Option("ANYTOWN, USA 12345", "--verify-string", help="String to verify in the processed output")
):
    """
    Run a smoke test on both deployed IDP patterns
    """
    try:
        typer.echo(f"Running smoke test on stacks with prefix: {stack_name_prefix}")
        
        service = SmokeTestService(
            stack_name_prefix=stack_name_prefix,
            file_path=file_path,
            verify_string=verify_string
        )
        
        result = service.do_smoketest()
        
        if result:
            typer.echo("All smoke tests passed successfully!")
        else:
            typer.echo("Smoke test failed!", err=True)
            sys.exit(1)
    except Exception as e:
        logger.exception(f"Error during smoke test: {str(e)}")
        typer.echo(f"Smoke test failed: {str(e)}", err=True)
        sys.exit(1)

@app.command()
def idp_cli_smoketest(
    cfn_prefix: str = typer.Option(..., "--cfn-prefix", help="CloudFormation prefix for stack naming"),
    admin_email: str = typer.Option(..., "--admin-email", help="Admin email for deployment"),
    account_id: str = typer.Option(..., "--account-id", help="AWS account ID"),
    cwd: str = typer.Option("../../../", "--cwd", help="Working directory path")
):
    """
    End-to-end smoketest: install CLI, deploy stack, run inference, verify results
    """
    try:
        typer.echo(f"Running IDP CLI smoketest with prefix: {cfn_prefix}")
        
        service = SmokeTestIdpCliService(
            cfn_prefix=cfn_prefix,
            admin_email=admin_email,
            account_id=account_id,
            cwd=cwd
        )
        
        result = service.do_smoketest()
        
        if result:
            typer.echo("IDP CLI smoketest passed successfully!")
        else:
            typer.echo("IDP CLI smoketest failed!", err=True)
            sys.exit(1)
    except Exception as e:
        logger.exception(f"Error during IDP CLI smoketest: {str(e)}")
        typer.echo(f"IDP CLI smoketest failed: {str(e)}", err=True)
        sys.exit(1)

@app.command()
def monitor_pipeline(
    pipeline_name: str = typer.Option(..., "--pipeline-name", help="Name of the CodePipeline to monitor"),
    execution_id: str = typer.Option(None, "--execution-id", help="Specific execution ID to monitor"),
    initial_wait: int = typer.Option(10, "--initial-wait", help="Initial wait time in seconds before monitoring"),
    poll_interval: int = typer.Option(30, "--poll-interval", help="Time in seconds between status checks"),
    max_wait: int = typer.Option(90, "--max-wait", help="Maximum wait time in minutes")
):
    """
    Monitor a CodePipeline execution until completion
    """
    try:
        typer.echo(f"Monitoring pipeline: {pipeline_name}")
        
        CodePipelineUtil.wait_for_pipeline_execution(
            pipeline_name=pipeline_name,
            execution_id=execution_id,
            initial_wait_seconds=initial_wait,
            poll_interval_seconds=poll_interval,
            max_wait_minutes=max_wait
        )
        
        typer.echo("Pipeline execution completed successfully!")

    except Exception as e:
        logger.exception(f"Error monitoring pipeline: {str(e)}")
        typer.echo(f"Pipeline monitoring failed: {str(e)}", err=True)
        try:
            log_messages = CodePipelineUtil.get_stage_logs(
                pipeline_name=pipeline_name,
                stage_name="Build"
            )
            typer.echo(f"---\nCodebuild logs:")
            for message in log_messages:
                typer.echo(message)
        except Exception as e:
            typer.echo(f"Codebuild logs failed: {str(e)}", err=True)
        finally:
            sys.exit(1)