import pytest
from flask import Flask
from app import app, db, User


@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'  # Használj memória-alapú SQLite DB-t teszteléshez

    with app.app_context():
        db.create_all()
        # Előzetes felhasználó létrehozása tesztelés céljából
        user = User(username="testuser", is_admin=False)
        user.set_password("testpass")
        db.session.add(user)
        db.session.commit()

    client = app.test_client()

    yield client

    with app.app_context():
        db.drop_all()


def test_register(client):
    response = client.post('/register', data=dict(
        username="testuser",
        password="testpass",
        is_admin=False
    ), follow_redirects=True)
    assert response.status_code == 200
    assert b"login" in response.data


def test_login(client):
    # Bejelentkezési kísérlet
    response = client.post('/login', data=dict(
        username="testuser",
        password="testpass"
    ), follow_redirects=True)
    
    assert response.status_code == 200
    assert b"testuser" in response.data  # Ellenőrizzük, hogy a felhasználói név megjelenik-e a válaszban


def test_logout(client):
    response = client.get('/logout', follow_redirects=True)
    assert response.status_code == 200
    assert b"login" in response.data
