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

### 1. Create a New Stack

Deploy a new IDP stack with the CLI (requires `--pattern` and `--admin-email`):

```bash
# Basic stack creation with Pattern 2
idp-cli deploy \
    --stack-name my-idp-stack \
    --pattern pattern-2 \
    --admin-email your.email@example.com \
    --wait
```

**With local configuration file:**
```bash
# Deploy with custom local config (automatically uploaded to S3)
idp-cli deploy \
    --stack-name my-idp-stack \
    --pattern pattern-2 \
    --admin-email your.email@example.com \
    --custom-config ./config_library/pattern-2/bank-statement-sample/config.yaml \
    --wait
```

**With additional parameters:**
```bash
idp-cli deploy \
    --stack-name my-idp-stack \
    --pattern pattern-2 \
    --admin-email your.email@example.com \
    --max-concurrent 200 \
    --parameters "DataRetentionInDays=90,ErrorThreshold=10" \
    --wait
```

**Important:** Stack creation takes 10-15 minutes. Use `--wait` to monitor progress, or omit it to return immediately.

### 2. Update an Existing Stack

For existing stacks, `--pattern` and `--admin-email` are optional. The CLI automatically retrieves existing values.

```bash
# Update max concurrent workflows only
idp-cli deploy \
    --stack-name my-idp-stack \
    --max-concurrent 200 \
    --wait

# Update multiple parameters
idp-cli deploy \
    --stack-name my-idp-stack \
    --max-concurrent 150 \
    --log-level DEBUG \
    --parameters "DataRetentionInDays=180" \
    --wait
```

### 3. Change Configuration on Existing Stack

Update the processing configuration by specifying a new config file:

```bash
# Update with local config file (automatically uploaded to S3)
idp-cli deploy \
    --stack-name my-idp-stack \
    --custom-config ./my-updated-config.yaml \
    --wait

# Update with S3 URI
idp-cli deploy \
    --stack-name my-idp-stack \
    --custom-config s3://my-bucket/configs/new-config.yaml \
    --wait

# Combine config change with other updates
idp-cli deploy \
    --stack-name my-idp-stack \
    --custom-config ./new-config.yaml \
    --max-concurrent 200 \
    --wait
```

**Note:** Local config files are automatically uploaded to a temporary S3 bucket and cleaned up after 30 days.

### 4. Process Documents

After your stack is deployed, process documents using one of three methods:

**Option A: From a Directory (Simplest)**
```bash
# Process all PDFs in a directory
idp-cli run-inference \
    --stack-name my-idp-stack \
    --dir ./my-documents/ \
    --monitor
```

**Option B: From an S3 Prefix**
```bash
# Process files already in InputBucket under a prefix
idp-cli run-inference \
    --stack-name my-idp-stack \
    --s3-prefix archive/2024/ \
    --monitor
```

**Option C: From a Manifest File (Most Control)**
```bash
# Create a simplified manifest file
cat > my-documents.csv << EOF
document_path
/path/to/document1.pdf
/path/to/document2.pdf
s3://external-bucket/document3.pdf
EOF

# Process with live monitoring
idp-cli run-inference \
    --stack-name my-idp-stack \
    --manifest my-documents.csv \
    --monitor
```

**Which method to use:**
- Use `--dir` for quick ad-hoc processing of local folders
- Use `--s3-prefix` when files are already in S3
- Use `--manifest` when you need precise control over document IDs or custom metadata

### 5. Check Processing Status

```bash
idp-cli status \
    --stack-name my-idp-stack \
    --batch-id cli-batch-20250110-153045-abc12345 \
    --wait
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
    --batch-prefix my-first-test \
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

To test different configurations, update the stack's config and then reprocess:

```bash
# Test with configuration v1
idp-cli deploy \
    --stack-name my-first-idp-stack \
    --custom-config ./config-v1.yaml \
    --wait

idp-cli run-inference \
    --stack-name my-first-idp-stack \
    --manifest ~/my-documents.csv \
    --batch-prefix test-v1 \
    --monitor

# Test with configuration v2
idp-cli deploy \
    --stack-name my-first-idp-stack \
    --custom-config ./config-v2.yaml \
    --wait

idp-cli run-inference \
    --stack-name my-first-idp-stack \
    --manifest ~/my-documents.csv \
    --batch-prefix test-v2 \
    --monitor

# Compare results
aws s3 ls s3://$BUCKET/test-v1/
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

### `deploy`

Deploy or update an IDP CloudFormation stack.

**Usage:**
```bash
idp-cli deploy [OPTIONS]
```

