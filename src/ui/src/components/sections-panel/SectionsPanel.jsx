// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

/* eslint-disable react/prop-types */
import React, { useState, useEffect } from 'react';
import {
  Box,
  Container,
  SpaceBetween,
  Table,
  StatusIndicator,
  Button,
  Header,
  FormField,
  Select,
  Input,
  Textarea,
  Modal,
  Alert,
} from '@awsui/components-react';
import { API, graphqlOperation } from 'aws-amplify';
import FileViewer from '../document-viewer/JSONViewer';
import { getSectionConfidenceAlertCount, getSectionConfidenceAlerts } from '../common/confidence-alerts-utils';
import useConfiguration from '../../hooks/use-configuration';
import processChanges from '../../graphql/queries/processChanges';

// Cell renderer components
const IdCell = ({ item }) => <span>{item.Id}</span>;
const ClassCell = ({ item }) => <span>{item.Class}</span>;
const PageIdsCell = ({ item }) => <span>{item.PageIds.join(', ')}</span>;

// Confidence alerts cell showing only count
const ConfidenceAlertsCell = ({ item, mergedConfig }) => {
  if (!mergedConfig) {
    // Fallback to original behavior - just show the count as a number
    const count = getSectionConfidenceAlertCount(item);
    return count === 0 ? (
      <StatusIndicator type="success">0</StatusIndicator>
    ) : (
      <StatusIndicator type="warning">{count}</StatusIndicator>
    );
  }

  const alerts = getSectionConfidenceAlerts(item, mergedConfig);
  const alertCount = alerts.length;

  if (alertCount === 0) {
    return <StatusIndicator type="success">0</StatusIndicator>;
  }

  return <StatusIndicator type="warning">{alertCount}</StatusIndicator>;
};

const ActionsCell = ({ item, pages, documentItem, mergedConfig }) => (
  <FileViewer
    fileUri={item.OutputJSONUri}
    fileType="json"
    buttonText="View/Edit Data"
    sectionData={{ ...item, pages, documentItem, mergedConfig }}
  />
);

// Editable cell components for edit mode (moved outside render)
const EditableIdCell = ({ item, validationErrors, updateSectionId }) => (
  <FormField errorText={validationErrors[item.Id]?.find((err) => err.includes('Section ID'))}>
    <Input
      value={item.Id}
      onChange={({ detail }) => updateSectionId(item.Id, detail.value)}
      placeholder="e.g., section_1"
      invalid={validationErrors[item.Id]?.some((err) => err.includes('Section ID'))}
    />
  </FormField>
);

const EditableClassCell = ({ item, validationErrors, updateSection, getAvailableClasses }) => (
  <FormField errorText={validationErrors[item.Id]?.find((err) => err.includes('class'))}>
    <Select
      selectedOption={getAvailableClasses().find((option) => option.value === item.Class) || null}
      onChange={({ detail }) => updateSection(item.Id, 'Class', detail.selectedOption.value)}
      options={getAvailableClasses()}
      placeholder="Select class/type"
      invalid={validationErrors[item.Id]?.some((err) => err.includes('class'))}
    />
  </FormField>
);

