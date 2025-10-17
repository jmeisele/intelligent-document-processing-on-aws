// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import envCompatible from 'vite-plugin-env-compatible';
import svgr from 'vite-plugin-svgr';
import { resolve } from 'path';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react({
      // Use automatic JSX runtime (React 17+)
      jsxRuntime: 'automatic',
      // Include all JavaScript files for JSX transformation
      include: '**/*.{js,jsx,ts,tsx}',
    }),
    // Enable REACT_APP_ prefix for environment variables for backward compatibility
    envCompatible({
      prefix: 'REACT_APP_',
    }),
    // Enable SVG import as React components
    svgr(),
  ],

  // Ensure all .js and .jsx files are treated as JSX
  esbuild: {
    jsx: 'automatic',
  },

  // Development server configuration
  server: {
    port: 3000,
    open: true,
    // Enable CORS for AWS Amplify
    cors: true,
  },

  // Build configuration
  build: {
    outDir: 'build',
    sourcemap: false,
    // Increase chunk size warning limit
    chunkSizeWarningLimit: 500,
    rollupOptions: {
      output: {
        // Manual chunking for better code splitting
        manualChunks: (id) => {
          if (id.includes('node_modules')) {
            if (id.includes('aws-amplify') || id.includes('@aws-amplify')) {
              return 'aws-amplify';
            }
            if (id.includes('@aws-sdk')) {
              return 'aws-sdk';
            }
            if (id.includes('@cloudscape-design')) {
              return 'cloudscape';
            }
            if (id.includes('chart.js') || id.includes('react-chartjs-2')) {
              return 'chart';
            }
            if (id.includes('react') || id.includes('react-dom') || id.includes('react-router')) {
              return 'react-vendor';
            }
            if (id.includes('lodash')) {
              return 'lodash';
            }
            return 'vendor';
          }
          
          if (id.includes('src/components/document-list') || 
              id.includes('src/components/document-details') ||
              id.includes('src/components/document-panel')) {
            return 'documents';
          }
          
          if (id.includes('src/components/configuration-layout') ||
              id.includes('src/components/upload-document') ||
              id.includes('src/components/discovery')) {
            return 'admin';
          }
          
          if (id.includes('src/components/document-kb-query-layout') ||
              id.includes('src/components/document-agents-layout') ||
              id.includes('src/components/agent-chat')) {
            return 'agents';
          }
          
          // Keep navigation/header components in main bundle for instant loading
          if (id.includes('src/components/genai-idp-top-navigation') ||
              id.includes('src/components/genaiidp-layout/navigation') ||
              id.includes('src/components/genaiidp-layout/breadcrumbs')) {
            return undefined; // Don't chunk these - keep in main bundle
          }
        },
      },
    },
    // Configure target to ensure JSX is handled
    target: 'esnext',
  },

  // Resolve configuration
  resolve: {
    alias: {
      '@': resolve(__dirname, './src'),
    },
    // Ensure proper module resolution
    extensions: ['.mjs', '.js', '.jsx', '.json'],
  },

  // Define global constants
  define: {
    // Ensure process.env is available for compatibility
    'process.env': {},
  },

  // Optimize dependencies
  optimizeDeps: {
    include: [
      'react',
      'react-dom',
      'react-router-dom',
      'aws-amplify',
      '@aws-amplify/ui-react',
      '@cloudscape-design/components',
      '@cloudscape-design/global-styles',
    ],
    exclude: ['@aws-sdk/signature-v4-multi-region'],
    esbuildOptions: {
      loader: {
        '.js': 'jsx',
      },
    },
  },

  // CSS configuration
  css: {
    modules: {
      localsConvention: 'camelCase',
    },
  },
});
