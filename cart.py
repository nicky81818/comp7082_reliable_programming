"""Shopping cart business logic (corrected version).

Money is calculated with Decimal and rounded to cents (ROUND_HALF_UP).
The discounted total is always *derived* from the current lines + the
selected coupon, so it can never become stale or be stacked.
"""
from decimal import Decimal, ROUND_HALF_UP

from models import CartLine

CENT = Decimal('0.01')

# code -> ('percent', rate_off) | ('fixed', amount_off) | ('none', 0)
DISCOUNTS = {
    'WELCOME10': ('percent', Decimal('0.10')),
    'STUDENT20': ('percent', Decimal('0.20')),
    'SAVE15': ('fixed', Decimal('15.00')),
    'FREESHIP': ('none', Decimal('0')),  # no shipping charge exists in this app
}


def money(value):
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def _valid_quantity(quantity):
    return isinstance(quantity, int) and not isinstance(quantity, bool) and quantity > 0


class ShoppingCart:
    def __init__(self, user_id, repository):
        self.user_id = user_id
        self.repository = repository
        self.lines = []
        self.discount_code = None

    def add_item(self, sku, quantity):
        if not _valid_quantity(quantity):
            return False
        product = self.repository.get_product(sku)
        if not product:
            return False
        existing = next((x for x in self.lines if x.sku == sku), None)
        already = existing.quantity if existing else 0
        if product.stock < already + quantity:  # count what is already in the cart
            return False
        if existing:
            existing.quantity += quantity
        else:
            self.lines.append(CartLine(sku, product.name, product.price, quantity))
        return True

    def remove_item(self, sku, quantity=None):
        if quantity is not None and not _valid_quantity(quantity):
            return False
        line = next((x for x in self.lines if x.sku == sku), None)
        if line is None:
            return False
        if quantity is None or quantity >= line.quantity:
            self.lines.remove(line)
        else:
            line.quantity -= quantity
        return True

    def subtotal(self):
        return float(sum((money(l.unit_price) * l.quantity for l in self.lines), Decimal('0')))

    def total(self):
        sub = Decimal(str(self.subtotal()))
        kind, value = DISCOUNTS.get(self.discount_code, ('none', Decimal('0')))
        if kind == 'percent':
            sub = sub * (1 - value)
        elif kind == 'fixed':
            sub = sub - value
        return float(max(money(sub), Decimal('0.00')))  # never negative

    def apply_discount(self, code):
        """Set (replace) the coupon. Coupons never stack."""
        if code not in DISCOUNTS:
            return False
        self.discount_code = code
        return True

    def load(self):
        """Replace the cart contents with the saved cart (idempotent)."""
        self.lines = []
        for sku, quantity in self.repository.get_saved_cart(self.user_id):
            self.add_item(sku, quantity)

    def save(self):
        self.repository.save_cart(self.user_id, self.lines)
