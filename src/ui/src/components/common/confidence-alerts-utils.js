// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

/**
 * Utility functions for handling confidence threshold alerts
 */

/**
 * Get the HITL confidence threshold from configuration
 * @param {Object} mergedConfig - Merged configuration object
 * @returns {number} HITL confidence threshold as decimal (0.0-1.0)
 */
export const getHitlConfidenceThreshold = (mergedConfig) => {
  if (!mergedConfig || !mergedConfig.assessment || !mergedConfig.assessment.hitl_confidence_score) {
    return 0.8; // Default threshold of 80%
  }

  const threshold = parseFloat(mergedConfig.assessment.hitl_confidence_score);
  // Convert from percentage (1-100) to decimal (0.0-1.0)
  return threshold / 100;
};

/**
 * Enhanced function to find explainability data in various possible locations within a section
 * @param {Object} section - Document section
 * @returns {Object|null} Explainability data if found, null otherwise
 */
const findExplainabilityData = (section) => {
  if (!section || typeof section !== 'object') {
    return null;
  }

  // Check direct explainabilityData property
  if (section.explainabilityData) {
    return section.explainabilityData;
  }

  // Check Output.explainabilityData
  if (section.Output && section.Output.explainabilityData) {
    return section.Output.explainabilityData;
  }

  // Check if Output itself contains confidence data
  if (section.Output && typeof section.Output === 'object') {
    // Look for any key that might contain explainability data
    const outputKeys = Object.keys(section.Output);

    // Check for keys that might contain explainability data
    const explainabilityKey = outputKeys.find(
      (key) =>
        key.toLowerCase().includes('explainability') ||
        key.toLowerCase().includes('confidence') ||
        key.toLowerCase().includes('assessment'),
    );

    if (explainabilityKey && section.Output[explainabilityKey]) {
      return section.Output[explainabilityKey];
    }

    // If no specific explainability key found, check if Output contains field-level confidence data
    // Look for nested objects that might contain confidence scores
    const outputKeysArray = Object.keys(section.Output);
    // eslint-disable-next-line no-restricted-syntax
    for (const key of outputKeysArray) {
      const value = section.Output[key];
      if (value && typeof value === 'object' && !Array.isArray(value)) {
        // Check if this object contains fields with confidence scores
        const hasConfidenceData = Object.values(value).some(
          (fieldValue) => fieldValue && typeof fieldValue === 'object' && typeof fieldValue.confidence === 'number',
        );

        if (hasConfidenceData) {
          return value;
        }
      }
    }
  }

  return null;
};

/**
 * Get fields that are below the HITL confidence threshold from explainability data
 * @param {Object} explainabilityData - Explainability data containing confidence scores
 * @param {number} hitlThreshold - HITL confidence threshold (0.0-1.0)
 * @param {string} path - Current path in the data structure
 * @returns {Array} Array of field objects with confidence below threshold
 */
export const getFieldsBelowThreshold = (explainabilityData, hitlThreshold, path = '') => {
  const fieldsBelow = [];

  if (!explainabilityData || typeof explainabilityData !== 'object') {
    return fieldsBelow;
  }

  Object.entries(explainabilityData).forEach(([fieldName, fieldData]) => {
    if (fieldData && typeof fieldData === 'object') {
      const { confidence } = fieldData;

      if (typeof confidence === 'number') {
        const fieldPath = path ? `${path}.${fieldName}` : fieldName;

        if (confidence < hitlThreshold) {
          fieldsBelow.push({
            fieldName,
            fieldPath,
            confidence,
            confidenceThreshold: hitlThreshold,
          });
        }
      }

      // Recursively check nested objects and arrays
      if (Array.isArray(fieldData)) {
        fieldData.forEach((item, index) => {
          if (item && typeof item === 'object') {
            const nestedPath = path ? `${path}.${fieldName}[${index}]` : `${fieldName}[${index}]`;
            const nestedFields = getFieldsBelowThreshold(item, hitlThreshold, nestedPath);
            fieldsBelow.push(...nestedFields);
          }
        });
      } else if (typeof fieldData === 'object' && fieldData !== null && !('confidence' in fieldData)) {
        // This is a nested object without confidence, recurse into it
        const nestedPath = path ? `${path}.${fieldName}` : fieldName;
        const nestedFields = getFieldsBelowThreshold(fieldData, hitlThreshold, nestedPath);
        fieldsBelow.push(...nestedFields);
      }
    }
  });

  return fieldsBelow;
};

