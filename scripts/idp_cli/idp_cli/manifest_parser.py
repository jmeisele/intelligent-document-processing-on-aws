# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Manifest Parser Module

Parses CSV and JSON manifest files containing document batch information.
"""

import csv
import json
import os
from typing import List, Dict, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class ManifestParser:
    """Parses manifest files in CSV or JSON format"""
    
    def __init__(self, manifest_path: str):
        """
        Initialize manifest parser
        
        Args:
            manifest_path: Path to manifest file (CSV or JSON)
        """
        self.manifest_path = manifest_path
        self.format = self._detect_format()
    
    def _detect_format(self) -> str:
        """Detect manifest format from file extension"""
        ext = Path(self.manifest_path).suffix.lower()
        
        if ext in ['.csv', '.txt']:
            return 'csv'
        elif ext in ['.json', '.jsonl']:
            return 'json'
        else:
            raise ValueError(f"Unsupported manifest format: {ext}. Use .csv or .json")
    
    def parse(self) -> List[Dict]:
        """
        Parse manifest file and return list of document specifications
        
        Returns:
            List of document dictionaries with keys:
                - document_id: Unique identifier
                - path: Local file path or S3 key
                - type: 'local' or 's3-key'
                - expected_class: Optional expected document class
                - baseline_key: Optional baseline key in EvaluationBaselineBucket
        """
        logger.info(f"Parsing {self.format.upper()} manifest: {self.manifest_path}")
        
        if self.format == 'csv':
            return self._parse_csv()
        elif self.format == 'json':
            return self._parse_json()
        else:
            raise ValueError(f"Unsupported format: {self.format}")
    
    def _parse_csv(self) -> List[Dict]:
        """Parse CSV manifest"""
        documents = []
        
        with open(self.manifest_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row_num, row in enumerate(reader, start=2):  # Start at 2 (after header)
                try:
                    doc = self._validate_and_normalize_row(row, row_num)
                    documents.append(doc)
                except ValueError as e:
                    logger.error(f"Row {row_num}: {e}")
                    raise
        
        logger.info(f"Parsed {len(documents)} documents from CSV")
        return documents
    
    def _parse_json(self) -> List[Dict]:
        """Parse JSON manifest"""
        with open(self.manifest_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Handle both array format and object with 'documents' key
        if isinstance(data, list):
            documents_list = data
        elif isinstance(data, dict) and 'documents' in data:
            documents_list = data['documents']
        else:
            raise ValueError("JSON manifest must be an array or object with 'documents' key")
        
        documents = []
        for idx, doc in enumerate(documents_list, start=1):
            try:
                validated_doc = self._validate_and_normalize_row(doc, idx)
                documents.append(validated_doc)
            except ValueError as e:
                logger.error(f"Document {idx}: {e}")
                raise
        
        logger.info(f"Parsed {len(documents)} documents from JSON")
        return documents
    
    def _validate_and_normalize_row(self, row: Dict, row_num: int) -> Dict:
        """
        Validate and normalize a manifest row
        
        Args:
            row: Raw row data
            row_num: Row number for error messages
        
        Returns:
            Normalized document dictionary
        """
        # Required fields
        document_path = row.get('document_path') or row.get('path', '').strip()
        document_id = row.get('document_id') or row.get('id', '').strip()
        doc_type = row.get('type', '').strip().lower()
        
        if not document_path:
            raise ValueError(f"Missing required field 'document_path' or 'path'")
        
        # Auto-generate document_id if not provided
        if not document_id:
            # Use filename without extension as ID
            document_id = Path(document_path).stem
            logger.debug(f"Auto-generated document_id: {document_id}")
        
        # Determine type if not specified
        if not doc_type:
            if document_path.startswith('s3://'):
                raise ValueError("S3 URIs not supported. Use 's3-key' type with key only")
            elif os.path.isabs(document_path) or os.path.exists(document_path):
                doc_type = 'local'
            else:
                doc_type = 's3-key'
        
        # Validate type
        if doc_type not in ['local', 's3-key']:
            raise ValueError(f"Invalid type '{doc_type}'. Must be 'local' or 's3-key'")
        
        # Validate local file exists
        if doc_type == 'local' and not os.path.exists(document_path):
            raise ValueError(f"Local file not found: {document_path}")
        
        # Optional fields
        expected_class = row.get('expected_class', '').strip()
        baseline_key = row.get('baseline_key') or row.get('baseline_path', '').strip()
        
        # Remove 's3://' prefix from baseline if present (should be key only)
        if baseline_key and baseline_key.startswith('s3://'):
            # Extract just the key part
            parts = baseline_key.replace('s3://', '').split('/', 1)
            if len(parts) > 1:
                baseline_key = parts[1]
                logger.debug(f"Converted baseline S3 URI to key: {baseline_key}")
            else:
                baseline_key = ''
        
        return {
            'document_id': document_id,
            'path': document_path,
            'type': doc_type,
            'expected_class': expected_class,
            'baseline_key': baseline_key
        }


def parse_manifest(manifest_path: str) -> List[Dict]:
    """
    Convenience function to parse a manifest file
    
    Args:
        manifest_path: Path to manifest file
    
    Returns:
        List of document dictionaries
    """
    parser = ManifestParser(manifest_path)
    return parser.parse()


def validate_manifest(manifest_path: str) -> tuple[bool, Optional[str]]:
    """
    Validate a manifest file without fully parsing it
    
    Args:
        manifest_path: Path to manifest file
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        parser = ManifestParser(manifest_path)
        documents = parser.parse()
        
        if not documents:
            return False, "Manifest contains no documents"
        
        # Check for duplicate IDs
        ids = [doc['document_id'] for doc in documents]
        if len(ids) != len(set(ids)):
            duplicates = [id for id in ids if ids.count(id) > 1]
            return False, f"Duplicate document IDs found: {', '.join(set(duplicates))}"
        
        return True, None
        
    except Exception as e:
        return False, str(e)