const EditablePageIdsCell = ({ item, validationErrors, updateSection }) => {
  // Store the raw input value separately from the parsed PageIds
  const [inputValue, setInputValue] = React.useState(
    item.PageIds && item.PageIds.length > 0 ? item.PageIds.join(', ') : '',
  );

  // Update input value when item changes (e.g., when entering edit mode)
  React.useEffect(() => {
    setInputValue(item.PageIds && item.PageIds.length > 0 ? item.PageIds.join(', ') : '');
  }, [item.PageIds]);

  const parseAndUpdatePageIds = (value) => {
    const trimmedValue = value.trim();

    if (!trimmedValue) {
      updateSection(item.Id, 'PageIds', []);
      return;
    }

    // Parse comma-separated page IDs
    const rawPageIds = trimmedValue
      .split(/[,\s]+/) // Split on commas and/or whitespace
      .map((id) => id.trim())
      .filter((id) => id !== '');

    const seenIds = new Set();

    const pageIds = rawPageIds
      .map((rawId) => parseInt(rawId, 10))
      .filter((parsed) => !Number.isNaN(parsed) && parsed > 0)
      .filter((parsed) => {
        if (seenIds.has(parsed)) {
          return false;
        }
        seenIds.add(parsed);
        return true;
      });

    updateSection(item.Id, 'PageIds', pageIds);
  };

  const handleInputChange = ({ detail }) => {
    // Only update the input value, don't parse yet
    setInputValue(detail.value);
  };

  const handleBlur = () => {
    // Parse and update PageIds when user finishes editing
    parseAndUpdatePageIds(inputValue);
  };

  return (
    <FormField
      errorText={validationErrors[item.Id]?.find((err) => err.includes('Page') || err.includes('page'))}
      description="Enter page numbers separated by commas (e.g., 1, 2, 3)"
    >
      <Textarea
        value={inputValue}
        onChange={handleInputChange}
        onBlur={handleBlur}
        placeholder="1, 2, 3"
        autoComplete="off"
        spellCheck={false}
        rows={1}
        invalid={validationErrors[item.Id]?.some((err) => err.includes('Page') || err.includes('page'))}
      />
    </FormField>
  );
};

const EditableActionsCell = ({ item, deleteSection }) => (
  <SpaceBetween direction="horizontal" size="xs">
    <Button variant="icon" iconName="remove" ariaLabel="Delete section" onClick={() => deleteSection(item.Id)} />
  </SpaceBetween>
);

// Column definitions
const createColumnDefinitions = (pages, documentItem, mergedConfig) => [
  {
    id: 'id',
    header: 'Section ID',
    cell: (item) => <IdCell item={item} />,
    sortingField: 'Id',
    minWidth: 160,
    width: 160,
    isResizable: true,
  },
  {
    id: 'class',
    header: 'Class/Type',
    cell: (item) => <ClassCell item={item} />,
    sortingField: 'Class',
    minWidth: 200,
    width: 200,
    isResizable: true,
  },
  {
    id: 'pageIds',
    header: 'Page IDs',
    cell: (item) => <PageIdsCell item={item} />,
    minWidth: 120,
    width: 120,
    isResizable: true,
  },
  {
    id: 'confidenceAlerts',
    header: 'Low Confidence Fields',
    cell: (item) => <ConfidenceAlertsCell item={item} mergedConfig={mergedConfig} />,
    minWidth: 140,
    width: 140,
    isResizable: true,
  },
  {
    id: 'actions',
    header: 'Actions',
    cell: (item) => <ActionsCell item={item} pages={pages} documentItem={documentItem} mergedConfig={mergedConfig} />,
    minWidth: 400,
    width: 400,
    isResizable: true,
  },
];

// Edit mode column definitions - expanded to use full available width
const createEditColumnDefinitions = (
  validationErrors,
  updateSection,
  updateSectionId,
  getAvailableClasses,
  deleteSection,
) => [
  {
    id: 'id',
    header: 'Section ID',
    cell: (item) => (
      <EditableIdCell item={item} validationErrors={validationErrors} updateSectionId={updateSectionId} />
    ),
    minWidth: 160,
    width: 240,
    isResizable: true,
  },
  {
    id: 'class',
    header: 'Class/Type',
    cell: (item) => (
      <EditableClassCell
        item={item}
        validationErrors={validationErrors}
        updateSection={updateSection}
        getAvailableClasses={getAvailableClasses}
      />
    ),
    minWidth: 200,
    width: 300,
    isResizable: true,
  },
  {
    id: 'pageIds',
    header: 'Page IDs',
    cell: (item) => (
      <EditablePageIdsCell item={item} validationErrors={validationErrors} updateSection={updateSection} />
    ),
    minWidth: 200,
    width: 350,
    isResizable: true,
  },
  {
    id: 'actions',
    header: 'Actions',
    cell: (item) => <EditableActionsCell item={item} deleteSection={deleteSection} />,
    minWidth: 100,
    width: 130,
    isResizable: true,
  },
];

