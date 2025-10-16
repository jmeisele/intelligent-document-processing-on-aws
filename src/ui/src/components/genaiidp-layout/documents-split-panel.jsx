// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React from 'react';
import { Route, Switch, useRouteMatch } from 'react-router-dom';
import { ConsoleLogger } from 'aws-amplify/utils';

import { DOCUMENTS_PATH } from '../../routes/constants';

import DocumentListSplitPanel from '../document-list/DocumentListSplitPanel';

const logger = new ConsoleLogger('CallsSplitPanel');

const CallsSplitPanel = () => {
  const { path } = useRouteMatch();
  logger.debug('path', path);
  return (
    <Switch>
      <Route exact path={DOCUMENTS_PATH}>
        <DocumentListSplitPanel />
      </Route>
    </Switch>
  );
};

export default CallsSplitPanel;
