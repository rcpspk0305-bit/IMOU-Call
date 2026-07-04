from unittest.mock import MagicMock
import pytest
from app.lifecycle import app_lifecycle

def test_initiate_stop():
    # Ensure initially running
    app_lifecycle._lifecycle_flag.set()
    assert app_lifecycle.is_running is True

    # Call initiate_stop
    mock_exit = MagicMock()
    res = app_lifecycle.initiate_stop(exit_delay_seconds=0.01, exit_func=mock_exit)
    
    assert res["status"] in ("stopping", "already_stopping")
    assert app_lifecycle.is_running is False

    # Reset lifecycle flag for other tests
    app_lifecycle._lifecycle_flag.set()
