// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React from 'react';
import { Route, Routes } from 'react-router-dom';
import { ConsoleLogger } from 'aws-amplify/utils';

// Import the component directly from the file instead of the directory
import DocumentsAgentsLayout from '../components/document-agents-layout/DocumentsAgentsLayout';
import GenAIIDPLayout from '../components/genaiidp-layout';

const logger = new ConsoleLogger('DocumentsAnalyticsRoutes');

const DocumentsAnalyticsRoutes = () => {
  logger.info('DocumentsAnalyticsRoutes');

  return (
    <Routes>
      <Route
        path="*"
        element={
          <GenAIIDPLayout>
            <DocumentsAgentsLayout />
          </GenAIIDPLayout>
        }
      />
    </Routes>
  );
};

export default DocumentsAnalyticsRoutes;
