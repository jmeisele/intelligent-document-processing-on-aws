# IDP CLI - Command Line Interface for Batch Document Processing

A command-line tool for batch document processing with the GenAI IDP Accelerator.

## Features

✨ **Batch Processing** - Process multiple documents from CSV/JSON manifests
📊 **Live Progress Monitoring** - Real-time updates with rich terminal UI
🔄 **Resume Monitoring** - Stop and resume monitoring without affecting processing
🎯 **Selective Step Execution** - Run specific pipeline steps only
📁 **Flexible Input** - Support for local files and S3 references
🔍 **Comprehensive Status** - Track queued, running, completed, and failed documents
📈 **Batch Analytics** - Success rates, durations, and detailed error reporting

## Installation

### Prerequisites

- Python 3.9 or higher
- AWS credentials configured (via AWS CLI or environment variables)
- An active IDP Accelerator CloudFormation stack

### Install from source

```bash
cd scripts/idp_cli
pip install -e .
```

### Install with test dependencies

```bash
cd scripts/idp_cli
pip install -e ".[test]"
```

## Quick Start

### 1. Create a manifest file

**CSV Format (sample-manifest.csv):**
```csv
document_path,document_id,type
samples/lending_package.pdf,lending-001,s3-key
samples/bank-statement-multipage.pdf,bank-statement-001,s3-key
```

**JSON Format (sample-manifest.json):**
```json
{
  "documents": [
    {
      "document_id": "lending-001",
      "path": "samples/lending_package.pdf",
      "type": "s3-key"
    }
  ]
}
```

### 2. Run batch inference with monitoring

```bash
idp-cli run-inference \
    --stack-name my-idp-stack \
    --manifest sample-manifest.csv \
    --monitor
```

### 3. Check status later

```bash
idp-cli status \
    --stack-name my-idp-stack \
    --batch-id cli-batch-20250110-153045-abc12345
```

---

## Complete Tutorial: From Zero to Results

This tutorial walks you through deploying a stack and processing your first batch of documents.

### Prerequisites

- AWS account with Bedrock access enabled
- AWS CLI configured with credentials
- Python 3.9+ and pip installed
- Local documents to process (e.g., PDFs)

### Step 1: Install the CLI

```bash
# Navigate to CLI directory
cd scripts/idp_cli

# Install in development mode
pip install -e .

# Verify installation
idp-cli --version
```

### Step 2: Deploy an IDP Stack

```bash
# Deploy Pattern 2 (Textract + Bedrock)
idp-cli deploy \
    --stack-name my-first-idp-stack \
    --pattern pattern-2 \
    --admin-email your.email@example.com \
    --max-concurrent 50 \
    --wait

# This will take 10-15 minutes
# Stack creation includes: S3 buckets, Lambda functions, Step Functions, DynamoDB tables, etc.
```

**What happens during deployment:**
- CloudFormation creates ~120 resources
- You'll receive an email with temporary admin password
- Stack outputs include web UI URL and bucket names

### Step 3: Enable Bedrock Model Access

**Important:** Before processing documents, enable Bedrock models:

```bash
# Open AWS Console → Bedrock → Model Access
# Or use this link:
echo "https://console.aws.amazon.com/bedrock/home#/modelaccess"

# Enable these models:
# - Amazon Nova (nova-lite, nova-pro)
# - Anthropic Claude (3.x Haiku, Sonnet)
# - Amazon Titan Embeddings
```

### Step 4: Prepare Your Documents

```bash
# Create a folder for your documents
mkdir ~/idp-test-documents

# Copy your PDFs (examples)
cp /path/to/your/invoice.pdf ~/idp-test-documents/
cp /path/to/your/w2-form.pdf ~/idp-test-documents/
cp /path/to/your/paystub.pdf ~/idp-test-documents/
```

### Step 5: Create a Manifest

```bash
# Create manifest file
cat > ~/my-documents.csv << EOF
document_path,document_id,type
/home/user/idp-test-documents/invoice.pdf,invoice-001,local
/home/user/idp-test-documents/w2-form.pdf,w2-2024,local
/home/user/idp-test-documents/paystub.pdf,paystub-jan,local
EOF
```

