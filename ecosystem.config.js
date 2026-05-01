module.exports = {
  apps: [
    {
      name: 'cryptominds-web',
      script: 'web/server_modular.js',
      env: { PORT: 3457, PYTHON_API_URL: 'http://localhost:3458' },
    },
    {
      name: 'cryptominds-python',
      script: 'api_server.py',
      interpreter: 'python3',
      env: { CRYPTOMINDS_API_PORT: 3458 },
    },
    {
      name: 'agent-tiedan',
      script: 'agents/agent_server.py',
      interpreter: 'python3',
      args: '--agent tiedan --port 5001',
      env: { CRYPTOMINDS_DEMO: '0' },
    },
    {
      name: 'agent-choudan',
      script: 'agents/agent_server.py',
      interpreter: 'python3',
      args: '--agent choudan --port 5002',
      env: { CRYPTOMINDS_DEMO: '0' },
    },
    {
      name: 'agent-ludan',
      script: 'agents/agent_server.py',
      interpreter: 'python3',
      args: '--agent ludan --port 5003',
      env: { CRYPTOMINDS_DEMO: '0' },
    },
    {
      name: 'agent-four-meme',
      script: 'agents/agent_server.py',
      interpreter: 'python3',
      args: '--agent four_meme --port 5004',
      env: { CRYPTOMINDS_DEMO: '0' },
    },
  ],
};