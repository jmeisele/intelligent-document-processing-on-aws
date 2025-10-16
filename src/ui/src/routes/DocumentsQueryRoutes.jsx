// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React from 'react';
import { Route, Routes } from 'react-router-dom';
import { ConsoleLogger } from 'aws-amplify/utils';

import DocumentsQueryLayout from '../components/document-kb-query-layout';
import GenAIIDPLayout from '../components/genaiidp-layout';

const logger = new ConsoleLogger('DocumentsQueryRoutes');

const DocumentsQueryRoutes = () => {
  logger.info('DocumentsQueryRoutes');

  return (
    <Routes>
      <Route
        path="*"
        element={
          <GenAIIDPLayout>
            <DocumentsQueryLayout />
          </GenAIIDPLayout>
        }
      />
    </Routes>
  );
};

export default DocumentsQueryRoutes;
