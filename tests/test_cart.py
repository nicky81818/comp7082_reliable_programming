import pytest

from cart import ShoppingCart


# ---- quantities / adding / removing -------------------------------------
@pytest.mark.parametrize('qty', [0, -1, 1.5, '2', None, True])
def test_add_item_rejects_invalid_quantity(cart, qty):
    assert cart.add_item('MOU-01', qty) is False
    assert cart.lines == []


def test_add_item_unknown_sku(cart):
    assert cart.add_item('NOPE', 1) is False


def test_add_duplicate_product_merges_into_one_line(cart):
    cart.add_item('MOU-01', 2)
    cart.add_item('MOU-01', 3)
    assert len(cart.lines) == 1 and cart.lines[0].quantity == 5


def test_stock_limit_counts_quantity_already_in_cart(cart):
    assert cart.add_item('LAP-01', 3) is True
    assert cart.add_item('LAP-01', 3) is False  # 3 + 3 > stock of 5
    assert cart.lines[0].quantity == 3


def test_stock_boundary_exact_stock_is_allowed(cart):
    assert cart.add_item('LAP-01', 5) is True


def test_sql_injection_in_sku_is_treated_as_plain_text(cart):
    assert cart.add_item("x' OR '1'='1", 1) is False


def test_remove_partial_and_full(cart):
    cart.add_item('MOU-01', 5)
    assert cart.remove_item('MOU-01', 2) is True
    assert cart.lines[0].quantity == 3
    assert cart.remove_item('MOU-01') is True
    assert cart.lines == []


def test_remove_missing_or_invalid_quantity(cart):
    cart.add_item('MOU-01', 2)
    assert cart.remove_item('USB-01') is False
    assert cart.remove_item('MOU-01', -3) is False
    assert cart.remove_item('MOU-01', 0) is False
    assert cart.lines[0].quantity == 2


# ---- money / discounts --------------------------------------------------
def test_subtotal_is_rounded_to_cents(cart):
    cart.add_item('MOU-01', 3)  # 3 * 29.95
    assert cart.subtotal() == 89.85


@pytest.mark.parametrize('code,expected', [
    ('WELCOME10', 80.87),   # 89.85 * 0.9 = 80.865 -> half-up
    ('STUDENT20', 71.88),
    ('SAVE15', 74.85),
    ('FREESHIP', 89.85),
])
def test_discount_totals(cart, code, expected):
    cart.add_item('MOU-01', 3)
    assert cart.apply_discount(code) is True
    assert cart.total() == expected


def test_invalid_coupon_rejected_and_total_unchanged(cart):
    cart.add_item('MOU-01', 1)
    assert cart.apply_discount('BOGUS') is False
    assert cart.discount_code is None
    assert cart.total() == 29.95


def test_discounts_do_not_stack(cart):
    cart.add_item('MOU-01', 3)
    cart.apply_discount('WELCOME10')
    cart.apply_discount('WELCOME10')
    assert cart.total() == 80.87  # not 0.9 * 0.9


def test_fixed_discount_never_makes_total_negative(cart):
    cart.add_item('USB-01', 1)  # 9.99 < 15
    cart.apply_discount('SAVE15')
    assert cart.total() == 0.0


def test_discount_is_recalculated_after_cart_edit(cart):
    cart.add_item('MOU-01', 2)
    cart.apply_discount('STUDENT20')
    assert cart.total() == 47.92  # 59.90 * 0.8
    cart.add_item('MOU-01', 1)
    assert cart.total() == 71.88  # no stale discounted total
    cart.remove_item('MOU-01', 2)
    assert cart.total() == 23.96


# ---- saved cart ---------------------------------------------------------
def test_save_and_load_roundtrip(repo):
    c1 = ShoppingCart('bob', repo)
    c1.add_item('MOU-01', 2)
    c1.add_item('USB-01', 1)
    c1.save()
    c2 = ShoppingCart('bob', repo)
    c2.load()
    assert {(l.sku, l.quantity) for l in c2.lines} == {('MOU-01', 2), ('USB-01', 1)}


def test_repeated_load_does_not_double_quantities(repo):
    c1 = ShoppingCart('bob', repo)
    c1.add_item('MOU-01', 2)
    c1.save()
    c2 = ShoppingCart('bob', repo)
    c2.load()
    c2.load()
    assert c2.lines[0].quantity == 2


def test_saved_carts_are_per_user(repo):
    a = ShoppingCart('alice', repo)
    a.add_item('MOU-01', 1)
    a.save()
    b = ShoppingCart('bob', repo)
    b.load()
    assert b.lines == []
