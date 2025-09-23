HIGH PRIORITY SECURITY ISSUES ANALYSIS
==================================================
Total High Priority Issues: 140

S3: 83 issues
  - S3-005: 30
  - S3-008: 27
  - S3-001: 26

DDB: 17 issues
  - DDB-002: 17

IAM: 14 issues
  - IAM-004: 8
  - IAM-005: 6

LAMBDA: 9 issues
  - LAMBDA-004: 3
  - LAMBDA-011: 3
  - LAMBDA-012: 3

EKS: 5 issues
  - EKS-024: 5

ASC: 3 issues
  - ASC-002: 3

CFR: 3 issues
  - CFR-004: 3

EC2: 2 issues
  - EC2-002: 2

CKV: 2 issues
  - CKV_AWS_99: 2

KMS: 2 issues
  - KMS-002: 1
  - KMS-007: 1

DETAILED ISSUE BREAKDOWN
==============================
30x: S3 bucket used as CloudFront origin lacks OAC configuration (intrinsic function ...
27x: S3 bucket lacks lifecycle policy
26x: S3 bucket does not have proper access logging or violates least privilege princi...
17x: DynamoDB data plane events are not captured by CloudTrail logging
8x: Compute resource has IAM role without permissions boundary, allowing unrestricte...
6x: Resource policy allows cross-account access without proper confused deputy preve...
5x: Container images are not being scanned for vulnerabilities (no image scanning st...
3x: No X-Ray tracing configured for Lambda function
3x: Lambda function lacks CloudWatch alarms for monitoring
3x: Lambda function shares an IAM execution role with another function
3x: AppSync GraphQL API is missing appropriate authorization method (missing or inco...
3x: CloudFront distribution allows insecure HTTP traffic (no minimum TLS version spe...
2x: EC2 instance role violates principle of least privilege
2x: Ensure Glue Security Configuration Encryption is enabled
