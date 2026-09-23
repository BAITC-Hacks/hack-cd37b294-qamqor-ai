import pytest
from app.catalog.loader import checked_dataset


@pytest.fixture
def dataset():
    return checked_dataset()
