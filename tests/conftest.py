import pytest

from cart import ShoppingCart
from checkout import CheckoutService
from payments import FakePaymentGateway
from repository import StoreRepository
from setup_db import initialize


@pytest.fixture
def repo(tmp_path):
    """Fresh, isolated SQLite file per test (never touches shop.db)."""
    db = str(tmp_path / 'test.db')
    initialize(db)
    return StoreRepository(db)


@pytest.fixture
def cart(repo):
    return ShoppingCart('alice', repo)


@pytest.fixture
def gateway():
    return FakePaymentGateway()


@pytest.fixture
def service(repo, gateway):
    return CheckoutService(repo, gateway)


def stock(repo, sku):
    return repo.get_product(sku).stock
