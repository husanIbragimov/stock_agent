import pytest

from uzse_agent.repo import PortfolioRepo
from uzse_agent.storage import Storage


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "agent.db"


@pytest.fixture
def repo(db_path):
    return PortfolioRepo(db_path)


@pytest.fixture
def storage(db_path):
    return Storage(db_path)
