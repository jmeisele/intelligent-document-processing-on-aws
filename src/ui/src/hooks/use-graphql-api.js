// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState, useCallback, useRef } from 'react';
import { generateClient } from 'aws-amplify/api';
import { ConsoleLogger } from 'aws-amplify/utils';

import useAppContext from '../contexts/app';
import listDocumentsDateShard from '../graphql/queries/listDocumentsDateShard';
import listDocumentsDateHour from '../graphql/queries/listDocumentsDateHour';
import getDocument from '../graphql/queries/getDocument';
import deleteDocument from '../graphql/queries/deleteDocument';
import reprocessDocument from '../graphql/queries/reprocessDocument';
import onCreateDocument from '../graphql/queries/onCreateDocument';
import onUpdateDocument from '../graphql/queries/onUpdateDocument';
import { DOCUMENT_LIST_SHARDS_PER_DAY } from '../components/document-list/documents-table-config';

const client = generateClient();

const logger = new ConsoleLogger('useGraphQlApi');

const useGraphQlApi = ({ initialPeriodsToLoad = DOCUMENT_LIST_SHARDS_PER_DAY * 2 } = {}) => {
  const [periodsToLoad, setPeriodsToLoad] = useState(initialPeriodsToLoad);
  const [isDocumentsListLoading, setIsDocumentsListLoading] = useState(false);
  const [documents, setDocuments] = useState([]);
  const { setErrorMessage } = useAppContext();

  const subscriptionsRef = useRef({ onCreate: null, onUpdate: null });

  const setDocumentsDeduped = useCallback((documentValues) => {
    logger.debug('setDocumentsDeduped called with:', documentValues);
    setDocuments((currentDocuments) => {
      const documentValuesdocumentIds = documentValues.map((c) => c.ObjectKey);
      const updatedDocuments = [
        ...currentDocuments.filter((c) => !documentValuesdocumentIds.includes(c.ObjectKey)),
        ...documentValues.map((document) => ({
          ...document,
          ListPK: document.ListPK || currentDocuments.find((c) => c.ObjectKey === document.ObjectKey)?.ListPK,
          ListSK: document.ListSK || currentDocuments.find((c) => c.ObjectKey === document.ObjectKey)?.ListSK,
        })),
      ];
      logger.debug('Documents state updated, new count:', updatedDocuments.length);
      return updatedDocuments;
    });
  }, []);

  const getDocumentDetailsFromIds = useCallback(
    async (objectKeys) => {
      // prettier-ignore
      logger.debug('getDocumentDetailsFromIds', objectKeys);
      const getDocumentPromises = objectKeys.map((objectKey) =>
        client.graphql({ query: getDocument, variables: { objectKey } }),
      );
      const getDocumentResolutions = await Promise.allSettled(getDocumentPromises);
      const getDocumentRejected = getDocumentResolutions.filter((r) => r.status === 'rejected');
      if (getDocumentRejected.length) {
        setErrorMessage('failed to get document details - please try again later');
        logger.error('get document promises rejected', getDocumentRejected);
      }
      const documentValues = getDocumentResolutions
        .filter((r) => r.status === 'fulfilled')
        .map((r) => r.value?.data?.getDocument);

      return documentValues;
    },
    [setErrorMessage],
  );

  useEffect(() => {
    if (subscriptionsRef.current.onCreate) {
      logger.debug('onCreateDocument subscription already exists, skipping');
      return undefined;
    }

    logger.debug('onCreateDocument subscription');
    const subscription = client.graphql({ query: onCreateDocument }).subscribe({
      next: async (subscriptionData) => {
        logger.debug('document list subscription update', subscriptionData);
        const data = subscriptionData?.data;
        const objectKey = data?.onCreateDocument?.ObjectKey || '';
        if (objectKey) {
          try {
            const documentValues = await getDocumentDetailsFromIds([objectKey]);
            if (documentValues && documentValues.length > 0) {
              setDocumentsDeduped(documentValues);
            }
          } catch (error) {
            logger.error('Error processing onCreateDocument subscription:', error);
          }
        }
      },
      error: (error) => {
        logger.error('onCreateDocument subscription error:', error);
        setErrorMessage('document list network subscription failed - please reload the page');
      },
    });

    subscriptionsRef.current.onCreate = subscription;

    return () => {
      logger.debug('onCreateDocument subscription cleanup');
      if (subscriptionsRef.current.onCreate) {
        subscriptionsRef.current.onCreate.unsubscribe();
        subscriptionsRef.current.onCreate = null;
      }
    };
  }, [getDocumentDetailsFromIds, setDocumentsDeduped, setErrorMessage]);

  useEffect(() => {
    if (subscriptionsRef.current.onUpdate) {
      logger.debug('onUpdateDocument subscription already exists, skipping');
      return undefined;
    }

    logger.debug('onUpdateDocument subscription setup');
    const subscription = client.graphql({ query: onUpdateDocument }).subscribe({
      next: async (subscriptionData) => {
        logger.debug('document update subscription received', subscriptionData);
        const data = subscriptionData?.data;
        const documentUpdateEvent = data?.onUpdateDocument;
        if (documentUpdateEvent?.ObjectKey) {
          setDocumentsDeduped([documentUpdateEvent]);
        }
      },
      error: (error) => {
        logger.error('onUpdateDocument subscription error:', error);
        setErrorMessage('document update network request failed - please reload the page');
      },
    });

    subscriptionsRef.current.onUpdate = subscription;

    return () => {
      logger.debug('onUpdateDocument subscription cleanup');
      if (subscriptionsRef.current.onUpdate) {
        subscriptionsRef.current.onUpdate.unsubscribe();
        subscriptionsRef.current.onUpdate = null;
      }
    };
  }, [setDocumentsDeduped, setErrorMessage, getDocumentDetailsFromIds]);

  const listDocumentIdsByDateShards = async ({ date, shards }) => {
    const listDocumentsDateShardPromises = shards.map((i) => {
      logger.debug('sending list document date shard', date, i);
      return client.graphql({ query: listDocumentsDateShard, variables: { date, shard: i } });
    });
    const listDocumentsDateShardResolutions = await Promise.allSettled(listDocumentsDateShardPromises);

    const listRejected = listDocumentsDateShardResolutions.filter((r) => r.status === 'rejected');
    if (listRejected.length) {
      setErrorMessage('failed to list documents - please try again later');
      logger.error('list document promises rejected', listRejected);
    }
    const documentData = listDocumentsDateShardResolutions
      .filter((r) => r.status === 'fulfilled')
      .map((r) => r.value?.data?.listDocumentsDateShard?.Documents || [])
      .reduce((pv, cv) => [...cv, ...pv], []);

    return documentData;
  };

  const listDocumentIdsByDateHours = async ({ date, hours }) => {
    const listDocumentsDateHourPromises = hours.map((i) => {
      logger.debug('sending list document date hour', date, i);
      return client.graphql({ query: listDocumentsDateHour, variables: { date, hour: i } });
    });
    const listDocumentsDateHourResolutions = await Promise.allSettled(listDocumentsDateHourPromises);

    const listRejected = listDocumentsDateHourResolutions.filter((r) => r.status === 'rejected');
    if (listRejected.length) {
      setErrorMessage('failed to list documents - please try again later');
      logger.error('list document promises rejected', listRejected);
    }

    const documentData = listDocumentsDateHourResolutions
      .filter((r) => r.status === 'fulfilled')
      .map((r) => r.value?.data?.listDocumentsDateHour?.Documents || [])
      .reduce((pv, cv) => [...cv, ...pv], []);

    return documentData;
  };

  const sendSetDocumentsForPeriod = async () => {
    // XXX this logic should be moved to the API
    try {
      const now = new Date();

      // array of arrays containing date / shard pairs relative to current UTC time
      // e.g. 2 periods to on load 2021-01-01T:20:00:00.000Z ->
      // [ [ '2021-01-01', 3 ], [ '2021-01-01', 4 ] ]
      const hoursInShard = 24 / DOCUMENT_LIST_SHARDS_PER_DAY;
      const dateShardPairs = [...Array(parseInt(periodsToLoad, 10)).keys()].map((p) => {
        const deltaInHours = p * hoursInShard;
        const relativeDate = new Date(now - deltaInHours * 3600 * 1000);

        const relativeDateString = relativeDate.toISOString().split('T')[0];
        const shard = Math.floor(relativeDate.getUTCHours() / hoursInShard);

        return [relativeDateString, shard];
      });

      // reduce array of date/shard pairs into object of shards by date
      // e.g. [ [ '2021-01-01', 3 ], [ '2021-01-01', 4 ] ] -> { '2021-01-01': [ 3, 4 ] }
      const dateShards = dateShardPairs.reduce((p, c) => ({ ...p, [c[0]]: [...(p[c[0]] || []), c[1]] }), {});
      logger.debug('document list date shards', dateShards);

      // parallelizes listDocuments and getDocumentDetails
      // alternatively we could implement it by sending multiple graphql queries in 1 request
      const documentDataDateShardPromises = Object.keys(dateShards).map(
        // pretttier-ignore
        async (d) => listDocumentIdsByDateShards({ date: d, shards: dateShards[d] }),
      );

      // get document Ids by hour on residual hours outside of the lower shard date/hour boundary
      // or just last n hours when periodsToLoad is less than 1 shard period
      let baseDate;
      let residualHours;
      if (periodsToLoad < 1) {
        baseDate = new Date(now);
        const numHours = parseInt(periodsToLoad * hoursInShard, 10);
        residualHours = [...Array(numHours).keys()].map((h) => baseDate.getUTCHours() - h);
      } else {
        baseDate = new Date(now - periodsToLoad * hoursInShard * 3600 * 1000);
        const residualBaseHour = baseDate.getUTCHours() % hoursInShard;
        residualHours = [...Array(hoursInShard - residualBaseHour).keys()].map((h) => baseDate.getUTCHours() + h);
      }
      const baseDateString = baseDate.toISOString().split('T')[0];

      const residualDateHours = { date: baseDateString, hours: residualHours };
      logger.debug('document list date hours', residualDateHours);

      const documentDataDateHourPromise = listDocumentIdsByDateHours(residualDateHours);

      const documentDataPromises = [...documentDataDateShardPromises, documentDataDateHourPromise];
      const documentDetailsPromises = documentDataPromises.map(async (documentDataPromise) => {
        const documentData = await documentDataPromise;
        const objectKeys = documentData.map((item) => item.ObjectKey);
        const documentDetails = await getDocumentDetailsFromIds(objectKeys);
        // Merge document details with PK and SK
        return documentDetails.map((detail) => {
          const matchingData = documentData.find((item) => item.ObjectKey === detail.ObjectKey);
          return { ...detail, ListPK: matchingData.PK, ListSK: matchingData.SK };
        });
      });

      const documentValuesPromises = documentDetailsPromises.map(async (documentValuesPromise) => {
        const documentValues = await documentValuesPromise;
        logger.debug('documentValues', documentValues);
        return documentValues;
      });

      const getDocumentsPromiseResolutions = await Promise.allSettled(documentValuesPromises);
      logger.debug('getDocumentsPromiseResolutions', getDocumentsPromiseResolutions);
      const documentValuesReduced = getDocumentsPromiseResolutions
        .filter((r) => r.status === 'fulfilled')
        .map((r) => r.value)
        .reduce((previous, current) => [...previous, ...current], []);
      logger.debug('documentValuesReduced', documentValuesReduced);
      setDocumentsDeduped(documentValuesReduced);
      setIsDocumentsListLoading(false);
      const getDocumentsRejected = getDocumentsPromiseResolutions.filter((r) => r.status === 'rejected');
      if (getDocumentsRejected.length) {
        setErrorMessage('failed to get document details - please try again later');
        logger.error('get document promises rejected', getDocumentsRejected);
      }
    } catch (error) {
      setIsDocumentsListLoading(false);
      setErrorMessage('failed to list Documents - please try again later');
      logger.error('error obtaining document list', error);
    }
  };

  useEffect(() => {
    if (isDocumentsListLoading) {
      logger.debug('document list is loading');
      // send in a timeout to avoid blocking rendering
      setTimeout(() => {
        setDocuments([]);
        sendSetDocumentsForPeriod();
      }, 1);
    }
  }, [isDocumentsListLoading]);

  useEffect(() => {
    logger.debug('list period changed', periodsToLoad);
    setIsDocumentsListLoading(true);
  }, [periodsToLoad]);

  const deleteDocuments = async (objectKeys) => {
    try {
      logger.debug('Deleting documents', objectKeys);
      const result = await client.graphql({ query: deleteDocument, variables: { objectKeys } });
      logger.debug('Delete documents result', result);

      // Refresh the document list after deletion
      setIsDocumentsListLoading(true);

      return result.data.deleteDocument;
    } catch (error) {
      setErrorMessage('Failed to delete document(s) - please try again later');
      logger.error('Error deleting documents', error);
      return false;
    }
  };

  const reprocessDocuments = async (objectKeys) => {
    try {
      logger.debug('Reprocessing documents', objectKeys);
      const result = await client.graphql({ query: reprocessDocument, variables: { objectKeys } });
      logger.debug('Reprocess documents result', result);
      // Refresh the document list after reprocessing
      setIsDocumentsListLoading(true);
      return result.data.reprocessDocument;
    } catch (error) {
      setErrorMessage('Failed to reprocess document(s) - please try again later');
      logger.error('Error reprocessing documents', error);
      return false;
    }
  };

  return {
    documents,
    isDocumentsListLoading,
    getDocumentDetailsFromIds,
    setIsDocumentsListLoading,
    setPeriodsToLoad,
    periodsToLoad,
    deleteDocuments,
    reprocessDocuments,
  };
};

export default useGraphQlApi;
