from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_add_pokemon():

    response = client.post(
        "/add",
        auth=("admin", "admin"),
        json={
            "pokemon_name": "TesteMon",
            "pokemon_level": 99,
            "pokemon_typing": "normal"
        }
    )

    assert response.status_code in [200, 400]


def test_get_pokemon():

    response = client.get(
        "/pokemon",
        auth=("admin", "admin")
    )

    assert response.status_code == 200

    data = response.json()

    assert "pokemon" in data