**Manifest explained:**
- `document_path` - Full path to your local PDF file
- `document_id` - Unique identifier for each document
- `type` - `local` means CLI will upload it (vs `s3-key` for files already in S3)

### Step 6: Process Your Batch

```bash
# Run inference with live monitoring
idp-cli run-inference \
    --stack-name my-first-idp-stack \
    --manifest ~/my-documents.csv \
    --output-prefix my-first-test \
    --monitor
```

**What you'll see:**
```
Validating manifest...
✓ Manifest validated successfully
Initializing batch processor for stack: my-first-idp-stack
✓ Uploaded 3 documents to InputBucket
✓ Sent 3 messages to processing queue

Monitoring Batch: my-first-test-20250110-153045-abc12345
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Status Summary
 ─────────────────────────────────────
 ✓ Completed      2      67%
 ⟳ Running        1      33%
 ⏸ Queued         0       0%
 ✗ Failed         0       0%
 
 Recent Completions
 ───────────────────────────────────────
  invoice-001     ✓ Success    45.2s
  w2-2024         ✓ Success    52.8s
```

### Step 7: Review Results

#### Option A: CLI Status Check

```bash
# Check final status
idp-cli status \
    --stack-name my-first-idp-stack \
    --batch-id my-first-test-20250110-153045-abc12345
```

#### Option B: Download Results from S3

```bash
# Get output bucket name
BUCKET=$(aws cloudformation describe-stacks \
    --stack-name my-first-idp-stack \
    --query 'Stacks[0].Outputs[?OutputKey==`S3OutputBucketName`].OutputValue' \
    --output text)

# Download all results
aws s3 cp s3://$BUCKET/my-first-test/ ./results/ --recursive

# View extraction results
cat results/invoice-001/extraction_result.json | jq .

# View assessment results
cat results/invoice-001/assessment_result.json | jq .
```

**Result files created for each document:**
- `extraction_result.json` - Extracted data fields
- `assessment_result.json` - Confidence scores
- `evaluation_result.json` - Accuracy metrics (if baseline provided)
- `summary_report.json` - Document summary

#### Option C: View in Web UI

```bash
# Get web UI URL
aws cloudformation describe-stacks \
    --stack-name my-first-idp-stack \
    --query 'Stacks[0].Outputs[?OutputKey==`ApplicationWebURL`].OutputValue' \
    --output text

# Open URL in browser
# Login with admin email and temporary password from email
# Navigate to "Documents" to see processed results
```

### Step 8: Iterate with Different Configurations

```bash
# Test with different extraction prompts
idp-cli run-inference \
    --stack-name my-first-idp-stack \
    --manifest ~/my-documents.csv \
    --config custom-extraction-prompts.yaml \
    --output-prefix test-v2 \
    --monitor

# Compare results
aws s3 ls s3://$BUCKET/my-first-test/
aws s3 ls s3://$BUCKET/test-v2/
```

### Troubleshooting

**Issue:** "Stack validation failed"
```bash
# Check stack status
aws cloudformation describe-stacks --stack-name my-first-idp-stack
```

**Issue:** "Template not found"
```bash
# Specify full template path
idp-cli deploy --template-path /full/path/to/template.yaml ...
```

**Issue:** "Access Denied" errors
```bash
# Check your AWS credentials
aws sts get-caller-identity

# Ensure you have permissions for CloudFormation, S3, Lambda, SQS
```

---

## Commands

### `run-inference`

Process a batch of documents from a manifest file.

**Usage:**
```bash
idp-cli run-inference [OPTIONS]
```

**Options:**
- `--stack-name` (required): CloudFormation stack name
- `--manifest` (required): Path to manifest file (CSV or JSON)
- `--config`: Path to custom configuration YAML file
- `--steps`: Steps to execute (default: `all`)
  - Examples: `all`, `extraction,assessment`, `classification,extraction,evaluation`
- `--output-prefix`: Output prefix for organizing results (default: `cli-batch`)
- `--monitor`: Monitor progress until completion (flag)
- `--refresh-interval`: Seconds between status checks (default: 5)
- `--region`: AWS region (optional)

