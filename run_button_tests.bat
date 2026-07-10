@echo off
echo Running Playwright Button and API Connection Tests...
echo.

REM Change to frontend directory
cd frontend

echo Building the application...
npm run build
if %ERRORLEVEL% NEQ 0 (
    echo Build failed. Exiting.
    pause
    exit /b 1
)

echo.
echo Starting Playwright tests for buttons and API connections...
echo.

REM Run the Playwright tests
npx playwright test tests/button-backend-interactions.spec.ts tests/api-endpoint-validation.spec.ts --reporter=html,list

echo.
echo Tests completed! Check the HTML report in playwright-report/index.html
echo Test results are also available in the test-results directory.
echo.

pause