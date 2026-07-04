import sys
from unittest.mock import MagicMock

# Create a mock representation of the supabase package
mock_supabase_module = MagicMock()
mock_supabase_module.Client = MagicMock

# Inject the mock package into sys.modules so imports do not raise ModuleNotFoundError
sys.modules['supabase'] = mock_supabase_module