**Options:**
- `--stack-name` (required): CloudFormation stack name
- `--pattern`: IDP pattern (required for new stacks)
  - Choices: `pattern-1`, `pattern-2`, `pattern-3`
- `--admin-email`: Admin user email (required for new stacks)
- `--custom-config`: Path to local config file or S3 URI
- `--pattern-config`: Pattern configuration preset
- `--template-path`: Path to local CloudFormation template
- `--template-url`: URL to CloudFormation template in S3
- `--max-concurrent`: Maximum concurrent workflows (default: 100)
- `--log-level`: Logging level (default: INFO)
  - Choices: `DEBUG`, `INFO`, `WARN`, `ERROR`
- `--enable-hitl`: Enable Human-in-the-Loop (default: false)
  - Choices: `true`, `false`
- `--parameters`: Additional parameters as `key=value,key2=value2`
- `--wait`: Wait for stack operation to complete (flag)
- `--region`: AWS region (optional, auto-detected from AWS config)

**Behavior:**
- **New Stacks**: Requires `--pattern` and `--admin-email`
- **Existing Stacks**: Optional parameters, automatically retrieves existing values
- **Local Config Files**: Automatically uploaded to temporary S3 bucket with 30-day lifecycle

**Examples:**

```bash
# Create new stack with Pattern 2
idp-cli deploy \
    --stack-name my-idp \
    --pattern pattern-2 \
    --admin-email user@example.com \
    --wait

# Create with local config file (automatically uploaded)
idp-cli deploy \
    --stack-name my-idp \
    --pattern pattern-2 \
    --admin-email user@example.com \
    --custom-config ./my-config.yaml \
    --wait

# Update existing stack - change config only
idp-cli deploy \
    --stack-name my-idp \
    --custom-config ./updated-config.yaml \
    --wait

# Update existing stack - multiple parameters
idp-cli deploy \
    --stack-name my-idp \
    --max-concurrent 200 \
    --log-level DEBUG \
    --wait

# Create with S3 config URI
idp-cli deploy \
    --stack-name my-idp \
    --pattern pattern-2 \
    --admin-email user@example.com \
    --custom-config s3://my-bucket/configs/config.yaml
```

**Notes:**
- Local config files are uploaded to: `idp-cli/custom-configurations/config_{timestamp}_{filename}`
- Temporary bucket naming: `idp-cli-config-{account}-{region}-{suffix}`
- Auto-cleanup: 30-day lifecycle policy on uploaded configs
- Region auto-detected from AWS session or `~/.aws/config`

### `run-inference`

Process a batch of documents using the stack's current configuration.

Specify documents using ONE of:
- `--manifest`: Explicit manifest file (CSV or JSON)
- `--dir`: Local directory (auto-generates manifest, preserves paths)
- `--s3-prefix`: S3 prefix in InputBucket (auto-generates manifest)

**Note:** To change the processing configuration, use `idp-cli deploy --custom-config` to update the stack first.

**Usage:**
```bash
idp-cli run-inference [OPTIONS]
```

**Options:**
- `--stack-name` (required): CloudFormation stack name
- **Document Source** (choose ONE):
  - `--manifest`: Path to manifest file (CSV or JSON)
  - `--dir`: Local directory containing documents
  - `--s3-prefix`: S3 prefix within InputBucket
- `--batch-id`: Custom batch ID (optional, auto-generated if not provided)
- `--batch-prefix`: Batch ID prefix for auto-generation (default: `cli-batch`, only used if --batch-id not provided)
- `--file-pattern`: File pattern for directory/S3 scanning (default: `*.pdf`)
- `--recursive/--no-recursive`: Include subdirectories (default: recursive)
- `--steps`: Steps to execute (default: `all`)
  - Examples: `all`, `extraction,assessment`, `classification,extraction,evaluation`
- `--monitor`: Monitor progress until completion (flag)
- `--refresh-interval`: Seconds between status checks (default: 5)
- `--region`: AWS region (optional)

**Examples:**

```bash
# Process from explicit manifest file
idp-cli run-inference \
    --stack-name my-idp-stack \
    --manifest docs.csv \
    --monitor

# Process all PDFs in local directory
idp-cli run-inference \
    --stack-name my-idp-stack \
    --dir ./documents/ \
    --monitor

# Process S3 prefix (files already in InputBucket)
idp-cli run-inference \
    --stack-name my-idp-stack \
    --s3-prefix archive/2024/ \
    --monitor

# Process with file pattern filtering
idp-cli run-inference \
    --stack-name my-idp-stack \
    --dir ./invoices/ \
    --file-pattern "invoice*.pdf" \
    --monitor

# Process specific steps only
idp-cli run-inference \
    --stack-name my-idp-stack \
    --dir ./docs/ \
    --steps extraction,assessment,evaluation

# Non-recursive (top-level files only)
idp-cli run-inference \
    --stack-name my-idp-stack \
    --dir ./documents/ \
    --no-recursive \
    --monitor
```

