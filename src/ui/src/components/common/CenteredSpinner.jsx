// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React from 'react';
import { Spinner, Box } from '@cloudscape-design/components';

const CenteredSpinner = ({ size = 'large' }) => {
  return (
    <div display="flex" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100%' }}>
      <Spinner size={size} />
    </div>
  );
};

export default CenteredSpinner;
