"""Checkout coordinator (corrected version).

Order of operations:
  1. validate request + return the earlier result for a repeated request_id (idempotency)
  2. atomically reserve stock
  3. charge the (simulated) gateway
  4. if not paid -> release the stock; always record the order
  5. clear the cart only when the order was paid
"""
from models import OrderResult


class CheckoutService:
    def __init__(self, repository, payment_gateway):
        self.repository = repository
        self.payment_gateway = payment_gateway

    def checkout(self, cart, payment_token, request_id):
        if not request_id:
            return OrderResult(None, 'invalid_request', 0)

        # Repeated request: return the original outcome, do NOT charge again.
        previous = self.repository.find_order_by_request(cart.user_id, request_id)
        if previous:
            order_id, status, amount = previous
            return OrderResult(order_id, status, amount)

        if len(cart.lines) == 0:
            return OrderResult(None, 'empty', 0)
        if not payment_token:
            return OrderResult(None, 'invalid_payment', 0)

        amount = cart.total()
        if amount <= 0:
            return OrderResult(None, 'invalid_total', amount)

        items = [(line.sku, line.quantity) for line in cart.lines]
        if not self.repository.reserve_stock(items):
            return OrderResult(None, 'out_of_stock', amount)

        try:
            response = self.payment_gateway.charge(amount, payment_token)
            status = 'paid' if response.get('approved') else 'declined'
        except Exception:
            status = 'payment_error'

        if status != 'paid':
            self.repository.release_stock(items)

        order_id = self.repository.save_order(cart.user_id, amount, status, request_id)

        if status == 'paid':
            cart.lines.clear()
            cart.discount_code = None
            cart.save()
        return OrderResult(order_id, status, amount)
