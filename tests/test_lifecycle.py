from unittest.mock import MagicMock
import pytest
from app import create_app
from app.lifecycle import app_lifecycle

@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

def test_stop_route(client):
    # Ensure initially running
    app_lifecycle._lifecycle_flag.set()
    assert app_lifecycle.is_running is True

    mock_exit = MagicMock()
    
    # Ping POST /stop route
    with pytest.MonkeyPatch.context() as mp:
        response = client.post("/stop")
        assert response.status_code == 200
        assert response.json["status"] in ("stopping", "already_stopping")
        assert app_lifecycle.is_running is False

    # Reset lifecycle flag for other tests
    app_lifecycle._lifecycle_flag.set()
