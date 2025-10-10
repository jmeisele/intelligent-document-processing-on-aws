#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

#
# Demo Script: Deploy Stack and Process W2 Documents
#
# This script demonstrates:
# 1. Deploying an IDP stack from CLI
# 2. Processing a batch of W2 documents
# 3. Downloading results from S3
#

set -e  # Exit on error

# Configuration
STACK_NAME="idp-cli-demo-w2-$(date +%Y%m%d-%H%M%S)"
ADMIN_EMAIL="${ADMIN_EMAIL:-user@example.com}"
PATTERN="pattern-2"
MAX_CONCURRENT=5
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
W2_SAMPLES_DIR="$PROJECT_ROOT/samples/w2"
MANIFEST_FILE="/tmp/w2-manifest.csv"
RESULTS_DIR="$SCRIPT_DIR/w2-results"

echo "=========================================="
echo "IDP CLI Demo - W2 Document Processing"
echo "=========================================="
echo ""
echo "Stack Name: $STACK_NAME"
echo "Admin Email: $ADMIN_EMAIL"
echo "Pattern: $PATTERN"
echo "Max Concurrent: $MAX_CONCURRENT"
echo "W2 Samples: $W2_SAMPLES_DIR"
echo ""

# Check if CLI is installed
if ! command -v idp-cli &> /dev/null; then
    echo "ERROR: idp-cli not found. Please install first:"
    echo "  cd scripts/idp_cli && pip install -e ."
    exit 1
fi

# Check if samples directory exists
if [ ! -d "$W2_SAMPLES_DIR" ]; then
    echo "ERROR: W2 samples directory not found: $W2_SAMPLES_DIR"
    exit 1
fi

echo "Step 1: Deploying IDP Stack"
echo "----------------------------"
echo "This will take 10-15 minutes..."
echo "Using public template from S3 (us-west-2 region)"
echo ""

idp-cli deploy \
    --stack-name "$STACK_NAME" \
    --pattern "$PATTERN" \
    --admin-email "$ADMIN_EMAIL" \
    --max-concurrent "$MAX_CONCURRENT" \
    --region us-west-2 \
    --wait

echo ""
echo "✓ Stack deployed successfully!"
echo ""

# Get output bucket name
echo "Step 2: Getting Stack Resources"
echo "--------------------------------"

OUTPUT_BUCKET=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs[?OutputKey==`S3OutputBucketName`].OutputValue' \
    --output text)

echo "Output Bucket: $OUTPUT_BUCKET"
echo ""

# Create manifest for W2 documents
echo "Step 3: Creating Manifest for W2 Documents"
echo "-------------------------------------------"

# Get absolute path to W2 samples
W2_ABS_PATH=$(cd "$W2_SAMPLES_DIR" && pwd)

# Create CSV manifest header
echo "document_path,document_id,type,expected_class" > "$MANIFEST_FILE"

# Add all W2 PDFs
for pdf in "$W2_ABS_PATH"/*.pdf; do
    if [ -f "$pdf" ]; then
        filename=$(basename "$pdf")
        doc_id="${filename%.*}"  # Remove .pdf extension
        echo "$pdf,$doc_id,local,W2" >> "$MANIFEST_FILE"
    fi
done

# Count documents
DOC_COUNT=$(tail -n +2 "$MANIFEST_FILE" | wc -l)
echo "Created manifest with $DOC_COUNT W2 documents"
echo "Manifest: $MANIFEST_FILE"
echo ""

# Display first few entries
echo "First 3 documents in manifest:"
head -n 4 "$MANIFEST_FILE"
echo ""

# Process documents
echo "Step 4: Processing W2 Documents"
echo "--------------------------------"
echo "Processing $DOC_COUNT documents with concurrency=$MAX_CONCURRENT"
echo ""

BATCH_ID=$(idp-cli run-inference \
    --stack-name "$STACK_NAME" \
    --manifest "$MANIFEST_FILE" \
    --output-prefix "w2-demo" \
    --monitor 2>&1 | tee /tmp/idp-cli-output.log | grep "Batch ID:" | awk '{print $3}')

# If monitoring was interrupted, extract batch ID from output
if [ -z "$BATCH_ID" ]; then
    BATCH_ID=$(grep "Batch ID:" /tmp/idp-cli-output.log | head -1 | awk '{print $3}')
fi

echo ""
echo "✓ Batch processing complete!"
echo "Batch ID: $BATCH_ID"
echo ""

# Download results
echo "Step 5: Downloading Results from S3"
echo "------------------------------------"

mkdir -p "$RESULTS_DIR"

echo "Downloading from s3://$OUTPUT_BUCKET/w2-demo/ to $RESULTS_DIR/"
aws s3 cp "s3://$OUTPUT_BUCKET/w2-demo/" "$RESULTS_DIR/" --recursive

echo ""
echo "✓ Results downloaded to: $RESULTS_DIR/"
echo ""

# Summary
echo "=========================================="
echo "Demo Complete!"
echo "=========================================="
echo ""
echo "Stack Name: $STACK_NAME"
echo "Output Bucket: $OUTPUT_BUCKET"
echo "Batch ID: $BATCH_ID"
echo "Results Location: $RESULTS_DIR/"
echo ""
echo "Next Steps:"
echo "1. Review results in: $RESULTS_DIR/"
echo "2. View in Web UI: (check CloudFormation outputs for ApplicationWebURL)"
echo "3. Clean up when done:"
echo "   aws cloudformation delete-stack --stack-name $STACK_NAME"
echo ""
echo "Example: View extraction results for first document:"
echo "  cat $RESULTS_DIR/W2_XL_input_clean_1000/extraction_result.json | jq ."
echo ""