const SectionsPanel = ({ sections, pages, documentItem, mergedConfig, onSaveChanges }) => {
  const [isEditMode, setIsEditMode] = useState(false);
  const [editedSections, setEditedSections] = useState([]);
  const [validationErrors, setValidationErrors] = useState({});
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const { mergedConfig: configuration } = useConfiguration();

  // Initialize edited sections when entering edit mode
  useEffect(() => {
    if (isEditMode && sections) {
      const sectionsWithEditableFormat = sections.map((section) => ({
        Id: section.Id,
        Class: section.Class,
        PageIds: section.PageIds ? [...section.PageIds] : [],
        OriginalId: section.Id,
        isModified: false,
        isNew: false,
      }));
      setEditedSections(sectionsWithEditableFormat);
    }
  }, [isEditMode, sections]);

  // Get available classes from configuration
  const getAvailableClasses = () => {
    if (!configuration?.classes) return [];
    return configuration.classes.map((cls) => ({
      label: cls.name,
      value: cls.name,
    }));
  };

  // Generate next sequential section ID
  const getNextSectionId = () => {
    const allSections = [...(sections || []), ...editedSections];

    // Extract all numeric values from existing section IDs
    const sectionNumbers = allSections
      .map((section) => {
        // Handle both formats: simple numbers ("1", "2") and prefixed ("section_1", "section_2")
        const simpleMatch = section.Id.match(/^\d+$/);
        const prefixedMatch = section.Id.match(/^section_(\d+)$/);

        if (simpleMatch) {
          return parseInt(section.Id, 10);
        }
        if (prefixedMatch) {
          return parseInt(prefixedMatch[1], 10);
        }
        return null;
      })
      .filter((num) => num !== null && !Number.isNaN(num));

    // Determine the format to use based on existing sections
    const hasSimpleFormat = allSections.some((section) => /^\d+$/.test(section.Id));
    const hasPrefixedFormat = allSections.some((section) => /^section_\d+$/.test(section.Id));

    // Get the next number
    const maxNumber = sectionNumbers.length > 0 ? Math.max(...sectionNumbers) : 0;
    const nextNumber = maxNumber + 1;

    // Use existing format or default to simple format
    if (hasSimpleFormat && !hasPrefixedFormat) {
      return nextNumber.toString();
    }
    return `section_${nextNumber}`;
  };

  // Validate page ID overlaps and section ID uniqueness
  const validateSections = (sectionsToValidate) => {
    const errors = {};
    const pageIdMap = new Map();
    const sectionIdMap = new Map();

    // Get available page IDs from the document
    const availablePageIds = pages ? pages.map((page) => page.Id) : [];
    const maxPageId = availablePageIds.length > 0 ? Math.max(...availablePageIds) : 0;

    sectionsToValidate.forEach((section) => {
      const sectionErrors = [];

      // Check for empty or invalid section ID
      if (!section.Id || !section.Id.trim()) {
        sectionErrors.push('Section ID cannot be empty');
      } else if (sectionIdMap.has(section.Id)) {
        sectionErrors.push(`Section ID '${section.Id}' is already used by another section`);
      } else {
        sectionIdMap.set(section.Id, true);
      }

      // Check for empty page IDs
      if (!section.PageIds || section.PageIds.length === 0) {
        sectionErrors.push('Section must have at least one valid page ID');
      } else {
        // Check each page ID for validity
        const invalidPageIds = [];
        const nonExistentPageIds = [];

        section.PageIds.forEach((pageId) => {
          // Check if page ID is valid (should be handled by parsing, but double-check)
          if (!Number.isInteger(pageId) || pageId <= 0) {
            invalidPageIds.push(pageId);
          } else if (!availablePageIds.includes(pageId)) {
            // Check if page exists in document
            nonExistentPageIds.push(pageId);
          } else if (pageIdMap.has(pageId)) {
            // Check for overlaps with other sections
            const conflictSection = pageIdMap.get(pageId);
            sectionErrors.push(`Page ${pageId} is already assigned to section ${conflictSection}`);
          } else {
            pageIdMap.set(pageId, section.Id);
          }
        });

        // Add specific error messages for invalid page IDs
        if (invalidPageIds.length > 0) {
          sectionErrors.push(`Invalid page IDs: ${invalidPageIds.join(', ')} (must be positive integers)`);
        }

        if (nonExistentPageIds.length > 0) {
          sectionErrors.push(
            `Page IDs ${nonExistentPageIds.join(', ')} do not exist in this document (available: 1-${maxPageId})`,
          );
        }
      }

      if (sectionErrors.length > 0) {
        errors[section.Id] = sectionErrors;
      }
    });

    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  // Handle section modifications
  const updateSection = (sectionId, field, value) => {
    const updatedSections = editedSections.map((section) => {
      if (section.Id === sectionId) {
        const updated = {
          ...section,
          [field]: value,
          isModified: true,
        };
        return updated;
      }
      return section;
    });

    setEditedSections(updatedSections);

    // Re-validate after changes
    setTimeout(() => validateSections(updatedSections), 0);
  };

  // Handle section ID updates
  const updateSectionId = (oldId, newId) => {
    const updatedSections = editedSections.map((section) => {
      if (section.Id === oldId) {
        return {
          ...section,
          Id: newId.trim(),
          isModified: true,
        };
      }
      return section;
    });

    setEditedSections(updatedSections);

    // Update validation errors - move errors from old ID to new ID
    const updatedErrors = { ...validationErrors };
    if (updatedErrors[oldId]) {
      updatedErrors[newId.trim()] = updatedErrors[oldId];
      delete updatedErrors[oldId];
      setValidationErrors(updatedErrors);
    }

    // Re-validate after changes
    setTimeout(() => validateSections(updatedSections), 0);
  };

  // Add new section
  const addSection = () => {
    const newId = getNextSectionId();
    const newSection = {
      Id: newId,
      Class: '',
      PageIds: [],
      OriginalId: null,
      isModified: false,
      isNew: true,
    };

    const updatedSections = [...editedSections, newSection];
    setEditedSections(updatedSections);
  };

  // Delete section
  const deleteSection = (sectionId) => {
    const updatedSections = editedSections.filter((section) => section.Id !== sectionId);
    setEditedSections(updatedSections);

    // Remove validation errors for deleted section
    const updatedErrors = { ...validationErrors };
    delete updatedErrors[sectionId];
    setValidationErrors(updatedErrors);

    // Re-validate remaining sections
    setTimeout(() => validateSections(updatedSections), 0);
  };

  // Sort sections by starting page ID
  const sortSectionsByPageId = (sectionsToSort) => {
    return [...sectionsToSort].sort((a, b) => {
      const aMin = Math.min(...(a.PageIds || [Infinity]));
      const bMin = Math.min(...(b.PageIds || [Infinity]));
      return aMin - bMin;
    });
  };

  // Handle save changes
  const handleSaveChanges = async () => {
    if (!validateSections(editedSections)) {
      return;
    }

    setShowConfirmModal(true);
  };

  // Confirm and process changes
  const confirmSaveChanges = async () => {
    setIsProcessing(true);
    setShowConfirmModal(false);

    try {
      // Sort sections by starting page ID
      const sortedSections = sortSectionsByPageId(editedSections);

      // Identify modified sections
      const modifiedSections = sortedSections.map((section) => ({
        sectionId: section.Id,
        classification: section.Class,
        pageIds: section.PageIds,
        isNew: section.isNew,
        isDeleted: false,
      }));

      // Find deleted sections
      const deletedSectionIds =
        sections
          ?.filter((original) => !editedSections.find((edited) => edited.OriginalId === original.Id))
          ?.map((section) => ({
            sectionId: section.Id,
            classification: section.Class,
            pageIds: section.PageIds,
            isNew: false,
            isDeleted: true,
          })) || [];

      const allChanges = [...modifiedSections, ...deletedSectionIds];

      // Call the GraphQL API
      const result = await API.graphql(
        graphqlOperation(processChanges, {
          objectKey: documentItem?.ObjectKey,
          modifiedSections: allChanges,
        }),
      );

      const response = result.data.processChanges;

      if (!response.success) {
        throw new Error(response.message || 'Failed to process changes');
      }

      console.log('Successfully processed changes:', response);

      // Call the optional save handler for UI updates
      if (onSaveChanges) {
        await onSaveChanges(allChanges);
      }

      // Exit edit mode
      setIsEditMode(false);
      setEditedSections([]);
      setValidationErrors({});
    } catch (error) {
      console.error('Error saving changes:', error);
      // Handle error (could show toast notification)
      alert(`Error processing changes: ${error.message}`);
    } finally {
      setIsProcessing(false);
    }
  };

  // Cancel edit mode
  const cancelEdit = () => {
    setIsEditMode(false);
    setEditedSections([]);
    setValidationErrors({});
  };

  // Determine which columns and data to use
  const columnDefinitions = isEditMode
    ? createEditColumnDefinitions(validationErrors, updateSection, updateSectionId, getAvailableClasses, deleteSection)
    : createColumnDefinitions(pages, documentItem, mergedConfig);

  const tableItems = isEditMode ? editedSections : sections || [];

  // Check if there are any validation errors
  const hasValidationErrors = Object.keys(validationErrors).length > 0;

  return (
    <SpaceBetween size="l">
      <Container
        header={
          <Header
            variant="h2"
            actions={
              <SpaceBetween direction="horizontal" size="xs">
                {!isEditMode ? (
                  <Button variant="primary" iconName="edit" onClick={() => setIsEditMode(true)}>
                    Edit Sections
                  </Button>
                ) : (
                  <>
                    <Button variant="link" onClick={cancelEdit} disabled={isProcessing}>
                      Cancel
                    </Button>
                    <Button iconName="add-plus" onClick={addSection} disabled={isProcessing}>
                      Add Section
                    </Button>
                    <Button
                      variant="primary"
                      iconName="external"
                      onClick={handleSaveChanges}
                      disabled={hasValidationErrors || isProcessing}
                      loading={isProcessing}
                    >
                      Save & Process Changes
                    </Button>
                  </>
                )}
              </SpaceBetween>
            }
          >
            Document Sections
          </Header>
        }
      >
        {hasValidationErrors && (
          <Alert type="error" header="Validation Errors">
            Please fix the following errors before saving:
            <ul>
              {Object.entries(validationErrors).map(([sectionId, errors]) => (
                <li key={sectionId}>
                  <strong>Section {sectionId}:</strong>
                  <ul>
                    {errors.map((error) => (
                      <li key={`${sectionId}-error-${error.slice(0, 50)}`}>{error}</li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          </Alert>
        )}

        <Table
          columnDefinitions={columnDefinitions}
          items={tableItems}
          sortingDisabled
          variant="embedded"
          resizableColumns
          stickyHeader
          empty={
            <Box textAlign="center" color="inherit">
              <b>No sections</b>
              <Box padding={{ bottom: 's' }} variant="p" color="inherit">
                {isEditMode ? "Click 'Add Section' to create a new section." : 'This document has no sections.'}
              </Box>
            </Box>
          }
          wrapLines
        />
      </Container>

      {/* Confirmation Modal */}
      <Modal
        onDismiss={() => setShowConfirmModal(false)}
        visible={showConfirmModal}
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setShowConfirmModal(false)}>
                Cancel
              </Button>
              <Button variant="primary" onClick={confirmSaveChanges}>
                Confirm & Process
              </Button>
            </SpaceBetween>
          </Box>
        }
        header="Confirm Section Changes"
      >
        <SpaceBetween size="s">
          <Box>You are about to save changes to document sections and trigger selective reprocessing. This will:</Box>
          <ul>
            <li>Update section classifications and page assignments</li>
            <li>Remove extraction data for modified sections</li>
            <li>Reprocess only the changed sections (skipping OCR and classification steps)</li>
          </ul>
          <Box>
            <strong>Are you sure you want to continue?</strong>
          </Box>
        </SpaceBetween>
      </Modal>
    </SpaceBetween>
  );
};

export default SectionsPanel;
