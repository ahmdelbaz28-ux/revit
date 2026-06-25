// Global setup - runs once before all tests
process.env.NODE_ENV = 'test';
process.env.JWT_SECRET = 'test-secret';
process.env.JWT_EXPIRES_IN = '7d';
process.env.DATABASE_URL = 'file:./dev.db';

// Kill any process on port 3001
const { execSync } = require('child_process');
try {
  execSync('fuser -k 3001/tcp 2>/dev/null || true');
} catch (e) {
  // Ignore errors
}

module.exports = async () => {
  // Setup complete
};