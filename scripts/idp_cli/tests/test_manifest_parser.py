# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Tests for manifest parser module
"""

import pytest
import tempfile
import os
from pathlib import Path
import json
import csv

from idp_cli.manifest_parser import ManifestParser, parse_manifest, validate_manifest


class TestManifestParser:
    """Test manifest parsing functionality"""
    
    def test_csv_parsing_basic(self, tmp_path):
        """Test basic CSV manifest parsing"""
        manifest_file = tmp_path / "test.csv"
        
        with open(manifest_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['document_path', 'document_id', 'type'])
            writer.writerow(['doc1.pdf', 'doc1', 's3-key'])
            writer.writerow(['doc2.pdf', 'doc2', 's3-key'])
        
        parser = ManifestParser(str(manifest_file))
        documents = parser.parse()
        
        assert len(documents) == 2
        assert documents[0]['document_id'] == 'doc1'
        assert documents[0]['path'] == 'doc1.pdf'
        assert documents[0]['type'] == 's3-key'
    
    def test_csv_auto_generate_id(self, tmp_path):
        """Test auto-generation of document ID from filename"""
        manifest_file = tmp_path / "test.csv"
        
        with open(manifest_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['document_path', 'type'])
            writer.writerow(['folder/document-name.pdf', 's3-key'])
        
        parser = ManifestParser(str(manifest_file))
        documents = parser.parse()
        
        assert documents[0]['document_id'] == 'document-name'
    
    def test_csv_auto_detect_type(self, tmp_path):
        """Test auto-detection of document type"""
        manifest_file = tmp_path / "test.csv"
        
        # Create a local file
        local_file = tmp_path / "local-doc.pdf"
        local_file.write_text("test content")
        
        with open(manifest_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['document_path'])
            writer.writerow([str(local_file)])  # Absolute path should be detected as local
            writer.writerow(['s3-key-path.pdf'])  # Relative path should be s3-key
        
        parser = ManifestParser(str(manifest_file))
        documents = parser.parse()
        
        assert documents[0]['type'] == 'local'
        assert documents[1]['type'] == 's3-key'
    
    def test_json_parsing_array_format(self, tmp_path):
        """Test JSON parsing with array format"""
        manifest_file = tmp_path / "test.json"
        
        data = [
            {
                "document_id": "doc1",
                "path": "doc1.pdf",
                "type": "s3-key"
            },
            {
                "document_id": "doc2",
                "path": "doc2.pdf",
                "type": "s3-key"
            }
        ]
        
        with open(manifest_file, 'w') as f:
            json.dump(data, f)
        
        parser = ManifestParser(str(manifest_file))
        documents = parser.parse()
        
        assert len(documents) == 2
        assert documents[0]['document_id'] == 'doc1'
        assert documents[1]['document_id'] == 'doc2'
    
    def test_json_parsing_object_format(self, tmp_path):
        """Test JSON parsing with object format"""
        manifest_file = tmp_path / "test.json"
        
        data = {
            "documents": [
                {
                    "id": "doc1",
                    "path": "doc1.pdf",
                    "type": "s3-key"
                }
            ],
            "config": {
                "pattern": "pattern-2"
            }
        }
        
        with open(manifest_file, 'w') as f:
            json.dump(data, f)
        
        parser = ManifestParser(str(manifest_file))
        documents = parser.parse()
        
        assert len(documents) == 1
        assert documents[0]['document_id'] == 'doc1'
    
    
    def test_missing_document_path(self, tmp_path):
        """Test error handling for missing document path"""
        manifest_file = tmp_path / "test.csv"
        
        with open(manifest_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['document_id', 'type'])
            writer.writerow(['doc1', 's3-key'])
        
        parser = ManifestParser(str(manifest_file))
        
        with pytest.raises(ValueError, match="Missing required field"):
            parser.parse()
    
    def test_invalid_type(self, tmp_path):
        """Test error handling for invalid document type"""
        manifest_file = tmp_path / "test.csv"
        
        with open(manifest_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['document_path', 'document_id', 'type'])
            writer.writerow(['doc1.pdf', 'doc1', 'invalid-type'])
        
        parser = ManifestParser(str(manifest_file))
        
        with pytest.raises(ValueError, match="Invalid type"):
            parser.parse()
    
    def test_local_file_not_found(self, tmp_path):
        """Test error handling for missing local file"""
        manifest_file = tmp_path / "test.csv"
        
        with open(manifest_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['document_path', 'document_id', 'type'])
            writer.writerow(['/nonexistent/file.pdf', 'doc1', 'local'])
        
        parser = ManifestParser(str(manifest_file))
        
        with pytest.raises(ValueError, match="Local file not found"):
            parser.parse()
    
    def test_s3_uri_rejection(self, tmp_path):
        """Test that S3 URIs are rejected"""
        manifest_file = tmp_path / "test.csv"
        
        with open(manifest_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['document_path', 'document_id'])
            writer.writerow(['s3://bucket/key.pdf', 'doc1'])
        
        parser = ManifestParser(str(manifest_file))
        
        with pytest.raises(ValueError, match="S3 URIs not supported"):
            parser.parse()
    
    def test_validate_manifest_success(self, tmp_path):
        """Test manifest validation success"""
        manifest_file = tmp_path / "test.csv"
        
        with open(manifest_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['document_path', 'document_id', 'type'])
            writer.writerow(['doc1.pdf', 'doc1', 's3-key'])
        
        is_valid, error = validate_manifest(str(manifest_file))
        
        assert is_valid
        assert error is None
    
    def test_validate_manifest_duplicate_ids(self, tmp_path):
        """Test validation catches duplicate document IDs"""
        manifest_file = tmp_path / "test.csv"
        
        with open(manifest_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['document_path', 'document_id', 'type'])
            writer.writerow(['doc1.pdf', 'duplicate-id', 's3-key'])
            writer.writerow(['doc2.pdf', 'duplicate-id', 's3-key'])
        
        is_valid, error = validate_manifest(str(manifest_file))
        
        assert not is_valid
        assert 'Duplicate document IDs' in error
    
    def test_validate_manifest_empty(self, tmp_path):
        """Test validation catches empty manifests"""
        manifest_file = tmp_path / "test.csv"
        
        with open(manifest_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['document_path', 'document_id', 'type'])
            # No data rows
        
        is_valid, error = validate_manifest(str(manifest_file))
        
        assert not is_valid
        assert 'no documents' in error
    
    def test_unsupported_format(self, tmp_path):
        """Test error for unsupported file format"""
        manifest_file = tmp_path / "test.xml"
        manifest_file.write_text("<manifest></manifest>")
        
        with pytest.raises(ValueError, match="Unsupported manifest format"):
            ManifestParser(str(manifest_file))
    
    def test_parse_manifest_convenience_function(self, tmp_path):
        """Test convenience parse_manifest function"""
        manifest_file = tmp_path / "test.csv"
        
        with open(manifest_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['document_path', 'document_id', 'type'])
            writer.writerow(['doc1.pdf', 'doc1', 's3-key'])
        
        documents = parse_manifest(str(manifest_file))
        
        assert len(documents) == 1
        assert documents[0]['document_id'] == 'doc1'
