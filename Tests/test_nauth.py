from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_sem_auth():

    response = client.get("/pokemon")

    assert response.status_code == 401