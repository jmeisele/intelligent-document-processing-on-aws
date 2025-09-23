# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Schema provider for analytics agents - generates comprehensive database descriptions.
"""

import logging
from typing import Any, Dict, Optional

from idp_common.config import get_config

logger = logging.getLogger(__name__)


def get_metering_table_description() -> str:
    """
    Get comprehensive description of the metering table.

    Returns:
        Detailed description of metering table schema and usage patterns
    """
    return """
## Metering Table (metering)

**Purpose**: Captures detailed usage metrics and cost information for document processing operations

**Key Usage**: Always use this table for questions about:
- Volume of documents processed
- Models used and their consumption patterns  
- Units of consumption (tokens, pages) for each processing step
- Costs and spending analysis
- Processing patterns and trends

**Important**: Each document has multiple rows in this table - one for each context/service/unit combination.

### Schema:
- `document_id` (string): Unique identifier for the document
- `context` (string): Processing context (OCR, Classification, Extraction, Assessment, Summarization, Evaluation)
- `service_api` (string): Specific API or model used (e.g., textract/analyze_document, bedrock/claude-3-sonnet)
- `unit` (string): Unit of measurement (pages, inputTokens, outputTokens, totalTokens)
- `value` (double): Quantity of the unit consumed
- `number_of_pages` (int): Number of pages in the document (replicated across all rows for same document)
- `unit_cost` (double): Cost per unit in USD
- `estimated_cost` (double): Calculated total cost (value × unit_cost)
- `timestamp` (timestamp): When the operation was performed

**Partitioned by**: date (YYYY-MM-DD format)

### Critical Aggregation Patterns:
- **For document page counts**: Use `MAX("number_of_pages")` per document (NOT SUM, as this value is replicated)
- **For total pages across documents**: Use `SUM` of per-document MAX values:
  ```sql
  SELECT SUM(max_pages) FROM (
    SELECT "document_id", MAX("number_of_pages") as max_pages 
    FROM metering 
    GROUP BY "document_id"
  )
  ```
- **For costs**: Use `SUM("estimated_cost")` for totals, `GROUP BY "context"` for breakdowns
- **For token usage**: Use `SUM("value")` when `"unit"` IN ('inputTokens', 'outputTokens', 'totalTokens')

### Sample Queries:
```sql
-- Total documents processed
SELECT COUNT(DISTINCT "document_id") FROM metering

-- Total pages processed (correct aggregation)
SELECT SUM(max_pages) FROM (
  SELECT "document_id", MAX("number_of_pages") as max_pages 
  FROM metering 
  GROUP BY "document_id"
)

-- Cost breakdown by processing context
SELECT "context", SUM("estimated_cost") as total_cost
FROM metering 
GROUP BY "context"
ORDER BY total_cost DESC

-- Token usage by model
SELECT "service_api", 
       SUM(CASE WHEN "unit" = 'inputTokens' THEN "value" ELSE 0 END) as input_tokens,
       SUM(CASE WHEN "unit" = 'outputTokens' THEN "value" ELSE 0 END) as output_tokens
FROM metering 
WHERE "unit" IN ('inputTokens', 'outputTokens')
GROUP BY "service_api"
```
"""


def get_evaluation_tables_description() -> str:
    """
    Get comprehensive description of the evaluation tables.

    Returns:
        Detailed description of evaluation table schemas and relationships
    """
    return """
## Evaluation Tables

**Purpose**: Store accuracy metrics from comparing extracted document data against ground truth baselines

**Key Usage**: Always use these tables for questions about accuracy for documents that have ground truth data

**Important**: These tables are typically empty unless users have run separate evaluation jobs (not run by default)

### Document Evaluations Table (document_evaluations)

**Purpose**: Document-level evaluation metrics and overall accuracy scores

#### Schema:
- `document_id` (string): Unique identifier for the document
- `input_key` (string): S3 key of the input document  
- `evaluation_date` (timestamp): When the evaluation was performed
- `accuracy` (double): Overall accuracy score (0-1)
- `precision` (double): Precision score (0-1)
- `recall` (double): Recall score (0-1)
- `f1_score` (double): F1 score (0-1)
- `false_alarm_rate` (double): False alarm rate (0-1)
- `false_discovery_rate` (double): False discovery rate (0-1)
- `execution_time` (double): Time taken to evaluate (seconds)

**Partitioned by**: date (YYYY-MM-DD format)

### Section Evaluations Table (section_evaluations)

**Purpose**: Section-level evaluation metrics grouped by document type/classification

