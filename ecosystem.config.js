module.exports = {
  apps: [
    {
      name: 'llama-server',
      script: 'C:\\Users\\bhunp\\work-software\\llama-cpp\\llama-server.exe',
      args: [
        '-m', 'C:\\Users\\bhunp\\.lmstudio\\models\\Jackrong\\Qwen3.5-9B-Claude-4.6-Opus-Reasoning-Distilled-GGUF\\Qwen3.5-9B.Q4_K_S.gguf',
        '--host', '0.0.0.0',
        '--port', '20022',
        '-ngl', '99',
        '-fa', 'on',
        '-ctk', 'q4_0',
        '-ctv', 'q4_0',
        '-c', '195000',
        '-np', '3',
        '-cb',
        '-b', '2048',
        '-ub', '512',
        '--metrics',
      ].join(' '),
      interpreter: 'none',
      autorestart: true,
      max_restarts: 5,
      env: {
        NODE_ENV: 'production',
      },
    },
    {
      name: 'scraper-api',
      script: 'uv',
      args: 'run python -m src.api.main',
      env: {
        NODE_ENV: 'production',
      },
    },
    {
      name: 'taskiq-worker',
      script: 'uv',
      args: 'run taskiq worker --workers 4 src.infrastructure.queue.broker:broker src.infrastructure.queue.workers src.infrastructure.queue.session_actor src.infrastructure.queue.cleanup_worker src.infrastructure.queue.research_task',
      env: {
        NODE_ENV: 'production',
      },
    },
  ],
};
