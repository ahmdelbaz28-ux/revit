#!/bin/bash

echo "Setting up UI and API integration tests..."

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "Node.js is not installed. Please install Node.js before continuing."
    exit 1
fi

echo "Installing dependencies..."
npm install

echo ""
echo "Dependencies installed successfully!"

echo ""
echo "To run UI tests with Puppeteer, use:"
echo "  npm run test:ui"
echo ""
echo "To run all tests, use:"
echo "  npm run test:all"
echo ""
echo "Before running tests, make sure to set environment variables:"
echo "  export BASE_URL=http://localhost:3000"
echo "  export API_URL=http://localhost:8000"
echo "  export API_KEY=your-api-key-here"
echo ""