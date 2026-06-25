from fastapi.testclient import TestClient
from main import app


client = TestClient(app)

def test_com_auth():

    response = client.get(
        "/pokemon",
        auth=("admin", "admin")
    )

    assert response.status_code == 200