**Examples:**

```bash
# Process batch with live monitoring
idp-cli run-inference \
    --stack-name my-idp-stack \
    --manifest docs.csv \
    --monitor

# Process specific steps only
idp-cli run-inference \
    --stack-name my-idp-stack \
    --manifest docs.csv \
    --steps extraction,assessment,evaluation

# Fire-and-forget mode (submit and exit)
idp-cli run-inference \
    --stack-name my-idp-stack \
    --manifest docs.csv \
    --output-prefix experiment-001

# Use custom configuration
idp-cli run-inference \
    --stack-name my-idp-stack \
    --manifest docs.csv \
    --config custom-config.yaml
```

### `status`

Check the status of a batch processing job.

**Usage:**
```bash
idp-cli status [OPTIONS]
```

**Options:**
- `--stack-name` (required): CloudFormation stack name
- `--batch-id` (required): Batch identifier
- `--wait`: Wait for all documents to complete (flag)
- `--refresh-interval`: Seconds between status checks (default: 5)
- `--region`: AWS region (optional)

**Examples:**

```bash
# Check current status once
idp-cli status \
    --stack-name my-idp-stack \
    --batch-id cli-batch-20250110-153045-abc12345

# Monitor until completion
idp-cli status \
    --stack-name my-idp-stack \
    --batch-id cli-batch-20250110-153045-abc12345 \
    --wait
```

### `list-batches`

List recent batch processing jobs.

**Usage:**
```bash
idp-cli list-batches [OPTIONS]
```

**Options:**
- `--stack-name` (required): CloudFormation stack name
- `--limit`: Maximum number of batches to list (default: 10)
- `--region`: AWS region (optional)

**Example:**

```bash
idp-cli list-batches --stack-name my-idp-stack --limit 5
```

### `validate`

Validate a manifest file without processing.

**Usage:**
```bash
idp-cli validate [OPTIONS]
```

**Options:**
- `--manifest` (required): Path to manifest file to validate

**Example:**

```bash
idp-cli validate --manifest documents.csv
```

## Manifest Format

### CSV Format

**Required Fields:**
- `document_path`: Local file path or S3 key (within InputBucket)

**Optional Fields:**
- `document_id`: Unique identifier (auto-generated from filename if omitted)
- `type`: Document type (`local` or `s3-key`, auto-detected if omitted)

**Example:**
```csv
document_path,document_id,type
/home/user/docs/w2.pdf,w2-2024,local
existing/doc.pdf,existing-doc,s3-key
samples/test.pdf,,
```

### JSON Format

**Array Format:**
```json
[
  {
    "document_id": "doc1",
    "path": "/local/path/doc1.pdf",
    "type": "local"
  }
]
```

**Object Format:**
```json
{
  "documents": [
    {
      "id": "doc1",
      "path": "folder/doc1.pdf",
      "type": "s3-key"
    }
  ],
  "config": {
    "pattern": "pattern-2",
    "output_prefix": "my-experiment"
  }
}
```

### Document Types

**`local` Type:**
- File exists on local filesystem
- CLI uploads to InputBucket automatically
- Path can be absolute or relative

**`s3-key` Type:**
- File already exists in InputBucket
- Path is the S3 key (not full S3 URI)
- CLI validates existence before processing

### Important Constraints

⚠️ **S3 Bucket Restrictions:**
- Documents must be in stack's InputBucket (cannot use external buckets)
- Baselines must be in stack's EvaluationBaselineBucket
- Use S3 keys only (not full `s3://bucket/key` URIs)

✅ **Supported:**
```csv
document_path,type
samples/doc.pdf,s3-key
/local/file.pdf,local
```

❌ **Not Supported:**
```csv
document_path,type
s3://external-bucket/doc.pdf,s3-key
```

## Architecture

### Processing Flow

```
CLI Script → Parse Manifest → Upload Files → Send to SQS Queue
                                                    ↓
                                    QueueProcessor Lambda (with concurrency control)
                                                    ↓
                                    Step Functions State Machine
                                                    ↓
                                    Document Processing Pipeline
                                                    ↓
                                    Results in OutputBucket
```

