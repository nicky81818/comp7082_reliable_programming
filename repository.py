"""SQLite persistence (corrected version): parameterised SQL, safe connections,
atomic stock reservation and per-user order queries."""
import sqlite3
from contextlib import contextmanager

from models import Product


class InsufficientStock(Exception):
    pass


class StoreRepository:
    def __init__(self, db_path='shop.db'):
        self.db_path = db_path

    def connect(self):
        return sqlite3.connect(self.db_path, timeout=2)

    @contextmanager
    def _conn(self):
        """Commit on success, roll back on error, ALWAYS close."""
        conn = self.connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def get_product(self, sku):
        with self._conn() as conn:
            row = conn.execute('SELECT sku, name, price, stock FROM products WHERE sku = ?', (sku,)).fetchone()
        return Product(*row) if row else None

    def get_saved_cart(self, user_id):
        with self._conn() as conn:
            return conn.execute('SELECT sku, quantity FROM saved_cart WHERE user_id = ?', (user_id,)).fetchall()

    def save_cart(self, user_id, lines):
        with self._conn() as conn:  # delete + inserts are one transaction
            conn.execute('DELETE FROM saved_cart WHERE user_id = ?', (user_id,))
            for line in lines:
                conn.execute('INSERT INTO saved_cart VALUES (?, ?, ?)', (user_id, line.sku, line.quantity))

    def reserve_stock(self, items):
        """Atomically take (sku, qty) pairs out of stock. All or nothing."""
        try:
            with self._conn() as conn:
                for sku, quantity in items:
                    cur = conn.execute(
                        'UPDATE products SET stock = stock - ? WHERE sku = ? AND stock >= ?',
                        (quantity, sku, quantity))
                    if cur.rowcount != 1:
                        raise InsufficientStock(sku)  # rolls back earlier lines too
        except InsufficientStock:
            return False
        return True

    def release_stock(self, items):
        """Put reserved stock back (declined / failed payment)."""
        with self._conn() as conn:
            for sku, quantity in items:
                conn.execute('UPDATE products SET stock = stock + ? WHERE sku = ?', (quantity, sku))

    def save_order(self, user_id, amount, status, request_id):
        with self._conn() as conn:
            cur = conn.execute('INSERT INTO orders(user_id, amount, status, request_id) VALUES (?, ?, ?, ?)',
                               (user_id, amount, status, request_id))
            return cur.lastrowid

    def find_order_by_request(self, user_id, request_id):
        with self._conn() as conn:
            return conn.execute(
                'SELECT id, status, amount FROM orders WHERE user_id = ? AND request_id = ?',
                (user_id, request_id)).fetchone()

    def list_orders(self, user_id):
        with self._conn() as conn:
            return conn.execute(
                'SELECT id, user_id, amount, status FROM orders WHERE user_id = ? ORDER BY id DESC',
                (user_id,)).fetchall()
