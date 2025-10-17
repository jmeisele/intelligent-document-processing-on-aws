// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React, { Suspense } from 'react';
import { Route, Routes } from 'react-router-dom';
import { ConsoleLogger } from 'aws-amplify/utils';
import CenteredSpinner from '../components/common/CenteredSpinner';
import GenAIIDPTopNavigation from '../components/genai-idp-top-navigation';

const GenAIIDPLayout = React.lazy(() => import('../components/genaiidp-layout'));

const logger = new ConsoleLogger('DocumentsRoutes');

const DocumentsRoutes = () => {
  logger.info('DocumentsRoutes');

  return (
    <Routes>
      <Route
        path="*"
        element={
          <div>
            <GenAIIDPTopNavigation />
            <Suspense fallback={<CenteredSpinner />}>
              <GenAIIDPLayout />
            </Suspense>
          </div>
        }
      />
    </Routes>
  );
};

export default DocumentsRoutes;
