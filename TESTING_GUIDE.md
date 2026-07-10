# UI and API Integration Testing Guide

This guide provides instructions for testing the CAD/BIM Integration Platform using both Postman for API testing and Puppeteer for UI simulation with corresponding API requests.

## Table of Contents
1. [Overview](#overview)
2. [Postman Collection Setup](#postman-collection-setup)
3. [Puppeteer UI Testing Setup](#puppeteer-ui-testing-setup)
4. [Running Tests](#running-tests)
5. [Test Report Generation](#test-report-generation)
6. [Troubleshooting](#troubleshooting)

## Overview

The testing suite consists of two main components:

1. **Postman Collection**: Comprehensive API testing for all endpoints in the CAD/BIM Integration Platform
2. **Puppeteer Script**: UI interaction simulation that clicks buttons and makes corresponding API requests

Both tools work together to provide complete coverage of the application's functionality.

## Postman Collection Setup

### Prerequisites
- Install [Postman](https://www.postman.com/downloads/)
- Or install [Newman](https://github.com/postmanlabs/newman) for command-line execution

### Importing the Collection
1. Open Postman
2. Go to **Collections** tab
3. Click **Import**
4. Select the `API_Test_Collection.postman_collection.json` file
5. The collection will be imported with all API endpoints organized by category

### Setting Up Environment Variables
1. Create a new environment in Postman
2. Add the following variables:
   - `baseUrl`: Your API base URL (e.g., `http://localhost:8000`)
   - `apiKey`: Your API key for authentication
   - `username`: Test user username
   - `password`: Test user password

### Running Tests in Postman
1. Select your environment
2. Choose the CAD/BIM Integration Platform collection
3. Click **Runner** to run all tests
4. Or select individual requests to run specific tests

### Running Tests with Newman (Command Line)
```bash
# Install Newman globally if not already installed
npm install -g newman

# Run the collection
newman run API_Test_Collection.postman_collection.json -e your-environment.json
```

## Puppeteer UI Testing Setup

### Prerequisites
- Node.js 16 or higher
- npm or yarn package manager

### Installation
```bash
# Install dependencies
npm install

# Puppeteer will automatically download a Chromium binary
```

### Configuration
The Puppeteer script uses environment variables for configuration:

```bash
# Set environment variables
export BASE_URL=http://localhost:3000      # Frontend URL
export API_URL=http://localhost:8000       # Backend API URL
export API_KEY=your-api-key-here          # API authentication key
export USERNAME=test-user                 # Test username
export PASSWORD=test-password             # Test password
```

Or create a `.env` file in the project root:

```env
BASE_URL=http://localhost:3000
API_URL=http://localhost:8000
API_KEY=your-api-key-here
USERNAME=test-user
PASSWORD=test-password
```

### Available Scripts

```bash
# Run UI tests with Puppeteer
npm run test:ui

# Run all tests (UI and API)
npm run test:all
```

## Running Tests

### Postman API Tests
The collection includes tests for:

#### Health Checks
- `/api/health` - Overall system health
- `/api/health/statistics` - System statistics

#### Authentication
- `/api/v1/auth/me` - Get current user info
- `/api/v1/auth/session/login` - Session login

#### Projects
- `/api/v1/projects` - List and create projects

#### AutoCAD Integration
- `/api/v1/autocad/connect` - Connect to AutoCAD
- `/api/v1/autocad/documents` - Get documents
- `/api/v1/autocad/upload` - Upload DWG files

#### Revit Integration
- `/api/v1/revit/connect` - Connect to Revit
- `/api/v1/revit/elements` - Get Revit elements
- `/api/v1/revit/upload` - Upload RVT files

#### Digital Twin
- `/api/v1/digital-twin/convert` - Convert CAD files
- `/api/v1/digital-twin/history` - Get conversion history

#### Devices & Elements
- `/api/v1/devices` - List devices
- `/api/v1/elements` - List elements

#### Connections & Conflicts
- `/api/v1/connections` - List connections
- `/api/v1/conflicts` - Check conflicts

#### Reports & Exports
- `/api/v1/reports/generate` - Generate reports
- `/api/v1/exports` - Export data

#### Monitoring
- `/api/v1/monitor/metrics` - Get metrics
- `/api/v1/monitor/health` - System health

### Puppeteer UI Tests
The Puppeteer script simulates user interactions with the UI and makes corresponding API requests:

1. **Dashboard Page**
   - Loads dashboard statistics
   - Retrieves recent projects

2. **Projects Page**
   - Creates new projects
   - Lists existing projects

3. **AutoCAD Page**
   - Connects to AutoCAD
   - Loads AutoCAD documents

4. **Revit Page**
   - Connects to Revit
   - Loads Revit elements

5. **Digital Twin Page**
   - Initiates conversions
   - Loads conversion history

6. **Elements Page**
   - Lists elements

7. **Connections Page**
   - Lists connections

8. **Conflicts Page**
   - Checks for conflicts

9. **Reports Page**
   - Generates reports

## Test Report Generation

### Postman Reports
Postman generates detailed reports showing:
- Response times
- Status codes
- Response bodies
- Assertion results
- Error details

### Puppeteer Reports
The Puppeteer script generates two types of reports:

1. **Markdown Report** (`test_report.md`)
   - Human-readable test results
   - Summary statistics
   - Individual test details
   - Failed test analysis

2. **JSON Report** (`test_report.json`)
   - Structured data for CI/CD pipelines
   - Programmatic analysis
   - Detailed timing information

Example report structure:
```json
{
  "startTime": "2023-01-01T00:00:00.000Z",
  "endTime": "2023-01-01T00:05:00.000Z",
  "results": [
    {
      "testName": "Connect AutoCAD Button",
      "action": "Click connect AutoCAD button",
      "timestamp": "2023-01-01T00:01:00.000Z",
      "status": 200,
      "duration": 125,
      "details": {
        "response": {},
        "headers": {}
      }
    }
  ],
  "summary": {
    "totalTests": 10,
    "passedTests": 9,
    "failedTests": 1,
    "totalTime": 300000
  }
}
```

## Troubleshooting

### Common Issues

#### Puppeteer Connection Issues
- Ensure the frontend application is running at the configured `BASE_URL`
- Verify the backend API is running at the configured `API_URL`
- Check that the API key is valid and has appropriate permissions

#### Postman Authentication Errors
- Verify the API key is correct
- Ensure the user account has necessary permissions
- Check that authentication endpoints are accessible

#### Timeout Errors
- Increase timeout values in the Puppeteer script
- Verify network connectivity to the application
- Check if the application is responding slowly due to high load

#### Element Not Found Errors (Puppeteer)
- Update selectors if the UI has changed
- Add waits for dynamic content to load
- Verify the application is rendering correctly

### Debugging Tips

#### Enable Verbose Logging
Add debug flags to get more detailed information:

```javascript
// In the Puppeteer script
await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'dark' }]);
await page.evaluateOnNewDocument(() => {
  Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
});
```

#### Monitor Network Requests
```javascript
page.on('response', response => {
  console.log(`${response.status()} ${response.url()}`);
});
```

## Best Practices

1. **Environment Consistency**: Use consistent environment variables across local, staging, and production testing
2. **Data Isolation**: Use test-specific data that won't interfere with production data
3. **Authentication Management**: Implement proper token refresh mechanisms for long-running tests
4. **Error Handling**: Implement robust error handling to prevent cascading failures
5. **Performance Monitoring**: Track response times and performance metrics
6. **Regular Maintenance**: Update tests regularly as the API evolves

## Continuous Integration

To integrate these tests into your CI pipeline:

```yaml
# Example GitHub Actions workflow
name: API and UI Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18'
      - name: Install dependencies
        run: npm install
      - name: Run Puppeteer tests
        run: npm run test:ui
        env:
          BASE_URL: ${{ secrets.BASE_URL }}
          API_URL: ${{ secrets.API_URL }}
          API_KEY: ${{ secrets.API_KEY }}
      - name: Archive test reports
        uses: actions/upload-artifact@v3
        with:
          name: test-reports
          path: test_report.*
```

This testing approach ensures comprehensive coverage of your CAD/BIM Integration Platform, combining the reliability of API testing with the realism of UI simulation.