### Key Design Decisions

1. **SQS Queue Integration**: Uses existing DocumentQueue for consistency with UI-based processing
2. **Concurrency Control**: Leverages existing DynamoDB-based concurrency limiting
3. **LookupFunction Reuse**: Uses existing Lambda function for status queries
4. **Zero Code Changes**: No modifications to existing Lambda functions or infrastructure
5. **Metadata Storage**: Batch information stored in OutputBucket under `cli-batches/`

## Progress Monitoring

### Fire-and-Forget Mode

Submit batch and exit immediately:

```bash
idp-cli run-inference --stack-name my-stack --manifest docs.csv
```

Output:
```
✓ Uploaded 10 documents to InputBucket
✓ Sent 10 messages to processing queue

Batch ID: cli-batch-20250110-153045-abc12345

To monitor progress:
  idp-cli status --stack-name my-stack --batch-id cli-batch-20250110-153045-abc12345
```

### Live Monitoring Mode

Monitor progress with real-time updates:

```bash
idp-cli run-inference --stack-name my-stack --manifest docs.csv --monitor
```

Display includes:
- Overall progress bar with percentage
- Status breakdown (completed, running, queued, failed)
- Recent completions with durations
- Failed documents with error messages
- Live updates every 5 seconds (configurable)

Press `Ctrl+C` to stop monitoring (processing continues in background)

## Use Cases

### Rapid Iteration Testing

Test different prompts and configurations quickly:

```bash
# Test configuration v1
idp-cli run-inference \
    --stack-name my-stack \
    --manifest test-set.csv \
    --config config-v1.yaml \
    --output-prefix test-v1 \
    --monitor

# Test configuration v2
idp-cli run-inference \
    --stack-name my-stack \
    --manifest test-set.csv \
    --config config-v2.yaml \
    --output-prefix test-v2 \
    --monitor

# Compare results in OutputBucket under test-v1/ and test-v2/
```

### Selective Step Re-processing

Re-run specific steps with cached earlier results:

```bash
# Initial full processing
idp-cli run-inference \
    --stack-name my-stack \
    --manifest docs.csv \
    --output-prefix baseline

# Later: re-run only extraction and evaluation with new prompts
idp-cli run-inference \
    --stack-name my-stack \
    --manifest docs.csv \
    --steps extraction,assessment,evaluation \
    --config new-extraction-prompts.yaml \
    --output-prefix experiment-new-prompts
```

### Large-Scale Evaluation

Process large document sets for accuracy testing:

```bash
# Process 1000 documents with baselines
idp-cli run-inference \
    --stack-name my-stack \
    --manifest evaluation-set-1000.csv \
    --output-prefix eval-batch-001 \
    --monitor

# Results automatically include evaluation metrics
```

### CI/CD Integration

Integrate into automated testing pipelines:

```bash
#!/bin/bash
# ci-test.sh

# Run batch processing
idp-cli run-inference \
    --stack-name $STACK_NAME \
    --manifest test-suite.csv \
    --output-prefix ci-test-$BUILD_ID \
    --monitor

# Check exit code
if [ $? -eq 0 ]; then
    echo "Batch processing completed successfully"
else
    echo "Batch processing failed"
    exit 1
fi
```

## Troubleshooting

### Stack Not Found

**Error:** `Stack 'my-stack' is not in a valid state for operations`

**Solution:** Verify stack exists and is in COMPLETE state:
```bash
aws cloudformation describe-stacks --stack-name my-stack
```

### Permission Denied

**Error:** `Access Denied` when uploading files

**Solution:** Ensure your AWS credentials have permissions for:
- S3 operations on InputBucket, OutputBucket
- SQS SendMessage on DocumentQueue
- Lambda InvokeFunction on LookupFunction

### Document Not Found

**Error:** `Document not found in InputBucket: doc.pdf`

**Solution:** 
- For `s3-key` type, ensure file exists in InputBucket
- Use AWS Console or CLI to verify: `aws s3 ls s3://input-bucket/doc.pdf`

### Manifest Validation Failed

**Error:** `Duplicate document IDs found`

