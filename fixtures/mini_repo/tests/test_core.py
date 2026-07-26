from app.core import boot


def test_boot():
    assert boot() == "ok"