#### Schema:
- `document_id` (string): Unique identifier for the document
- `section_id` (string): Identifier for the section
- `section_type` (string): Type/class of the section (e.g., 'invoice', 'receipt', 'w2')
- `accuracy` (double): Section accuracy score (0-1)
- `precision` (double): Section precision score (0-1)
- `recall` (double): Section recall score (0-1)
- `f1_score` (double): Section F1 score (0-1)
- `false_alarm_rate` (double): Section false alarm rate (0-1)
- `false_discovery_rate` (double): Section false discovery rate (0-1)
- `evaluation_date` (timestamp): When the evaluation was performed

**Partitioned by**: date (YYYY-MM-DD format)

### Attribute Evaluations Table (attribute_evaluations)

**Purpose**: Detailed attribute-level comparison results showing expected vs actual extracted values

#### Schema:
- `document_id` (string): Unique identifier for the document
- `section_id` (string): Identifier for the section
- `section_type` (string): Type/class of the section
- `attribute_name` (string): Name of the extracted attribute
- `expected` (string): Expected (ground truth) value
- `actual` (string): Actual extracted value
- `matched` (boolean): Whether the values matched according to evaluation method
- `score` (double): Match score (0-1)
- `reason` (string): Explanation for the match result
- `evaluation_method` (string): Method used for comparison (EXACT, FUZZY, SEMANTIC, etc.)
- `confidence` (string): Confidence score from extraction process
- `confidence_threshold` (string): Confidence threshold used for evaluation
- `evaluation_date` (timestamp): When the evaluation was performed

**Partitioned by**: date (YYYY-MM-DD format)

### Relationships:
- Use `document_id` to join between all three tables
- Use `section_id` and `document_id` to join section and attribute evaluations
- Join with metering table on `document_id` for cost vs accuracy analysis

