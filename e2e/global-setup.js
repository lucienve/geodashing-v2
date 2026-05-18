const { execSync } = require('child_process');
const path = require('path');

module.exports = async (_config) => {
    console.log('\n--- Playwright Global Setup ---');

    if (!process.env.CI) {
        console.log('Local environment detected: Starting Docker containers...');
        try {
            const composePath = path.resolve(__dirname, 'docker-compose.yml');
            try {
                // Prioritize modern Docker Compose V2 (plugin)
                execSync(`docker compose -f "${composePath}" up -d`, { stdio: 'inherit' });
            } catch (v2Error) {
                // Fallback to legacy Docker Compose V1 (standalone) for older developer environments
                console.log('Falling back to legacy docker-compose (v1)...');
                execSync(`docker-compose -f "${composePath}" up -d`, { stdio: 'inherit' });
            }
        } catch (error) {
            console.error('\nERROR: Failed to start Docker containers!');
            throw error;
        }
    }

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
