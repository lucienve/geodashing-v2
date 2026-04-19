const { execSync } = require('child_process');
const path = require('path');

module.exports = async (_config) => {
    console.log('\n--- Playwright Global Setup ---');
    console.log('Synchronizing E2E Test Database...');
    
    // Resolve path securely against repository root (which is parent of e2e/)
    const scriptPath = path.resolve(__dirname, 'setup-test-db.sh');

    try {
        // Execute the native shell script to bootstrap test schema and prevent divergence
        // Setting stdio: 'inherit' routes the output visually for the developer
        execSync(`bash "${scriptPath}"`, { stdio: 'inherit' });
        console.log('Database synchronization complete!\n');
    } catch (error) {
        console.error('\nERROR: Failed to initialize E2E test database!');
        console.error('Ensure that the "geodashing_test" database exists in your local MySQL instance.');
        throw error;
    }
};