/**
 * Calculate the total count of confidence threshold alerts for a document using dynamic threshold
 * @param {Array} sections - Array of document sections
 * @param {Object} mergedConfig - Merged configuration object
 * @returns {number} Total count of confidence threshold alerts
 */
export const getDocumentConfidenceAlertCount = (sections, mergedConfig = null) => {
  if (!sections || !Array.isArray(sections)) {
    return 0;
  }

  // If mergedConfig is provided, use dynamic threshold calculation
  if (mergedConfig) {
    const hitlThreshold = getHitlConfidenceThreshold(mergedConfig);

    return sections.reduce((total, section) => {
      const explainabilityData = findExplainabilityData(section);

      if (explainabilityData) {
        const fieldsBelow = getFieldsBelowThreshold(explainabilityData, hitlThreshold);
        return total + fieldsBelow.length;
      }

      // Fallback to existing ConfidenceThresholdAlerts if no explainability data
      if (section.ConfidenceThresholdAlerts && Array.isArray(section.ConfidenceThresholdAlerts)) {
        return total + section.ConfidenceThresholdAlerts.length;
      }

      return total;
    }, 0);
  }

  // Fallback to original logic for backward compatibility
  return sections.reduce((total, section) => {
    if (section.ConfidenceThresholdAlerts && Array.isArray(section.ConfidenceThresholdAlerts)) {
      return total + section.ConfidenceThresholdAlerts.length;
    }
    return total;
  }, 0);
};

/**
 * Calculate the count of confidence threshold alerts for a specific section using dynamic threshold
 * @param {Object} section - Document section
 * @param {Object} mergedConfig - Merged configuration object
 * @returns {number} Count of confidence threshold alerts for the section
 */
export const getSectionConfidenceAlertCount = (section, mergedConfig = null) => {
  if (!section) {
    return 0;
  }

  // If mergedConfig is provided, use dynamic threshold calculation
  if (mergedConfig) {
    const hitlThreshold = getHitlConfidenceThreshold(mergedConfig);
    const explainabilityData = findExplainabilityData(section);

    if (explainabilityData) {
      const fieldsBelow = getFieldsBelowThreshold(explainabilityData, hitlThreshold);
      return fieldsBelow.length;
    }
  }

  // Fallback to existing ConfidenceThresholdAlerts
  if (!section.ConfidenceThresholdAlerts || !Array.isArray(section.ConfidenceThresholdAlerts)) {
    return 0;
  }
  return section.ConfidenceThresholdAlerts.length;
};

/**
 * Get detailed confidence alerts for a section using dynamic threshold
 * @param {Object} section - Document section
 * @param {Object} mergedConfig - Merged configuration object
 * @returns {Array} Array of detailed confidence alert objects
 */
export const getSectionConfidenceAlerts = (section, mergedConfig = null) => {
  if (!section) {
    return [];
  }

  // If mergedConfig is provided, use dynamic threshold calculation
  if (mergedConfig) {
    const hitlThreshold = getHitlConfidenceThreshold(mergedConfig);
    const explainabilityData = findExplainabilityData(section);

    if (explainabilityData) {
      const fieldsBelow = getFieldsBelowThreshold(explainabilityData, hitlThreshold);
      return fieldsBelow;
    }
  }

  // Fallback to existing ConfidenceThresholdAlerts
  if (!section.ConfidenceThresholdAlerts || !Array.isArray(section.ConfidenceThresholdAlerts)) {
    return [];
  }

  return section.ConfidenceThresholdAlerts.map((alert) => ({
    fieldName: alert.attributeName,
    fieldPath: alert.attributeName,
    confidence: alert.confidence,
    confidenceThreshold: alert.confidenceThreshold,
  }));
};

/**
 * Check if a field should be highlighted due to low confidence
 * @param {string} fieldName - Name of the field
 * @param {number} fieldConfidence - Confidence value for the field
 * @param {Array} confidenceThresholdAlerts - Array of confidence threshold alerts
 * @returns {Object} Object with highlight flag and threshold info
 */
export const getFieldHighlightInfo = (fieldName, fieldConfidence, confidenceThresholdAlerts) => {
  if (!confidenceThresholdAlerts || !Array.isArray(confidenceThresholdAlerts) || !fieldName) {
    return { shouldHighlight: false };
  }

  const alertMatch = confidenceThresholdAlerts.find((alert) => alert.attributeName === fieldName);

  if (alertMatch) {
    return {
      shouldHighlight: true,
      confidence: alertMatch.confidence,
      confidenceThreshold: alertMatch.confidenceThreshold,
      alert: alertMatch,
    };
  }

  return { shouldHighlight: false };
};

