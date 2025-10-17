// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

/* eslint-disable react/prop-types */
import React, { useState } from 'react';
import { Box } from '@cloudscape-design/components';
import { generateClient } from 'aws-amplify/api';
import { ConsoleLogger } from 'aws-amplify/utils';
import DOMPurify from 'dompurify';
// Note: XLSX and mammoth imports removed since we're using download approach for Excel/Docx files
import useSettingsContext from '../../contexts/settings';
import generateS3PresignedUrl from '../common/generate-s3-presigned-url';
import useAppContext from '../../contexts/app';
import getFileContents from '../../graphql/queries/getFileContents';

const client = generateClient();
const logger = new ConsoleLogger('FileViewer');

// Helper function to create a safe data URL for HTML content
const createSafeDataUrl = (content, contentType) => {
  // For HTML content, sanitize with DOMPurify
  if (contentType.includes('html')) {
    const sanitizedContent = DOMPurify.sanitize(content, {
      FORBID_TAGS: ['script', 'iframe', 'object', 'embed'],
      FORBID_ATTR: ['onerror', 'onload', 'onclick', 'onmouseover', 'onmouseout'],
    });

    return `data:${contentType};charset=utf-8,${encodeURIComponent(sanitizedContent)}`;
  }

  // For CSV files, treat as plain text for better browser compatibility
  if (contentType.includes('csv')) {
    return `data:text/plain;charset=utf-8,${encodeURIComponent(content)}`;
  }

  // For other text-based content, use as is
  return `data:${contentType};charset=utf-8,${encodeURIComponent(content)}`;
};

// Helper function to detect file type from object key or content type
const detectFileType = (objectKey, contentType) => {
  // First check content type if available
  if (contentType) {
    if (contentType.includes('pdf')) return 'pdf';
    if (contentType.includes('image/')) return 'image';
    if (contentType.includes('html')) return 'html';
    if (contentType.includes('text/')) return 'text';
    if (contentType.includes('json')) return 'json';
    if (contentType.includes('spreadsheet') || contentType.includes('excel')) return 'excel';
    if (contentType.includes('wordprocessingml') || contentType.includes('msword')) return 'docx';
  }
  // Fallback to checking file extension
  if (objectKey) {
    const extension = objectKey.split('.').pop().toLowerCase();
    if (extension === 'pdf') return 'pdf';
    if (['jpg', 'jpeg', 'png', 'gif', 'svg', 'webp'].includes(extension)) return 'image';
    if (extension === 'html' || extension === 'htm') return 'html';
    if (['txt', 'md', 'csv', 'log'].includes(extension)) return 'text';
    if (extension === 'json') return 'json';
    if (['xlsx', 'xls', 'xlsm', 'xlsb'].includes(extension)) return 'excel';
    if (['docx', 'doc'].includes(extension)) return 'docx';
  }
  return 'unknown';
};

