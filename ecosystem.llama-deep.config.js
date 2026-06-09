// Workstream D experiment — alternate llama profile: q8_0 KV + smaller ctx.
//
// Rationale (from llm-inference-experiments/ctx_tps_sweep_report.md):
//   - Research active context (last_prompt) is only ~15-30k (p90=29k), NOT 50-120k.
//     We sit in the fast region, so np=3 stays optimal AND q8_0 fits at ≤90k.
//   - q8_0 is +0.3-1.8 tok/s vs q4_0 at ≤90k and better KV quality → may reduce the
//     2/21 empty-card failures. -c 108000 (36k/slot × np3) frees VRAM vs the 195k
//     production config (oversized ~4× vs real footprint).
//
// USE:    pm2 delete llama-server && pm2 start ecosystem.llama-deep.config.js
// REVERT: pm2 delete llama-server && pm2 start ecosystem.config.js --only llama-server
//
// If VRAM OOMs on 8GB (q8_0 × np3 is tight), drop -np to 2 or fall back to q4_0.
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
        '-ctk', 'q8_0',
        '-ctv', 'q8_0',
        '-c', '108000',
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
  ],
};
