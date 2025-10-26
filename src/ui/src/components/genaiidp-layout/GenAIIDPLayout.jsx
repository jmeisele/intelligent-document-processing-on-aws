// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React, { useState } from 'react';
import PropTypes from 'prop-types';
import { Routes, Route } from 'react-router-dom';
import { AppLayout, Flashbar } from '@cloudscape-design/components';

import { ConsoleLogger } from 'aws-amplify/utils';

import { DocumentsContext } from '../../contexts/documents';

import useNotifications from '../../hooks/use-notifications';
import useSplitPanel from '../../hooks/use-split-panel';
import useGraphQlApi from '../../hooks/use-graphql-api';

import DocumentList from '../document-list';
import DocumentDetails from '../document-details';
import DocumentsQueryLayout from '../document-kb-query-layout';
import DocumentsAgentsLayout from '../document-agents-layout/DocumentsAgentsLayout';
import UploadDocumentPanel from '../upload-document';
import DiscoveryPanel from '../discovery/DiscoveryPanel';
import { appLayoutLabels } from '../common/labels';

import Navigation from './navigation';
import Breadcrumbs from './breadcrumbs';
import ToolsPanel from './tools-panel';
import SplitPanel from './documents-split-panel';
import ConfigurationLayout from '../configuration-layout';

import { DOCUMENT_LIST_SHARDS_PER_DAY, PERIODS_TO_LOAD_STORAGE_KEY } from '../document-list/documents-table-config';

import useAppContext from '../../contexts/app';

const logger = new ConsoleLogger('GenAIIDPLayout');

const GenAIIDPLayout = ({ children }) => {
  const { navigationOpen, setNavigationOpen } = useAppContext();

  const notifications = useNotifications();
  const [toolsOpen, setToolsOpen] = useState(false);
  const [selectedItems, setSelectedItems] = useState([]);

  const getInitialPeriodsToLoad = () => {
    // default to 2 hours - half of one (4hr) shard period
    let periods = 0.5;
    try {
      const periodsFromStorage = Math.abs(JSON.parse(localStorage.getItem(PERIODS_TO_LOAD_STORAGE_KEY)));
      // prettier-ignore
      if (
        !Number.isFinite(periodsFromStorage)
        // load max of to 30 days
        || periodsFromStorage > DOCUMENT_LIST_SHARDS_PER_DAY * 30
      ) {
        logger.warn('invalid initialPeriodsToLoad value from local storage');
      } else {
        periods = (periodsFromStorage > 0) ? periodsFromStorage : periods;
        localStorage.setItem(PERIODS_TO_LOAD_STORAGE_KEY, JSON.stringify(periods));
      }
    } catch {
      logger.warn('failed to parse initialPeriodsToLoad from local storage');
    }

    return periods;
  };
  const initialPeriodsToLoad = getInitialPeriodsToLoad();

  const {
    documents,
    getDocumentDetailsFromIds,
    isDocumentsListLoading,
    periodsToLoad,
    setIsDocumentsListLoading,
    setPeriodsToLoad,
    deleteDocuments,
    reprocessDocuments,
  } = useGraphQlApi({ initialPeriodsToLoad });

  // eslint-disable-next-line prettier/prettier
  const { splitPanelOpen, onSplitPanelToggle, splitPanelSize, onSplitPanelResize } = useSplitPanel(selectedItems);

  // eslint-disable-next-line react/jsx-no-constructed-context-values
  const documentsContextValue = {
    documents,
    getDocumentDetailsFromIds,
    isDocumentsListLoading,
    selectedItems,
    setIsDocumentsListLoading,
    setPeriodsToLoad,
    setToolsOpen,
    setSelectedItems,
    periodsToLoad,
    toolsOpen,
    deleteDocuments,
    reprocessDocuments,
  };

  return (
    <DocumentsContext.Provider value={documentsContextValue}>
      <AppLayout
        headerSelector="#top-navigation"
        navigation={<Navigation />}
        navigationOpen={navigationOpen}
        onNavigationChange={({ detail }) => setNavigationOpen(detail.open)}
        breadcrumbs={<Breadcrumbs />}
        notifications={<Flashbar items={notifications} />}
        tools={<ToolsPanel />}
        toolsOpen={toolsOpen}
        onToolsChange={({ detail }) => setToolsOpen(detail.open)}
        splitPanelOpen={splitPanelOpen}
        onSplitPanelToggle={onSplitPanelToggle}
        splitPanelSize={splitPanelSize}
        onSplitPanelResize={onSplitPanelResize}
        splitPanel={<SplitPanel />}
        content={
          children || (
            <Routes>
              <Route index element={<DocumentList />} />
              <Route path="query" element={<DocumentsQueryLayout />} />
              <Route path="agents" element={<DocumentsAgentsLayout />} />
              <Route path="config" element={<ConfigurationLayout />} />
              <Route path="upload" element={<UploadDocumentPanel />} />
              <Route path="discovery" element={<DiscoveryPanel />} />
              <Route path=":objectKey" element={<DocumentDetails />} />
            </Routes>
          )
        }
        ariaLabels={appLayoutLabels}
      />
    </DocumentsContext.Provider>
  );
};

GenAIIDPLayout.propTypes = {
  children: PropTypes.node,
};

export default GenAIIDPLayout;
