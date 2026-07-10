@echo off
echo Setting up UI and API integration tests...

REM Check if Node.js is installed
node --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Node.js is not installed. Please install Node.js before continuing.
    pause
    exit /b 1
)

echo Installing dependencies...
npm install

echo.
echo Dependencies installed successfully!

echo.
echo To run UI tests with Puppeteer, use:
echo   npm run test:ui
echo.
echo To run all tests, use:
echo   npm run test:all
echo.
echo Before running tests, make sure to set environment variables:
echo   set BASE_URL=http://localhost:3000
echo   set API_URL=http://localhost:8000
echo   set API_KEY=your-api-key-here
echo.
echo Press any key to close this window...
pause >nul