/**
 * Get confidence information for a field from explainability data with dynamic threshold support
 * @param {string} fieldName - Name of the field
 * @param {Object} explainabilityInfo - Explainability info object containing confidence data for all fields
 * @param {Array} path - Optional path array for nested fields (e.g., ['FederalTaxes', 0, 'YTD'])
 * @param {Object} mergedConfig - Merged configuration object for dynamic threshold
 * @returns {Object} Object with confidence info and display properties
 */
export const getFieldConfidenceInfo = (fieldName, explainabilityInfo, path = [], mergedConfig = null) => {
  if (!explainabilityInfo || !fieldName) {
    return { hasConfidenceInfo: false };
  }

  // explainabilityInfo is typically an array, get the first element
  const explainabilityData = Array.isArray(explainabilityInfo) ? explainabilityInfo[0] : explainabilityInfo;

  if (!explainabilityData || typeof explainabilityData !== 'object') {
    return { hasConfidenceInfo: false };
  }

  // Navigate to the nested location in explainabilityData using the path
  let currentExplainabilityData = explainabilityData;

  // Traverse the path to find the nested explainability data
  // eslint-disable-next-line no-restricted-syntax
  for (const pathSegment of path) {
    if (currentExplainabilityData && typeof currentExplainabilityData === 'object') {
      if (Array.isArray(currentExplainabilityData)) {
        // Handle array indices
        const index = parseInt(pathSegment, 10);
        if (!Number.isNaN(index) && index >= 0 && index < currentExplainabilityData.length) {
          // nosemgrep: javascript.lang.security.audit.prototype-pollution.prototype-pollution-loop
          currentExplainabilityData = currentExplainabilityData[index];
        } else {
          return { hasConfidenceInfo: false };
        }
      } else {
        // Handle object properties
        // nosemgrep: javascript.lang.security.audit.prototype-pollution.prototype-pollution-loop
        currentExplainabilityData = currentExplainabilityData[pathSegment];
      }
    } else {
      return { hasConfidenceInfo: false };
    }
  }

  // Now look for the field in the current explainability data location
  if (!currentExplainabilityData || typeof currentExplainabilityData !== 'object') {
    return { hasConfidenceInfo: false };
  }

  const fieldData = currentExplainabilityData[fieldName];
  if (!fieldData || typeof fieldData !== 'object') {
    return { hasConfidenceInfo: false };
  }

  const { confidence } = fieldData;
  let confidenceThreshold = fieldData.confidence_threshold;

  // Check if we have confidence data
  const hasConfidence = typeof confidence === 'number';

  if (!hasConfidence) {
    return { hasConfidenceInfo: false };
  }

  // Use dynamic threshold from configuration if available and no field-specific threshold
  if (mergedConfig && (confidenceThreshold === undefined || confidenceThreshold === null)) {
    confidenceThreshold = getHitlConfidenceThreshold(mergedConfig);
  }

  const hasThreshold = typeof confidenceThreshold === 'number';

  // Case 1: Both confidence and threshold available
  if (hasConfidence && hasThreshold) {
    const isAboveThreshold = confidence >= confidenceThreshold;
    return {
      hasConfidenceInfo: true,
      confidence,
      confidenceThreshold,
      isAboveThreshold,
      shouldHighlight: !isAboveThreshold,
      textColor: isAboveThreshold ? '#16794d' : '#d13313', // Green for good, red for poor
      displayMode: 'with-threshold',
    };
  }

  // Case 2: Only confidence available (no threshold)
  if (hasConfidence && !hasThreshold) {
    return {
      hasConfidenceInfo: true,
      confidence,
      confidenceThreshold: undefined,
      isAboveThreshold: undefined,
      shouldHighlight: false,
      textColor: '#000000', // Black font when no threshold to compare
      displayMode: 'confidence-only',
    };
  }

  // Case 3: Neither available (handled by the hasConfidence check above)
  return { hasConfidenceInfo: false };
};

/**
 * Get all confidence threshold alerts for a section as a map by attribute name
 * @param {Object} section - Document section
 * @returns {Object} Map of attribute names to alert objects
 */
export const getConfidenceAlertsMap = (section) => {
  if (!section || !section.ConfidenceThresholdAlerts || !Array.isArray(section.ConfidenceThresholdAlerts)) {
    return {};
  }

  const alertsMap = {};
  section.ConfidenceThresholdAlerts.forEach((alert) => {
    if (alert.attributeName) {
      alertsMap[alert.attributeName] = alert;
    }
  });

  return alertsMap;
};
