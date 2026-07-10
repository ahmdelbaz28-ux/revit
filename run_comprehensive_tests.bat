@echo off
echo Running Comprehensive Button and Backend Connection Tests...
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
echo Starting comprehensive Playwright tests for all buttons and backend connections...
echo.

REM Run the comprehensive Playwright tests
npx playwright test tests/complete-button-backend-test.spec.ts --reporter=html,list

echo.
echo Tests completed! 
echo Check the HTML report in playwright-report/index.html
echo Test results are also available in the test-results directory.
echo.

REM Generate test report
echo Generating detailed test report...
echo Test Report: Comprehensive Button and Backend Connection Tests > TEST_REPORT_GENERATED.md
echo =============================== >> TEST_REPORT_GENERATED.md
echo. >> TEST_REPORT_GENERATED.md
echo Executed on: %DATE% at %TIME% >> TEST_REPORT_GENERATED.md
echo. >> TEST_REPORT_GENERATED.md
echo Results: >> TEST_REPORT_GENERATED.md
type ..\frontend\test-results\*.* 2>nul >> TEST_REPORT_GENERATED.md
if %ERRORLEVEL% NEQ 0 (
    echo Unable to generate detailed test report.
)

echo.
echo Test report generated: TEST_REPORT_GENERATED.md
echo.

pause