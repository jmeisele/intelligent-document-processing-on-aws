// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React, { Suspense } from 'react';
import PropTypes from 'prop-types';
import { ConsoleLogger } from 'aws-amplify/utils';
import { Navigate, Route, Routes } from 'react-router-dom';

import { Button, useAuthenticator } from '@aws-amplify/ui-react';

import { SettingsContext } from '../contexts/settings';
import useParameterStore from '../hooks/use-parameter-store';
import useAppContext from '../contexts/app';
import CenteredSpinner from '../components/common/CenteredSpinner';

const DocumentsRoutes = React.lazy(() => import('./DocumentsRoutes'));
const DocumentsQueryRoutes = React.lazy(() => import('./DocumentsQueryRoutes'));
const DocumentsAnalyticsRoutes = React.lazy(() => import('./DocumentsAnalyticsRoutes'));

import {
  DOCUMENTS_PATH,
  DEFAULT_PATH,
  LOGIN_PATH,
  LOGOUT_PATH,
  DOCUMENTS_KB_QUERY_PATH,
  DOCUMENTS_ANALYTICS_PATH,
} from './constants';

const logger = new ConsoleLogger('AuthRoutes');

const AuthRoutes = ({ redirectParam }) => {
  const { currentCredentials } = useAppContext();
  const settings = useParameterStore(currentCredentials);
  const { signOut } = useAuthenticator();

  // eslint-disable-next-line react/jsx-no-constructed-context-values
  const settingsContextValue = {
    settings,
  };
  logger.debug('settingsContextValue', settingsContextValue);

  return (
    <SettingsContext.Provider value={settingsContextValue}>
      <Routes>
        <Route
          path={`${DOCUMENTS_PATH}/*`}
          element={
            <Suspense fallback={<CenteredSpinner />}>
              <DocumentsRoutes />
            </Suspense>
          }
        />
        <Route
          path={LOGIN_PATH}
          element={
            <Navigate to={!redirectParam || redirectParam === LOGIN_PATH ? DEFAULT_PATH : `${redirectParam}`} replace />
          }
        />
        <Route path={LOGOUT_PATH} element={<Button onClick={signOut}>Sign Out</Button>} />
        <Route
          path={`${DOCUMENTS_KB_QUERY_PATH}/*`}
          element={
            <Suspense fallback={<CenteredSpinner />}>
              <DocumentsQueryRoutes />
            </Suspense>
          }
        />
        <Route
          path={`${DOCUMENTS_ANALYTICS_PATH}/*`}
          element={
            <Suspense fallback={<CenteredSpinner />}>
              <DocumentsAnalyticsRoutes />
            </Suspense>
          }
        />
        <Route path="*" element={<Navigate to={DEFAULT_PATH} replace />} />
      </Routes>
    </SettingsContext.Provider>
  );
};

AuthRoutes.propTypes = {
  redirectParam: PropTypes.string.isRequired,
};

export default AuthRoutes;
