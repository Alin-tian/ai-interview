import pytest
from app.utils.security import validate_public_url


def test_reject_private_url():
    with pytest.raises(ValueError):
        validate_public_url("http://127.0.0.1:8000/private")