### Sample Queries:
```sql
-- Overall accuracy by document type
SELECT "section_type", 
       AVG("accuracy") as avg_accuracy,
       COUNT(*) as document_count
FROM section_evaluations
GROUP BY "section_type"
ORDER BY avg_accuracy DESC

-- Confidence vs accuracy correlation
SELECT 
  CASE 
    WHEN CAST("confidence" AS double) < 0.7 THEN 'Low (<0.7)'
    WHEN CAST("confidence" AS double) < 0.9 THEN 'Medium (0.7-0.9)'
    ELSE 'High (>0.9)'
  END as confidence_band,
  AVG(CASE WHEN "matched" THEN 1.0 ELSE 0.0 END) as accuracy_rate,
  COUNT(*) as attribute_count
FROM attribute_evaluations
WHERE "confidence" IS NOT NULL
GROUP BY confidence_band

-- Cost per accuracy point by document type  
SELECT se."section_type",
       AVG(se."accuracy") as avg_accuracy,
       SUM(m."estimated_cost") / COUNT(DISTINCT m."document_id") as avg_cost_per_doc
FROM section_evaluations se
JOIN metering m ON se."document_id" = m."document_id"  
GROUP BY se."section_type"
```
"""


def get_dynamic_document_sections_description(
    config: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generate deployment-specific description of document sections tables based on actual configuration.

    Args:
        config: Optional configuration dictionary. If None, loads from environment.

    Returns:
        Deployment-specific description with exact table names and column schemas
    """
    try:
        if config is None:
            config = get_config()

        # Get document classes from config
        classes = config.get("classes", [])

        if not classes:
            logger.warning("No classes found in configuration")
            return _get_fallback_description()

        description = """
## Document Sections Tables (Configuration-Based)

**Purpose**: Store actual extracted data from document sections in structured format for analytics

**Key Usage**: Use these tables to query the actual extracted content and attributes from processed documents

**IMPORTANT**: Based on your current configuration, the following tables DEFINITELY exist. Do NOT use discovery queries (SHOW TABLES, DESCRIBE) for these - use them directly.

"""

        # Generate table list
        table_names = []
        for doc_class in classes:
            class_name = doc_class.get("name", "Unknown")
            # Apply exact table name transformation logic
            table_name = f"document_sections_{_get_table_suffix(class_name)}"
            table_names.append(table_name)

        description += "### Known Document Sections Tables:\n\n"
        for table_name in table_names:
            description += f"- `{table_name}`\n"

        description += "\n### Complete Table Schemas:\n\n"
        description += "Each table has the following structure:\n\n"

        # Generate detailed schema for each table
        for doc_class in classes:
            class_name = doc_class.get("name", "Unknown")
            class_desc = doc_class.get("description", "No description available")
            table_name = f"document_sections_{_get_table_suffix(class_name)}"
            attributes = doc_class.get("attributes", [])

            description += f'**`{table_name}`** (Class: "{class_name}"):\n'
            description += f"- **Description**: {class_desc}\n"

            # Standard columns always present
            description += "- **Standard Columns**:\n"
            description += (
                "  - `document_class.type` (string): Document classification type\n"
            )
            description += (
                "  - `document_id` (string): Unique identifier for the document\n"
            )
            description += (
                "  - `section_id` (string): Unique identifier for the section\n"
            )
            description += (
                "  - `section_classification` (string): Type/class of the section\n"
            )
            description += "  - `section_confidence` (string): Confidence score for the section classification\n"
            description += "  - `explainability_info` (string): JSON containing explanation of extraction decisions\n"
            description += (
                "  - `timestamp` (timestamp): When the document was processed\n"
            )
            description += "  - `date` (string): Partition key in YYYY-MM-DD format\n"
            description += (
                "  - Various `metadata.*` columns (strings): Processing metadata\n"
            )

            # Configuration-specific columns
            if attributes:
                description += "- **Configuration-Specific Columns**:\n"
                column_count = 0
                for attr in attributes:
                    attr_desc_text, columns_added = _generate_attribute_columns(
                        attr, "  "
                    )
                    description += attr_desc_text
                    column_count += columns_added
                    if column_count > 50:  # Limit output length
                        description += f"  - ... and {len(attributes) - attributes.index(attr)} more attributes from configuration\n"
                        break
            else:
                description += "- **Configuration-Specific Columns**: None configured\n"

            description += "\n"

        description += """### Column Naming Patterns:
- **Simple attributes**: `inference_result.{attribute_name_lowercase}` (all strings)
- **Group attributes**: `inference_result.{group_name_lowercase}.{sub_attribute_lowercase}` (all strings)
- **List attributes**: `inference_result.{list_name_lowercase}` (JSON string containing array data)

### Important Querying Notes:
- **All `inference_result.*` columns are string type** - even numeric data is stored as strings
- **Always use double quotes** around column names: `"inference_result.companyaddress.state"`
- **List data is stored as JSON strings** - use JSON parsing functions to extract array elements
- **Case sensitivity**: Column names are lowercase, use LOWER() for string comparisons
- **Partitioning**: All tables partitioned by `date` in YYYY-MM-DD format

### Sample Queries:
```sql
-- Query specific attributes (example for Payslip)
SELECT "document_id", 
       "inference_result.ytdnetpay",
       "inference_result.employeename.firstname",
       "inference_result.companyaddress.state"
FROM document_sections_payslip
WHERE date >= '2024-01-01'

-- Parse JSON list data (example for FederalTaxes)
SELECT "document_id",
       json_extract_scalar(tax_item, '$.ItemDescription') as tax_type,
       json_extract_scalar(tax_item, '$.YTD') as ytd_amount
FROM document_sections_payslip
CROSS JOIN UNNEST(json_parse("inference_result.federaltaxes")) as t(tax_item)

-- Join with metering for cost analysis
SELECT ds."section_classification",
       COUNT(DISTINCT ds."document_id") as document_count,
       AVG(CAST(m."estimated_cost" AS double)) as avg_processing_cost
FROM document_sections_w2 ds
JOIN metering m ON ds."document_id" = m."document_id"
GROUP BY ds."section_classification"
```

**This schema information is generated from your actual configuration and shows exactly what tables and columns exist in your deployment.**
"""

        return description

    except Exception as e:
        logger.error(f"Error generating dynamic sections description: {e}")
        return _get_fallback_description()


def _get_table_suffix(class_name: str) -> str:
    """
    Convert class name to table suffix using exact transformation rules.

    Args:
        class_name: The class name from configuration

    Returns:
        Table suffix for use in document_sections_{suffix}
    """
    return class_name.lower().replace("-", "_").replace(" ", "_")


def _generate_attribute_columns(attr: Dict[str, Any], indent: str) -> tuple[str, int]:
    """
    Generate column descriptions for an attribute.

    Args:
        attr: Attribute configuration dictionary
        indent: Indentation string for formatting

    Returns:
        Tuple of (description_text, columns_added_count)
    """
    attr_name = attr.get("name", "unknown")
    attr_desc = attr.get("description", "")
    attr_type = attr.get("attributeType", "simple")

    desc_parts = []
    columns_added = 0

    if attr_type == "simple":
        column_name = f"inference_result.{attr_name.lower()}"
        desc_parts.append(f'{indent}- `"{column_name}"` (string): {attr_desc}')
        columns_added = 1

    elif attr_type == "group":
        group_attrs = attr.get("groupAttributes", [])
        group_name_lower = attr_name.lower()
        desc_parts.append(
            f"{indent}- **{attr_name} Group** ({len(group_attrs)} columns):"
        )

        for group_attr in group_attrs:
            sub_name = group_attr.get("name", "unknown")
            sub_desc = group_attr.get("description", "")
            column_name = f"inference_result.{group_name_lower}.{sub_name.lower()}"
            desc_parts.append(f'{indent}  - `"{column_name}"` (string): {sub_desc}')
            columns_added += 1

    elif attr_type == "list":
        column_name = f"inference_result.{attr_name.lower()}"
        list_template = attr.get("listItemTemplate", {})
        item_attrs = list_template.get("itemAttributes", [])
        item_names = [ia.get("name", "") for ia in item_attrs]
        desc_parts.append(f'{indent}- `"{column_name}"` (string): {attr_desc}')
        desc_parts.append(
            f"{indent}  - JSON array containing items with: {', '.join(item_names)}"
        )
        columns_added = 1

    return "\n".join(desc_parts) + "\n", columns_added


