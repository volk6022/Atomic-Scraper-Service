# Infrastructure Layer

Handles external integrations, resource management, and asynchronous task execution.

## Subdirectories
- `browser/`: 
    - `pool_manager.py`: Singleton for stateless browser pool.
    - `session_manager.py`: Individual browser manager for stateful actors.
- `llm/`: 
    - `facade.py`: Unified AI interface.
    - `openai_client.py`, `jina_client.py`: Specific service integrations.
- `queue/`: 
    - `broker.py`: Taskiq + Redis configuration.
    - `pool_workers.py`: Workers for stateless Circuit A.
    - `actor_workers.py`: Workers for stateful Circuit B (the Actor Model).
