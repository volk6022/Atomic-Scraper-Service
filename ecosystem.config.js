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
        // q4_0 KV: по sweep'у ±1 tok/s к q8 при ≤90k, но -~600MB VRAM — с
        // draft-моделью на борту q8-KV не влезает (спилл в sysmem → PCIe-крол)
        '-ctk', 'q4_0',
        '-ctv', 'q4_0',
        // 81000 = 27k/слот при np=3: p99 вызовов агента < 24k (компакт-порог 23k),
        // а освободившиеся ~540MB VRAM — запас против WDDM-демоции (см.
        // perf_analysis/ANALYSIS.md §7: клин 2026-06-12, prefill 23 tok/s по PCIe)
        '-c', '81000',
        '-np', '3',
        '-cb',
        '-b', '2048',
        '-ub', '512',
        // Speculative decoding (draft 0.8B, та же дистилляция что 9B-таргет):
        // ВЫКЛЮЧЕН для throughput-прогонов. A/B 2026-06-12 на 3 одновременных
        // reasoning-потоках: без драфта 39-42 tok/s/слот (агрегат ~120, VRAM
        // 6538MiB); с драфтом 19-25 (агрегат ~64, VRAM 7891) при acceptance
        // 0.92-0.97. Драфт ВЫИГРЫВАЕТ только без contention: одиночный поток
        // 56 vs 42 tok/s (+33%) — включать для latency/low-np профилей (np=1-2).
        // '-md', 'C:\\Users\\bhunp\\.lmstudio\\models\\Jackrong\\Qwen3.5-0.8B-Claude-4.6-Opus-Reasoning-Distilled-GGUF\\Qwen3.5-0.8B.Q4_K_M.gguf',
        // '-ngld', '99',
        // '-ctkd', 'q4_0',
        // '-ctvd', 'q4_0',
        // '--spec-draft-n-max', '12',
        // '--spec-draft-n-min', '2',
        // '--spec-draft-p-min', '0.75',
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
