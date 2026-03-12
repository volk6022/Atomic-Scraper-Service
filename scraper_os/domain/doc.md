# Domain Layer

Contains business logic abstractions, data models, and the central action registry.

## Components
- `models/`: 
    - `requests.py`: Input schemas for API endpoints.
    - `dsl.py`: Schema for action results, commands, and LLM decisions.
- `registry/`: 
    - `action_registry.py`: Implements the Registry pattern to map strings to action classes.
