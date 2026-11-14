from conftest import stock
from cart import ShoppingCart
from checkout import CheckoutService


class ExplodingGateway:
    def __init__(self):
        self.calls = 0

    def charge(self, amount, token):
        self.calls += 1
        raise ConnectionError('gateway down')


def test_empty_cart_returns_empty_and_does_not_charge(service, cart, gateway):
    result = service.checkout(cart, 'TOK', 'req-1')
    assert result.status == 'empty' and result.order_id is None
    assert gateway.calls == []


def test_successful_checkout_charges_discounted_total_and_updates_stock(service, cart, gateway, repo):
    cart.add_item('MOU-01', 2)
    cart.apply_discount('WELCOME10')
    result = service.checkout(cart, 'TOK', 'req-1')
    assert result.status == 'paid' and result.total == 53.91
    assert gateway.calls == [(53.91, 'TOK')]
    assert stock(repo, 'MOU-01') == 18
    assert cart.lines == [] and cart.discount_code is None
    assert repo.list_orders('alice')[0][3] == 'paid'


def test_declined_payment_restores_stock_and_keeps_cart(repo, cart):
    from payments import FakePaymentGateway
    service = CheckoutService(repo, FakePaymentGateway(should_approve=False))
    cart.add_item('MOU-01', 2)
    result = service.checkout(cart, 'TOK', 'req-1')
    assert result.status == 'declined'
    assert stock(repo, 'MOU-01') == 20       # not decremented
    assert len(cart.lines) == 1              # user keeps their cart


def test_gateway_exception_is_handled_and_stock_restored(repo, cart):
    gw = ExplodingGateway()
    service = CheckoutService(repo, gw)
    cart.add_item('LAP-01', 1)
    result = service.checkout(cart, 'TOK', 'req-1')
    assert result.status == 'payment_error'
    assert stock(repo, 'LAP-01') == 5
    assert len(cart.lines) == 1


def test_repeated_request_id_does_not_charge_or_decrement_twice(service, cart, gateway, repo):
    cart.add_item('MOU-01', 2)
    first = service.checkout(cart, 'TOK', 'req-1')
    second = service.checkout(cart, 'TOK', 'req-1')  # e.g. double click / retry
    assert second == first
    assert len(gateway.calls) == 1
    assert stock(repo, 'MOU-01') == 18
    assert len(repo.list_orders('alice')) == 1


def test_missing_request_id_is_rejected(service, cart, gateway):
    cart.add_item('MOU-01', 1)
    assert service.checkout(cart, 'TOK', None).status == 'invalid_request'
    assert service.checkout(cart, 'TOK', '').status == 'invalid_request'
    assert gateway.calls == []


def test_stock_changed_after_adding_to_cart_blocks_checkout(service, cart, gateway, repo):
    cart.add_item('LAP-01', 3)
    other = ShoppingCart('bob', repo)
    other.add_item('LAP-01', 4)
    assert service.checkout(other, 'TOK', 'bob-1').status == 'paid'  # only 1 laptop left
    result = service.checkout(cart, 'TOK', 'req-1')
    assert result.status == 'out_of_stock'
    assert stock(repo, 'LAP-01') == 1
    assert len(gateway.calls) == 1  # alice was never charged


def test_multi_line_reservation_is_all_or_nothing(service, cart, repo):
    cart.add_item('USB-01', 2)
    cart.add_item('LAP-01', 2)
    repo_conn = repo.connect()
    repo_conn.execute("UPDATE products SET stock = 1 WHERE sku = 'LAP-01'")  # sold elsewhere
    repo_conn.commit(); repo_conn.close()
    assert service.checkout(cart, 'TOK', 'req-1').status == 'out_of_stock'
    assert stock(repo, 'USB-01') == 50  # first line rolled back


def test_zero_total_is_not_charged(service, cart, gateway):
    cart.add_item('USB-01', 1)
    cart.apply_discount('SAVE15')
    assert service.checkout(cart, 'TOK', 'req-1').status == 'invalid_total'
    assert gateway.calls == []


def test_orders_are_listed_per_user_only(service, repo):
    for user, req in [('alice', 'a1'), ('bob', 'b1')]:
        c = ShoppingCart(user, repo)
        c.add_item('USB-01', 1)
        service.checkout(c, 'TOK', req)
    assert [o[1] for o in repo.list_orders('alice')] == ['alice']
    assert [o[1] for o in repo.list_orders('bob')] == ['bob']


def test_payment_token_is_not_printed(service, cart, capsys):
    cart.add_item('USB-01', 1)
    service.checkout(cart, 'SECRET-TOKEN-123', 'req-1')
    out = capsys.readouterr()
    assert 'SECRET-TOKEN-123' not in out.out + out.err
