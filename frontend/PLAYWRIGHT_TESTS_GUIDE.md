# Playwright Button and API Connection Tests Guide

This guide explains how to run the comprehensive Playwright tests that validate all UI buttons and their corresponding backend API connections in the CAD/BIM Integration Platform.

## Overview

The testing suite includes two main types of tests:

1. **Button Interaction Tests** (`tests/button-backend-interactions.spec.ts`): Tests all UI buttons across different pages and validates their functionality
2. **API Endpoint Validation Tests** (`tests/api-endpoint-validation.spec.ts`): Specifically validates that button clicks trigger the correct API endpoints with proper responses

## Prerequisites

Before running the tests, ensure you have:

- Node.js 18+ installed
- The frontend application built and running
- Backend API server running on the expected port (typically `http://localhost:8000`)
- Valid API key for authentication (set as environment variable)

## Setup

### 1. Install Dependencies

```bash
cd frontend
npm install
```

### 2. Environment Variables

Create a `.env` file in the frontend directory with the following variables:

```env
API_URL=http://localhost:8000
API_KEY=your-api-key-here
```

Alternatively, you can set them when running the tests:

```bash
API_URL=http://localhost:8000 API_KEY=your-api-key-here npm run test:visual
```

### 3. Build the Application

```bash
npm run build
```

## Running Tests

### 1. Run All Button and API Tests

```bash
npm run test:visual
```

This will run all Playwright tests including the new button and API connection tests.

### 2. Run Specific Test Files

To run only the button interaction tests:

```bash
npx playwright test tests/button-backend-interactions.spec.ts
```

To run only the API validation tests:

```bash
npx playwright test tests/api-endpoint-validation.spec.ts
```

### 3. Run Tests with UI Mode

To run tests in interactive UI mode:

```bash
npm run test:visual:ui
```

### 4. Generate Updated Snapshots

If you're adding new visual tests and need to update snapshots:

```bash
npm run test:visual:update
```

## Test Structure

### Button Interaction Tests

These tests cover:

- **Dashboard Page**: Refresh buttons, quick action buttons
- **Projects Page**: Create, edit, delete, and view project buttons
- **AutoCAD Page**: Connect, upload, and drawing operation buttons
- **Revit Page**: Connect, upload, and element creation buttons
- **Digital Twin Page**: Conversion, configuration, and history buttons
- **Elements Page**: Filter, search, and element operation buttons
- **Connections Page**: Create, validate, and sync connection buttons
- **Conflicts Page**: Check and resolve conflict buttons
- **Reports Page**: Generate and export report buttons
- **Settings Page**: Save and test connection buttons

### API Endpoint Validation Tests

These tests specifically validate:

- Correct API endpoints are called when buttons are clicked
- Proper HTTP methods are used (GET, POST, PUT, DELETE)
- Expected status codes are returned (200-299 for successful operations)
- API responses contain expected data structures
- Error handling works correctly

## Test Reports

After running tests, you'll find:

1. **HTML Report**: Located in `frontend/playwright-report/` - open `index.html` in a browser
2. **Test Results**: Located in `frontend/test-results/`
3. **Console Output**: Shows detailed test results with response times and status codes

## Available Commands

| Command | Description |
|--------|-------------|
| `npm run test:visual` | Run all visual tests including button and API tests |
| `npm run test:visual:ui` | Run tests in interactive UI mode |
| `npm run test:visual:update` | Update test snapshots |
| `npx playwright show-report` | Show the HTML report |

## Configuration

The tests use the Playwright configuration in `playwright.config.ts` which:

- Runs tests against the built application on port 4173
- Uses Chromium browser by default
- Captures traces and screenshots for failed tests
- Sets a standard viewport size (1280x720)

## Extending Tests

To add new button tests:

1. Add new test cases to `tests/button-backend-interactions.spec.ts`
2. Use the existing patterns for intercepting API calls and validating responses
3. Follow the same structure for logging test results

To add new API validation tests:

1. Add new test cases to `tests/api-endpoint-validation.spec.ts`
2. Use the `page.waitForResponse()` pattern to validate API calls
3. Ensure proper assertions for status codes and response content

## Troubleshooting

### Common Issues

1. **Tests failing due to API unavailability**: Ensure the backend server is running and accessible
2. **Timeout errors**: Increase the timeout values in the test configuration
3. **Element not found errors**: Update selectors if the UI has changed

### Debugging Tips

1. Run tests in UI mode (`npm run test:visual:ui`) to visually see what's happening
2. Check the generated HTML report for detailed failure information
3. Look at captured screenshots and traces in the test-results directory
4. Add temporary console.log statements to track API call details

## Continuous Integration

These tests are designed to work in CI/CD environments and will automatically run as part of the build pipeline, generating reports that can be archived as build artifacts.