module.exports = {
  apps: [
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
      args: 'run taskiq worker src.infrastructure.queue.broker:broker src.infrastructure.queue.workers src.infrastructure.queue.session_actor src.infrastructure.queue.cleanup_worker',
      env: {
        NODE_ENV: 'production',
      },
    },
  ],
};