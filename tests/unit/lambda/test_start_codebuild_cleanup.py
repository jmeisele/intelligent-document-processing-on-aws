import importlib
import sys
import types
import unittest
from unittest.mock import MagicMock


class ClientError(Exception):
    """Lightweight stand-in for botocore.exceptions.ClientError."""

    def __init__(self, error_response, operation_name):
        super().__init__(error_response)
        self.response = error_response
        self.operation_name = operation_name


fake_boto3 = types.ModuleType("boto3")


def _fake_client(service_name, config=None):  # pylint: disable=unused-argument
    return MagicMock(name=f"{service_name}_client")


fake_boto3.client = _fake_client
sys.modules.setdefault("boto3", fake_boto3)

fake_botocore = types.ModuleType("botocore")
fake_botocore_config = types.ModuleType("botocore.config")
fake_botocore_config.Config = MagicMock  # type: ignore[attr-defined]

fake_botocore_exceptions = types.ModuleType("botocore.exceptions")
fake_botocore_exceptions.ClientError = ClientError

fake_botocore.config = fake_botocore_config
fake_botocore.exceptions = fake_botocore_exceptions

sys.modules.setdefault("botocore", fake_botocore)
sys.modules.setdefault("botocore.config", fake_botocore_config)
sys.modules.setdefault("botocore.exceptions", fake_botocore_exceptions)

fake_crhelper = types.ModuleType("crhelper")


class _FakeCfnResource:
    def __init__(self, *args, **kwargs):
        self.Data = {}

    def create(self, func):
        return func

    def update(self, func):
        return func

    def poll_create(self, func):
        return func

    def poll_update(self, func):
        return func

    def delete(self, func):
        return func

    def init_failure(self, exception):
        raise exception

    def __call__(self, event, context):
        return None


fake_crhelper.CfnResource = _FakeCfnResource
sys.modules.setdefault("crhelper", fake_crhelper)

start_codebuild = importlib.import_module("src.lambda.start_codebuild.index")
start_codebuild.ClientError = ClientError  # ensure same reference in tests


class StartCodebuildCleanupTests(unittest.TestCase):
    def setUp(self):
        self.repo_name = "pattern-2"
        self.ecr_client = MagicMock(name="ecr_client")
        self.paginator = MagicMock(name="list_images_paginator")
        self.ecr_client.get_paginator.return_value = self.paginator
        start_codebuild.ECR_CLIENT = self.ecr_client

    def test_delete_all_ecr_images_handles_pagination_and_chunking(self):
        images_page_one = [{"imageDigest": f"sha256:{i:064d}"} for i in range(100)]
        images_page_two = [{"imageDigest": f"sha256:{100 + i:064d}"} for i in range(50)]
        self.paginator.paginate.return_value = [
            {"imageIds": images_page_one},
            {"imageIds": images_page_two},
        ]

        start_codebuild._delete_all_ecr_images(self.repo_name)  # pylint: disable=protected-access

        self.ecr_client.batch_delete_image.assert_any_call(
            repositoryName=self.repo_name, imageIds=images_page_one
        )
        self.ecr_client.batch_delete_image.assert_any_call(
            repositoryName=self.repo_name, imageIds=images_page_two
        )

    def test_delete_all_ecr_images_skips_when_repository_empty(self):
        self.paginator.paginate.return_value = [{"imageIds": []}]

        start_codebuild._delete_all_ecr_images(self.repo_name)  # pylint: disable=protected-access

        self.ecr_client.batch_delete_image.assert_not_called()

    def test_delete_resource_handles_repository_not_found(self):
        cleanup_event = {
            "ResourceType": "Custom::ECRRepositoryCleanup",
            "ResourceProperties": {"RepositoryName": self.repo_name},
        }
        self.paginator.paginate.side_effect = ClientError(
            {"Error": {"Code": "RepositoryNotFoundException"}}, "ListImages"
        )

        start_codebuild.delete_resource(cleanup_event, None)

        self.ecr_client.batch_delete_image.assert_not_called()

    def test_delete_resource_raises_unexpected_ecr_error(self):
        cleanup_event = {
            "ResourceType": "Custom::ECRRepositoryCleanup",
            "ResourceProperties": {"RepositoryName": self.repo_name},
        }
        self.paginator.paginate.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException"}}, "ListImages"
        )

        with self.assertRaises(ClientError):
            start_codebuild.delete_resource(cleanup_event, None)

    def test_delete_resource_ignores_non_cleanup_types(self):
        event = {"ResourceType": "Custom::CodeBuildRun", "ResourceProperties": {}}

        start_codebuild.delete_resource(event, None)

        self.ecr_client.batch_delete_image.assert_not_called()


if __name__ == "__main__":
    unittest.main()