**Path Preservation:**

When using `--dir`, the CLI preserves the directory structure in S3:

```
Local structure:
./dataset/
├── W2s/
│   └── w2-john.pdf
└── 1099s/
    └── 1099-vendor.pdf

Uploaded to S3 InputBucket:
{batch-id}/W2s/w2-john.pdf
{batch-id}/1099s/1099-vendor.pdf

Document IDs:
W2s/w2-john
1099s/1099-vendor
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
- `document_path`: Local file path or full S3 URI (s3://bucket/key)

**Optional Fields:**
- `document_id`: Unique identifier (auto-generated from filename if omitted)
- `baseline_source`: S3 URI or local path to baseline data for automatic evaluation

**Simplified Example (No Duplicates):**
```csv
document_path
/home/user/docs/invoice-001.pdf
/home/user/docs/invoice-002.pdf
s3://external-bucket/archive/statement.pdf
```

**With Custom IDs (For Duplicates or Organization):**
```csv
document_path,document_id
/home/user/clientA/invoice.pdf,clientA-invoice-2024
/home/user/clientB/invoice.pdf,clientB-invoice-2024
s3://data-lake/docs/report.pdf,q1-report
```

**With Baselines (For Automatic Evaluation):**
```csv
document_path,document_id,baseline_source
/local/invoice.pdf,inv-001,s3://output-bucket/validated/invoice.pdf/
/local/w2.pdf,w2-001,/local/baselines/w2-baseline/
s3://data-lake/doc.pdf,doc-001,s3://my-baseline-bucket/doc-001/
```

**Key Features:**
- Type auto-detected from path format (local file vs S3 URI)
- S3 URIs can be from **any bucket** (automatically copied to InputBucket)
- `document_id` optional - auto-generated from filename if omitted
- Duplicate filenames detected - provide explicit `document_id` values to resolve

### JSON Format

**Minimal Array Format:**
```json
[
  {
    "path": "/local/path/doc1.pdf"
  },
  {
    "path": "s3://external-bucket/doc2.pdf"
  }
]
```

**With Custom IDs:**
```json
[
  {
    "path": "/local/clientA/invoice.pdf",
    "document_id": "clientA-invoice"
  },
  {
    "path": "s3://data-lake/report.pdf",
    "document_id": "q1-report"
  }
]
```

**Object Format:**
```json
{
  "documents": [
    {
      "path": "/local/doc1.pdf",
      "document_id": "doc1"
    },
    {
      "path": "s3://bucket/doc2.pdf",
      "document_id": "doc2"
    }
  ],
  "config": {
    "pattern": "pattern-2",
    "output_prefix": "my-experiment"
  }
}
```

### Auto-Detection

**Document Type (Automatic):**
- `s3://...` → S3 file (copied from source bucket to InputBucket)
- Absolute path or existing file → Local file (uploaded)
- Invalid path → Error

**Document ID (If Not Provided):**
- Auto-generated from filename without extension
- Example: `s3://bucket/invoice-2024.pdf` → ID: `invoice-2024`

### Path Construction

All documents uploaded/copied to InputBucket follow consistent pattern:

**Manifest-based:**
```
Source: /local/invoice.pdf
Destination: {batch-id}/invoice.pdf
```

**Directory-based (preserves structure):**
```
Source: ./docs/W2s/w2.pdf
Destination: {batch-id}/W2s/w2.pdf
```

**S3 source:**
```
Source: s3://external-bucket/archive/doc.pdf
Destination: {batch-id}/doc.pdf
```

### Important Notes

✅ **Now Supported:**
- Documents from **any S3 bucket** (automatically copied)
- Local files with absolute or relative paths
- Mixed sources in same manifest

⚠️ **Duplicate Filenames:**
- If multiple files have same name, provide explicit `document_id` values
- Validation will catch duplicates and provide clear error message

❌ **Not Supported:**
- S3 URIs without `s3://` prefix
- Relative paths that don't exist locally

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

Test different configurations by updating the stack between batches:

```bash
# Test configuration v1
idp-cli deploy --stack-name my-stack --custom-config ./config-v1.yaml --wait
idp-cli run-inference \
    --stack-name my-stack \
    --manifest test-set.csv \
    --batch-prefix test-v1 \
    --monitor

# Test configuration v2
idp-cli deploy --stack-name my-stack --custom-config ./config-v2.yaml --wait
idp-cli run-inference \
    --stack-name my-stack \
    --manifest test-set.csv \
    --batch-prefix test-v2 \
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
    --batch-prefix baseline

# Later: Update config and re-run only extraction and evaluation
idp-cli deploy --stack-name my-stack --custom-config ./new-extraction-prompts.yaml --wait
idp-cli run-inference \
    --stack-name my-stack \
    --manifest docs.csv \
    --steps extraction,assessment,evaluation \
    --batch-prefix experiment-new-prompts
```

### Large-Scale Evaluation

Process large document sets for accuracy testing:

```bash
# Process 1000 documents with baselines
idp-cli run-inference \
    --stack-name my-stack \
    --manifest evaluation-set-1000.csv \
    --batch-prefix eval-batch-001 \
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
    --batch-prefix ci-test-$BUILD_ID \
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
| `document_path` or `path` | Yes | string | Local file path or S3 URI | `/home/user/doc.pdf` or `s3://bucket/doc.pdf` |
| `document_id` or `id` | No | string | Unique identifier (auto-generated from filename if omitted) | `doc-001` |

### Auto-Detection Rules

**Document Type (Automatic):**
- Starts with `s3://` → S3 file (copied from source bucket to InputBucket)
- Absolute path or file exists → Local file (uploaded to InputBucket)
- Invalid path → Error with descriptive message

**Document ID (If Not Provided):**
- Auto-generated from filename without extension
- Example: `s3://bucket/invoice-2024.pdf` → `invoice-2024`
- Example: `/local/statement.pdf` → `statement`

**Duplicate Detection:**
- Validates no duplicate document_id values
- Validates no duplicate filenames (would cause S3 key collisions)
- Clear error message if duplicates found

## Examples

### Example 1: Directory-Based Processing

```bash
# Process all PDFs in a directory (simplest approach)
idp-cli run-inference \
    --stack-name my-stack \
    --dir ./tax-documents-2024/ \
    --monitor

# With subdirectories preserved:
# Source: ./tax-documents-2024/W2s/john-w2.pdf
# Uploaded to S3: {batch-id}/W2s/john-w2.pdf
# Document ID: W2s/john-w2
```

**With file pattern filtering:**
```bash
# Process only W2 forms
idp-cli run-inference \
    --stack-name my-stack \
    --dir ./tax-documents/ \
    --file-pattern "W2*.pdf" \
    --batch-prefix w2-batch \
    --monitor

# Process only invoices
idp-cli run-inference \
    --stack-name my-stack \
    --dir ./documents/ \
    --file-pattern "invoice_*.pdf" \
    --monitor
```

**Non-recursive processing:**
```bash
# Process only top-level files (skip subdirectories)
idp-cli run-inference \
    --stack-name my-stack \
    --dir ./documents/ \
    --no-recursive \
    --monitor
```

**With custom batch ID:**
```bash
# Use meaningful batch ID for easier tracking
idp-cli run-inference \
    --stack-name my-stack \
    --dir ./tax-documents-2024/ \
    --batch-id tax-returns-2024-q1 \
    --monitor

# Useful for experiments with version tracking
idp-cli run-inference \
    --stack-name my-stack \
    --dir ./test-set/ \
    --batch-id experiment-prompt-v3 \
    --monitor
```

### Example 2: S3 Prefix Processing

```bash
# Process all documents under an S3 prefix
idp-cli run-inference \
    --stack-name my-stack \
    --s3-prefix archive/2024/invoices/ \
    --monitor

# With file pattern
idp-cli run-inference \
    --stack-name my-stack \
    --s3-prefix processed-docs/ \
    --file-pattern "*.pdf" \
    --batch-prefix reprocess-batch \
    --monitor
```

### Example 3: Manifest-Based Processing (Maximum Control)

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
    --batch-prefix dev-test \
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
    --batch-prefix accuracy-test-001 \
    --monitor
```

### Example 3: Extraction-Only Processing

```bash
# Skip OCR and classification (use cached results)
idp-cli run-inference \
    --stack-name my-stack \
    --manifest docs-already-classified.csv \
    --steps extraction,assessment \
    --batch-prefix extraction-experiment
```

### Example 4: Background Processing

```bash
# Submit batch
idp-cli run-inference \
    --stack-name my-stack \
    --manifest large-batch.csv \
    --batch-prefix overnight-batch

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