**Solution:** Ensure all document_id values are unique in the manifest

### Monitoring Connection Issues

**Error:** Lambda invocation errors during monitoring

**Solution:**
- Check AWS credentials are valid
- Verify network connectivity
- Check CloudWatch logs for LookupFunction

## Advanced Usage

### Custom Refresh Intervals

Adjust monitoring refresh rate:

```bash
# Fast updates (every 2 seconds)
idp-cli run-inference --stack-name my-stack --manifest docs.csv --monitor --refresh-interval 2

# Slow updates (every 30 seconds) for long-running batches
idp-cli run-inference --stack-name my-stack --manifest large-batch.csv --monitor --refresh-interval 30
```

### Processing Documents Already in S3

If documents are already uploaded to InputBucket:

```csv
document_path,document_id,type
folder1/doc1.pdf,doc1,s3-key
folder2/doc2.pdf,doc2,s3-key
```

```bash
idp-cli run-inference --stack-name my-stack --manifest existing-docs.csv
```

### Mixed Local and S3 Documents

Combine local uploads with existing S3 files:

```csv
document_path,document_id,type
/local/new-doc.pdf,new-doc,local
existing/old-doc.pdf,old-doc,s3-key
```

## Testing

Run the test suite:

```bash
cd scripts/idp_cli
pytest
```

Run tests with coverage:

```bash
pytest --cov=. --cov-report=html
```

Run specific test file:

```bash
pytest tests/test_manifest_parser.py -v
```

## Architecture Details

### SQS Queue Integration

The CLI sends messages to the existing DocumentQueue, which:
1. Maintains concurrency control via DynamoDB counter
2. Provides retry logic with exponential backoff
3. Integrates with existing Step Functions workflow
4. Enables consistent monitoring via CloudWatch

### Metadata Storage

Batch metadata is stored at:
```
s3://output-bucket/cli-batches/{batch-id}/metadata.json
```

Contains:
- Batch ID and timestamp
- List of document IDs
- Processing statistics
- Original manifest path and configuration

### Status Queries

Uses existing LookupFunction Lambda to query document status:
- Checks DynamoDB TrackingTable
- Retrieves Step Functions execution details
- Returns comprehensive status information

## Manifest Format Reference

### Field Specifications

| Field | Required | Type | Description | Example |
|-------|----------|------|-------------|---------|
| `document_path` or `path` | Yes | string | Local file path or S3 key | `/home/user/doc.pdf` or `folder/doc.pdf` |
| `document_id` or `id` | No | string | Unique identifier (auto-generated if omitted) | `doc-001` |
| `type` | No | string | `local` or `s3-key` (auto-detected if omitted) | `local` |

### Auto-Detection Rules

**Document ID:**
- If omitted, extracted from filename without extension
- Example: `folder/my-document.pdf` → `my-document`

**Document Type:**
- Absolute path or file exists → `local`
- Relative path and file doesn't exist → `s3-key`
- S3 URI (`s3://...`) → **ERROR** (not supported)

## Examples

### Example 1: Local Development Testing

```bash
# Create test manifest
cat > test-docs.csv << EOF
document_path,document_id,type
/home/user/test-docs/doc1.pdf,test-doc-1,local
/home/user/test-docs/doc2.pdf,test-doc-2,local
EOF

# Process and monitor
idp-cli run-inference \
    --stack-name dev-idp-stack \
    --manifest test-docs.csv \
    --output-prefix dev-test \
    --monitor
```

### Example 2: Evaluation with Baselines

```bash
# Manifest for evaluation documents
cat > eval-set.csv << EOF
document_path,document_id,type
eval/doc1.pdf,doc1,s3-key
eval/doc2.pdf,doc2,s3-key
eval/doc3.pdf,doc3,s3-key
EOF

# Process with evaluation
idp-cli run-inference \
    --stack-name prod-idp-stack \
    --manifest eval-set.csv \
    --steps all \
    --output-prefix accuracy-test-001 \
    --monitor
```

### Example 3: Extraction-Only Processing