def _get_fallback_description() -> str:
    """
    Get fallback description when configuration loading fails.

    Returns:
        Basic description without discovery queries
    """
    return """
## Document Sections Tables (Dynamic)

**Purpose**: Store actual extracted data from document sections in structured format for analytics

**Key Usage**: Use these tables to query the actual extracted content and attributes from processed documents

**IMPORTANT**: Configuration loading failed, but common document section tables include:
- `document_sections_w2` - W2 tax form processing
- `document_sections_payslip` - Payslip processing
- `document_sections_bank_statement` - Bank statement processing
- `document_sections_bank_checks` - Bank check processing

### Common Schema for All Document Sections Tables:

**Standard Metadata Columns** (all tables):
- `document_class.type` (string): Document classification type
- `document_id` (string): Unique identifier for the document
- `section_id` (string): Unique identifier for the section
- `section_classification` (string): Type/class of the section
- `section_confidence` (string): Confidence score for the section classification
- `explainability_info` (string): JSON containing explanation of extraction decisions
- `timestamp` (timestamp): When the document was processed
- `date` (string): Partition key in YYYY-MM-DD format

**Dynamic Inference Columns**: `inference_result.*` columns based on extracted data (all strings)

**Important**: Always use double quotes around column names containing periods in Athena queries.

### Sample Queries:
```sql
-- Basic query pattern
SELECT "document_id", "section_classification", "timestamp"
FROM document_sections_w2
WHERE date >= '2024-01-01'

-- Join with metering for cost analysis  
SELECT ds."section_classification",
       COUNT(DISTINCT ds."document_id") as document_count,
       AVG(CAST(m."estimated_cost" AS double)) as avg_processing_cost
FROM document_sections_w2 ds
JOIN metering m ON ds."document_id" = m."document_id"
GROUP BY ds."section_classification"
```

**Note**: Table schemas include dynamically generated `inference_result.*` columns based on extraction results.
"""


def generate_comprehensive_database_description(
    config: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generate a comprehensive database description including all table types.

    Args:
        config: Optional configuration dictionary for dynamic sections

    Returns:
        Complete database description with all tables and schemas
    """
    description = """# Comprehensive Athena Database Schema

## Overview

This database contains three main categories of tables for document processing analytics:

1. **Metering Table**: Usage metrics, costs, and consumption data
2. **Evaluation Tables**: Accuracy assessment data (typically empty unless evaluation jobs are run)  
3. **Document Sections Tables**: Extracted content from processed documents (dynamically created)

## Important Notes

- **Column Names**: Always enclose column names in double quotes in Athena queries
- **Partitioning**: All tables are partitioned by date (YYYY-MM-DD format) for efficient querying
- **Timestamps**: All date/timestamp columns refer to processing time, not document content dates
- **Case Sensitivity**: Use LOWER() functions when comparing string values as case may vary

---
"""

    # Add each table category description
    description += get_metering_table_description()
    description += "\n---\n"
    description += get_evaluation_tables_description()
    description += "\n---\n"
    description += get_dynamic_document_sections_description(config)

    description += """
---

## General Query Tips

### Table Discovery:
```sql
-- List all tables
SHOW TABLES

-- Get document sections tables (filter manually from SHOW TABLES output)
-- Alternative: Query information schema for document sections tables
SELECT table_name 
FROM information_schema.tables 
WHERE table_name LIKE 'document_sections_%'

-- Get table schema
DESCRIBE table_name
```

### Performance Optimization:
- Use date partitioning in WHERE clauses when possible: `WHERE date >= '2024-01-01'`
- Use LIMIT for exploratory queries to avoid large result sets
- Consider using approximate functions like `approx_distinct()` for large datasets

### Common Joins:
```sql
-- Join metering with evaluations for cost vs accuracy analysis
SELECT m."document_id", m."estimated_cost", e."accuracy"
FROM metering m
JOIN document_evaluations e ON m."document_id" = e."document_id"

-- Join document sections with metering for content analysis with costs
SELECT ds.*, m."estimated_cost"
FROM document_sections_invoice ds  
JOIN metering m ON ds."document_id" = m."document_id"
```
"""

    return description
