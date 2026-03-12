from scraper_os.domain.registry import action_registry
import scraper_os.actions  # This should trigger registration if __init__.py is set up correctly

print(f"Registered actions: {action_registry.list_actions()}")