```bash
# Skip OCR and classification (use cached results)
idp-cli run-inference \
    --stack-name my-stack \
    --manifest docs-already-classified.csv \
    --steps extraction,assessment \
    --output-prefix extraction-experiment
```

### Example 4: Background Processing

```bash
# Submit batch
idp-cli run-inference \
    --stack-name my-stack \
    --manifest large-batch.csv \
    --output-prefix overnight-batch

# Returns immediately with batch ID
# Batch ID: cli-batch-20250110-220045-xyz98765

# Check status next morning
idp-cli status \
    --stack-name my-stack \
    --batch-id cli-batch-20250110-220045-xyz98765
```

## Workflow Comparison

### UI-Based Workflow
1. Upload documents via web interface
2. Wait for processing
3. View results in UI
4. Manual configuration changes require UI interaction

### CLI-Based Workflow
1. Create manifest (version controlled)
2. Run batch with specific configuration (version controlled)
3. Monitor progress in terminal
4. Iterate rapidly with different configurations
5. Automate in CI/CD pipelines

## Security Considerations

### IAM Permissions

Your AWS credentials need:

**S3 Permissions:**
```json
{
  "Effect": "Allow",
  "Action": [
    "s3:PutObject",
    "s3:GetObject",
    "s3:HeadObject"
  ],
  "Resource": [
    "arn:aws:s3:::input-bucket/*",
    "arn:aws:s3:::output-bucket/*"
  ]
}
```

**SQS Permissions:**
```json
{
  "Effect": "Allow",
  "Action": "sqs:SendMessage",
  "Resource": "arn:aws:sqs:region:account:DocumentQueue"
}
```

**Lambda Permissions:**
```json
{
  "Effect": "Allow",
  "Action": "lambda:InvokeFunction",
  "Resource": "arn:aws:lambda:region:account:function:LookupFunction"
}
```

**CloudFormation Permissions:**
```json
{
  "Effect": "Allow",
  "Action": [
    "cloudformation:DescribeStacks",
    "cloudformation:ListStackResources"
  ],
  "Resource": "*"
}
```

### Best Practices

1. **Use IAM roles** instead of access keys when possible
2. **Limit bucket access** to only stack-created buckets
3. **Version control** manifests and configurations
4. **Review failed documents** before re-processing
5. **Monitor costs** for large batch operations

## Troubleshooting Common Issues

### Issue: "NoSuchBucket" error

**Cause:** Stack resources not found or incorrect stack name

**Solution:**
```bash
# Verify stack name
aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE

# Check stack outputs
aws cloudformation describe-stacks --stack-name my-stack --query 'Stacks[0].Outputs'
```

### Issue: Monitoring shows all documents as "UNKNOWN"

**Cause:** LookupFunction not found or no permissions

**Solution:**
```bash
# Verify function exists
aws lambda get-function --function-name $(aws cloudformation describe-stacks \
    --stack-name my-stack \
    --query 'Stacks[0].Outputs[?OutputKey==`LambdaLookupFunctionName`].OutputValue' \
    --output text)
```

### Issue: Documents stuck in "QUEUED" state

**Cause:** QueueProcessor Lambda may have issues or concurrency limit reached

**Solution:**
```bash
# Check queue depth
aws sqs get-queue-attributes \
    --queue-url <queue-url> \
    --attribute-names ApproximateNumberOfMessages

# Check CloudWatch logs for QueueProcessor
aws logs tail /aws/lambda/<QueueProcessor-function-name> --follow
```

## Contributing

To contribute improvements:

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Run test suite: `pytest`
5. Submit pull request

### Development Setup

```bash
cd scripts/idp_cli
pip install -e ".[test]"
pytest
```

### Adding New Features

Follow these patterns:
- Add new module in `idp_cli/`
- Add corresponding tests in `tests/`
- Update this README with usage examples
- Ensure zero changes to existing Lambda functions

## License

Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0

## Support

For issues or questions:
- Open an issue on GitHub
- Check CloudWatch logs for Lambda functions
- Review AWS Console for resource status

## Version History

### v1.0.0 (2025-01-10)
- Initial release
- Batch document processing
- Live progress monitoring
- CSV and JSON manifest support
- Comprehensive test suite
