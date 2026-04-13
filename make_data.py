# make data py
from __future__ import annotations
import random
import sqlite3
from datetime import datetime, timedelta
from faker import Faker

fake = Faker("es_MX")
random.seed(42)

DB_PATH = "retail_mobile.db"

stores = [
    ("S001", "Urban Click Polanco", "CDMX", 4.8),
    ("S002", "Urban Click Coyoacán", "CDMX", 4.6),
    ("S003", "Urban Click Monterrey Centro", "Monterrey", 4.7),
]

products_catalog = [
    ("P001", "iPhone 15", "smartphone", 18999.0, "pieza"),
    ("P002", "Samsung Galaxy S24", "smartphone", 17499.0, "pieza"),
    ("P003", "Xiaomi Redmi Note 13", "smartphone", 5499.0, "pieza"),
    ("P004", "Audífonos Bluetooth Pro", "audio", 1299.0, "pieza"),
    ("P005", "Cargador USB-C 30W", "accesorios", 499.0, "pieza"),
    ("P006", "Smartwatch Fit X", "wearables", 3299.0, "pieza"),
    ("P007", "Tablet Air 11", "tablet", 11299.0, "pieza"),
    ("P008", "Funda MagSafe Premium", "accesorios", 799.0, "pieza"),
]

order_statuses = ["pending", "confirmed", "shipped", "delivered", "cancelled"]
payment_methods = ["card", "transfer", "cash_on_delivery"]

def create_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.executescript("""
    DROP TABLE IF EXISTS stores;
    DROP TABLE IF EXISTS products;
    DROP TABLE IF EXISTS customers;
    DROP TABLE IF EXISTS orders;

    CREATE TABLE stores (
        store_id TEXT PRIMARY KEY,
        store_name TEXT NOT NULL,
        city TEXT NOT NULL,
        rating REAL NOT NULL
    );

    CREATE TABLE products (
        product_id TEXT PRIMARY KEY,
        store_id TEXT NOT NULL,
        product_name TEXT NOT NULL,
        category TEXT NOT NULL,
        price REAL NOT NULL,
        unit TEXT NOT NULL,
        stock INTEGER NOT NULL,
        promo TEXT NOT NULL,
        rating REAL NOT NULL,
        FOREIGN KEY (store_id) REFERENCES stores(store_id)
    );

    CREATE TABLE customers (
        customer_id TEXT PRIMARY KEY,
        full_name TEXT NOT NULL,
        city TEXT NOT NULL,
        segment TEXT NOT NULL
    );

    CREATE TABLE orders (
        order_id TEXT PRIMARY KEY,
        customer_id TEXT NOT NULL,
        store_id TEXT NOT NULL,
        product_id TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        unit_price REAL NOT NULL,
        total REAL NOT NULL,
        payment_method TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        delivery_type TEXT NOT NULL,
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
        FOREIGN KEY (store_id) REFERENCES stores(store_id),
        FOREIGN KEY (product_id) REFERENCES products(product_id)
    );
    """)

    cur.executemany(
        "INSERT INTO stores VALUES (?, ?, ?, ?)",
        stores
    )

    products = []
    for product_id, name, category, price, unit in products_catalog:
        store = random.choice(stores)
        products.append((
            product_id,
            store[0],
            name,
            category,
            price,
            unit,
            random.randint(8, 120),
            random.choice([
                "Sin promoción",
                "10% de descuento",
                "Envío gratis a partir de $999",
                "12 MSI con tarjeta participante"
            ]),
            round(random.uniform(4.1, 4.9), 1)
        ))

    cur.executemany(
        "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        products
    )

    customers = []
    for i in range(1, 31):
        customers.append((
            f"C{i:03d}",
            fake.name(),
            random.choice(["CDMX", "Monterrey", "Guadalajara", "Puebla"]),
            random.choice(["new", "loyal", "vip"])
        ))

    cur.executemany(
        "INSERT INTO customers VALUES (?, ?, ?, ?)",
        customers
    )

    orders = []
    for i in range(1, 121):
        customer = random.choice(customers)
        product = random.choice(products)
        qty = random.randint(1, 3)
        unit_price = product[4]
        total = round(qty * unit_price, 2)
        created_at = (
            datetime.now() - timedelta(days=random.randint(0, 30),
                                       hours=random.randint(0, 23))
        ).strftime("%Y-%m-%d %H:%M:%S")

        orders.append((
            f"O{i:04d}",
            customer[0],
            product[1],
            product[0],
            qty,
            unit_price,
            total,
            random.choice(payment_methods),
            random.choice(order_statuses),
            created_at,
            random.choice(["home_delivery", "store_pickup"])
        ))

    cur.executemany(
        "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        orders
    )

    conn.commit()
    conn.close()
    print(f"Base creada: {DB_PATH}")

if __name__ == "__main__":
    create_db()