const FileViewer = ({ objectKey }) => {
  const [presignedUrl, setPresignedUrl] = useState(null);
  const [fileContent, setFileContent] = useState(null);
  const [contentType, setContentType] = useState(null);
  const { settings } = useSettingsContext();
  const { currentCredentials } = useAppContext();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [viewMethod, setViewMethod] = useState('presigned'); // 'presigned' or 'content'
  const [imageError, setImageError] = useState(false);
  const [imageErrorUrl, setImageErrorUrl] = useState('');

  // Fetch file contents via GraphQL API and process special file types
  const fetchFileContents = async (s3Url) => {
    try {
      logger.info('Fetching file contents via GraphQL for:', s3Url);
      const response = await client.graphql({
        query: getFileContents,
        variables: { s3Uri: s3Url },
      });

      const result = response.data.getFileContents;
      logger.info('Content type received:', result.contentType);
      logger.info('Binary content?', result.isBinary);
      logger.info('Content length:', result.content ? result.content.length : 'null');
      logger.info('Content type:', typeof result.content);
      logger.info('Content preview:', result.content ? result.content.substring(0, 100) : 'null');

      // Get file type
      const fileType = detectFileType(objectKey, result.contentType);
      logger.info('Detected file type:', fileType);

      // For Excel and Docx files, we always use presigned URL with download approach
      if (fileType === 'excel' || fileType === 'docx') {
        logger.info(`${fileType} file detected, using presigned URL with download approach`);
      }

      // Set content and type for other files
      setFileContent(result.content);
      setContentType(result.contentType);

      // Determine view method based on content type and binary flag
      let selectedViewMethod;
      if (
        fileType === 'pdf' ||
        fileType === 'excel' ||
        fileType === 'docx' ||
        (result.isBinary === true && fileType !== 'html' && fileType !== 'text')
      ) {
        // Use presigned URL for PDFs, Excel, Docx, and other binary content
        selectedViewMethod = 'presigned';
      } else if (fileType === 'html' || fileType === 'text' || result.isBinary === false) {
        // Use content-based viewing for HTML, text content, and non-binary files (like CSV)
        selectedViewMethod = 'content';
      } else {
        // Use presigned URL for other content
        selectedViewMethod = 'presigned';
      }

      logger.info('Selected view method:', selectedViewMethod);
      setViewMethod(selectedViewMethod);

      return result;
    } catch (err) {
      logger.error('Error fetching file contents:', err);
      throw err;
    }
  };

  // Generate presigned URL for direct viewing
  const generateUrl = async () => {
    setIsLoading(true);
    setError(null);
    try {
      if (!settings.InputBucket) {
        throw new Error('Input bucket not configured');
      }

      const region = import.meta.env.VITE_AWS_REGION;
      const s3Url = `https://${settings.InputBucket}.s3.${region}.amazonaws.com/${objectKey}`;

      // First fetch the content via GraphQL to determine content type
      const result = await fetchFileContents(s3Url);

      // Get file type to determine if we need presigned URL
      const fileType = detectFileType(objectKey, result.contentType);

      // Determine if we need presigned URL based on the same logic as in fetchFileContents
      const needsPresignedUrl =
        fileType === 'pdf' ||
        fileType === 'excel' ||
        fileType === 'docx' ||
        (result.isBinary === true && fileType !== 'html' && fileType !== 'text');

      // Generate presigned URL only if needed
      if (needsPresignedUrl) {
        logger.info('Generating presigned URL for:', s3Url);
        const url = await generateS3PresignedUrl(s3Url, currentCredentials);
        setPresignedUrl(url);
      } else {
        logger.info('Using content-based viewing, no presigned URL needed');
      }
    } catch (err) {
      logger.error('Error preparing document for viewing:', err);
      setError('Failed to load document. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  // Reset image error state when presigned URL changes
  React.useEffect(() => {
    if (presignedUrl) {
      setImageError(false);
      setImageErrorUrl('');
    }
  }, [presignedUrl]);

  React.useEffect(() => {
    generateUrl();
  }, [objectKey]);

  if (error) {
    return (
      <Box color="text-status-error" padding="s">
        {error}
      </Box>
    );
  }

  // Render loading state
  if (isLoading) {
    return (
      <Box textAlign="center" padding="s">
        Loading document...
      </Box>
    );
  }

  // Render content-based viewer (for HTML and text files)
  if (viewMethod === 'content' && fileContent && contentType) {
    logger.info('Rendering content-based viewer');
    logger.info('File content length:', fileContent.length);
    logger.info('Content type for data URL:', contentType);

    const safeDataUrl = createSafeDataUrl(fileContent, contentType);
    logger.info('Generated data URL length:', safeDataUrl.length);
    logger.info('Data URL preview:', safeDataUrl.substring(0, 200));

    return (
      <Box className="document-container" padding={{ top: 's' }}>
        <iframe
          src={safeDataUrl}
          title="Document Viewer"
          width="100%"
          height="800px"
          className="h-full w-full"
          sandbox="allow-same-origin allow-popups allow-forms"
          referrerPolicy="no-referrer"
        />
      </Box>
    );
  }

  // Render presigned URL viewer (for PDFs, images, etc.)
  if (viewMethod === 'presigned' && presignedUrl) {
    // Get the file type
    const fileType = detectFileType(objectKey, contentType);
    const isPdf = fileType === 'pdf';
    logger.info('Rendering presigned URL viewer for file type:', fileType);
    logger.info('Presigned URL:', presignedUrl);

    if (isPdf) {
      // Special handling for PDFs - use object tag instead of iframe for better PDF support
      return (
        <Box className="document-container" padding={{ top: 's' }}>
          <object data={presignedUrl} type="application/pdf" width="100%" height="800px" className="h-full w-full">
            <p>
              It appears your browser does not support embedded PDFs. You can{' '}
              <a href={presignedUrl} target="_blank" rel="noopener noreferrer">
                download the PDF
              </a>{' '}
              instead.
            </p>
          </object>
        </Box>
      );
    }
    // For image files, display them inline using img tag
    if (fileType === 'image') {
      const handleImageError = () => {
        setImageError(true);
        setImageErrorUrl(presignedUrl);
      };

      return (
        <Box className="document-container" padding={{ top: 's' }}>
          <Box textAlign="center">
            {!imageError ? (
              <img
                src={presignedUrl}
                alt="Document preview"
                style={{
                  maxWidth: '100%',
                  maxHeight: '800px',
                  height: 'auto',
                  objectFit: 'contain',
                }}
                onError={handleImageError}
              />
            ) : (
              <Box padding="xl">
                <h3>🖼️ Image Document</h3>
                <p>Unable to display this image.</p>
                <p>
                  <a
                    href={imageErrorUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      display: 'inline-block',
                      padding: '12px 24px',
                      backgroundColor: '#0073bb',
                      color: 'white',
                      textDecoration: 'none',
                      borderRadius: '4px',
                      fontWeight: 'bold',
                      margin: '10px',
                    }}
                  >
                    📥 Download Image
                  </a>
                </p>
              </Box>
            )}
          </Box>
        </Box>
      );
    }

    // For Excel and Docx files, provide download link since browsers can't display them inline
    if (fileType === 'excel' || fileType === 'docx') {
      const fileTypeName = fileType === 'excel' ? 'Excel' : 'Word';
      return (
        <Box className="document-container" padding={{ top: 's' }} textAlign="center">
          <Box padding="xl">
            <h3>📄 {fileTypeName} Document</h3>
            <p>This {fileTypeName} document cannot be displayed directly in the browser.</p>
            <p>
              <a
                href={presignedUrl}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  display: 'inline-block',
                  padding: '12px 24px',
                  backgroundColor: '#0073bb',
                  color: 'white',
                  textDecoration: 'none',
                  borderRadius: '4px',
                  fontWeight: 'bold',
                  margin: '10px',
                }}
              >
                📥 Download {fileTypeName} File
              </a>
            </p>
            <p style={{ fontSize: '14px', color: '#666' }}>
              The file will open in your default {fileTypeName} application.
            </p>
          </Box>
        </Box>
      );
    }

    // For other non-PDF content, use iframe with appropriate sandbox settings
    return (
      <Box className="document-container" padding={{ top: 's' }}>
        <iframe
          src={presignedUrl}
          title="Document Viewer"
          width="100%"
          height="800px"
          className="h-full w-full"
          sandbox="allow-same-origin allow-popups allow-forms"
          referrerPolicy="no-referrer"
        />
      </Box>
    );
  }

  // Default fallback
  return (
    <Box textAlign="center" padding="s">
      Unable to display document.
    </Box>
  );
};

export default FileViewer;
