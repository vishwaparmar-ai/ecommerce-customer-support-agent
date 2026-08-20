"""
Seed script for the customer-support-agent database.

Run from the project root:
    uv run python -m backend.scripts.seed_data

Generates:
    - Customers
    - Products
    - Orders (+ OrderItems)
    - Payments (mostly paid, some FAILED)
    - Shipments (mostly on-time, some DELAYED / LOST)
    - Returns (some COMPLETED, some REJECTED as "expired")
    - Refunds (tied to completed/approved returns)
    - SupportTickets (some order-linked, some general)
"""

import random
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from faker import Faker

from backend.db.session import SessionLocal
from backend.db.models import (
    Customer,
    Product,
    Order,
    OrderStatus,
    OrderItem,
    Payment,
    PaymentStatus,
    PaymentMethod,
    Shipment,
    ShipmentStatus,
    Return,
    ReturnStatus,
    Refund,
    RefundStatus,
    SupportTicket,
    TicketPriority,
    TicketStatus,
)
from backend.core.security import hash_password  # rename if your function differs

fake = Faker("en_IN")
random.seed(42)
Faker.seed(42)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
NUM_CUSTOMERS = 50
NUM_PRODUCTS = 40
MAX_ORDERS_PER_CUSTOMER = 5

PRODUCT_CATEGORIES = [
    "Electronics", "Clothing", "Home & Kitchen", "Books",
    "Sports & Fitness", "Beauty", "Toys", "Grocery",
]

CARRIERS = ["BlueDart", "Delhivery", "Ekart", "DTDC", "India Post"]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------
def seed_customers(db, n=NUM_CUSTOMERS) -> list[Customer]:
    customers = []
    for _ in range(n):
        c = Customer(
            id=uuid.uuid4(),
            name=fake.name(),
            email=fake.unique.email(),
            password_hash=hash_password("Password123!"),
            phone=fake.phone_number()[:20],
            is_active=random.random() > 0.05,  # ~5% inactive accounts
        )
        db.add(c)
        customers.append(c)
    db.flush()
    return customers


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------
def seed_products(db, n=NUM_PRODUCTS) -> list[Product]:
    products = []
    for _ in range(n):
        p = Product(
            id=uuid.uuid4(),
            name=fake.catch_phrase(),
            description=fake.text(max_nb_chars=150),
            category=random.choice(PRODUCT_CATEGORIES),
            price=Decimal(random.randrange(199, 49999)) / Decimal(1),
            stock_quantity=random.randint(0, 500),
            is_active=random.random() > 0.1,
        )
        db.add(p)
        products.append(p)
    db.flush()
    return products


# ---------------------------------------------------------------------------
# Orders, OrderItems, Payments, Shipments
# ---------------------------------------------------------------------------
def make_order(db, customer: Customer, products: list[Product]) -> Order:
    order_created = fake.date_time_between(start_date="-180d", end_date="now", tzinfo=timezone.utc)

    order = Order(
        id=uuid.uuid4(),
        customer_id=customer.id,
        status=OrderStatus.PENDING,  # set properly below once we know payment/shipment outcome
        total_amount=Decimal("0.00"),
        shipping_address=fake.address().replace("\n", ", "),
        created_at=order_created,
    )
    db.add(order)
    db.flush()

    # --- Order items ---
    chosen_products = random.sample(products, k=random.randint(1, 4))
    total = Decimal("0.00")
    for prod in chosen_products:
        qty = random.randint(1, 3)
        unit_price = prod.price
        subtotal = unit_price * qty
        total += subtotal
        db.add(OrderItem(
            id=uuid.uuid4(),
            order_id=order.id,
            product_id=prod.id,
            quantity=qty,
            unit_price=unit_price,
            subtotal=subtotal,
        ))
    order.total_amount = total

    # --- Payment ---
    payment_roll = random.random()
    if payment_roll < 0.08:
        pay_status = PaymentStatus.FAILED
    elif payment_roll < 0.12:
        pay_status = PaymentStatus.PENDING
    else:
        pay_status = PaymentStatus.PAID

    payment = Payment(
        id=uuid.uuid4(),
        order_id=order.id,
        amount=total,
        method=random.choice(list(PaymentMethod)),
        status=pay_status,
        transaction_reference=f"TXN{uuid.uuid4().hex[:12].upper()}",
        created_at=order_created + timedelta(minutes=random.randint(1, 30)),
    )
    db.add(payment)

    # --- Order status + Shipment (only progresses if payment succeeded) ---
    if pay_status == PaymentStatus.FAILED:
        order.status = OrderStatus.CANCELLED
        db.flush()
        return order

    if pay_status == PaymentStatus.PENDING:
        order.status = OrderStatus.CONFIRMED
        db.flush()
        return order

    # Payment succeeded -> build a shipment
    ship_roll = random.random()
    estimated_delivery = order_created + timedelta(days=random.randint(3, 7))

    if ship_roll < 0.05:
        # Lost in transit
        ship_status = ShipmentStatus.LOST
        actual_delivery = None
        order_status = OrderStatus.PROCESSING
    elif ship_roll < 0.20:
        # Delayed: actual delivery well past the estimate (or still pending/delayed now)
        ship_status = ShipmentStatus.DELAYED
        if random.random() < 0.5 and estimated_delivery < now_utc():
            actual_delivery = estimated_delivery + timedelta(days=random.randint(2, 10))
            order_status = OrderStatus.DELIVERED
        else:
            actual_delivery = None
            order_status = OrderStatus.OUT_FOR_DELIVERY
    elif ship_roll < 0.30:
        ship_status = ShipmentStatus.OUT_FOR_DELIVERY
        actual_delivery = None
        order_status = OrderStatus.OUT_FOR_DELIVERY
    elif ship_roll < 0.40:
        ship_status = ShipmentStatus.IN_TRANSIT
        actual_delivery = None
        order_status = OrderStatus.SHIPPED
    else:
        ship_status = ShipmentStatus.DELIVERED
        actual_delivery = estimated_delivery - timedelta(days=random.randint(0, 2))
        order_status = OrderStatus.DELIVERED

    order.status = order_status

    db.add(Shipment(
        id=uuid.uuid4(),
        order_id=order.id,
        carrier=random.choice(CARRIERS),
        tracking_number=f"TRK{uuid.uuid4().hex[:10].upper()}",
        status=ship_status,
        estimated_delivery=estimated_delivery,
        actual_delivery=actual_delivery,
    ))

    db.flush()
    return order


def seed_orders(db, customers: list[Customer], products: list[Product]) -> list[Order]:
    orders = []
    for customer in customers:
        n_orders = random.randint(0, MAX_ORDERS_PER_CUSTOMER)
        for _ in range(n_orders):
            orders.append(make_order(db, customer, products))
    return orders


# ---------------------------------------------------------------------------
# Returns + Refunds (only for DELIVERED orders with a PAID payment)
# ---------------------------------------------------------------------------
RETURN_REASONS = [
    "Item damaged on arrival",
    "Wrong item received",
    "Product not as described",
    "Changed my mind",
    "Size/fit issue",
    "Defective / not working",
]

RETURN_WINDOW_DAYS = 10  # policy: returns must be requested within 10 days of delivery


def seed_returns_and_refunds(db, orders: list[Order]):
    delivered_orders = [
        o for o in orders
        if o.status == OrderStatus.DELIVERED and o.payment and o.payment.status == PaymentStatus.PAID
    ]
    eligible = random.sample(delivered_orders, k=min(len(delivered_orders), int(len(delivered_orders) * 0.35)))

    for order in eligible:
        delivered_at = order.shipment.actual_delivery or order.created_at + timedelta(days=5)
        expired = random.random() < 0.25  # ~25% of return requests are past the window

        if expired:
            requested_at = delivered_at + timedelta(days=RETURN_WINDOW_DAYS + random.randint(5, 30))
        else:
            requested_at = delivered_at + timedelta(days=random.randint(1, RETURN_WINDOW_DAYS - 1))

        ret = Return(
            id=uuid.uuid4(),
            order_id=order.id,
            customer_id=order.customer_id,
            reason=random.choice(RETURN_REASONS),
            requested_at=requested_at,
        )

        if expired:
            ret.status = ReturnStatus.REJECTED
            ret.reason += " (return requested after the 10-day return window had expired)"
            db.add(ret)
            db.flush()
            continue

        outcome_roll = random.random()
        if outcome_roll < 0.15:
            ret.status = ReturnStatus.REJECTED
            db.add(ret)
            db.flush()
            continue
        elif outcome_roll < 0.30:
            ret.status = ReturnStatus.UNDER_REVIEW
            db.add(ret)
            db.flush()
            continue
        elif outcome_roll < 0.45:
            ret.status = ReturnStatus.APPROVED
            ret.approved_at = requested_at + timedelta(days=1)
            db.add(ret)
            db.flush()
            continue

        # Fully completed return -> gets a refund
        ret.status = ReturnStatus.COMPLETED
        ret.approved_at = requested_at + timedelta(days=1)
        ret.completed_at = ret.approved_at + timedelta(days=random.randint(2, 6))
        db.add(ret)
        db.flush()

        refund_roll = random.random()
        refund_status = RefundStatus.COMPLETED if refund_roll > 0.1 else RefundStatus.FAILED

        refund = Refund(
            id=uuid.uuid4(),
            return_id=ret.id,
            payment_id=order.payment.id,
            amount=order.payment.amount,
            status=refund_status,
            refund_reference=f"RFD{uuid.uuid4().hex[:12].upper()}",
            created_at=ret.completed_at,
            completed_at=ret.completed_at + timedelta(days=random.randint(1, 3))
            if refund_status == RefundStatus.COMPLETED else None,
        )
        db.add(refund)

        if refund_status == RefundStatus.COMPLETED:
            order.payment.status = PaymentStatus.REFUNDED

    db.flush()


# ---------------------------------------------------------------------------
# Support tickets
# ---------------------------------------------------------------------------
TICKET_SUBJECTS = [
    "Order not delivered yet",
    "Received damaged product",
    "Refund not credited",
    "Wrong item delivered",
    "Unable to track my order",
    "Payment deducted but order not confirmed",
    "Want to change delivery address",
    "Product quality complaint",
]


def seed_support_tickets(db, customers: list[Customer], orders: list[Order], n=60):
    orders_by_customer: dict[uuid.UUID, list[Order]] = {}
    for o in orders:
        orders_by_customer.setdefault(o.customer_id, []).append(o)

    for _ in range(n):
        customer = random.choice(customers)
        customer_orders = orders_by_customer.get(customer.id, [])
        linked_order = random.choice(customer_orders) if customer_orders and random.random() < 0.7 else None

        status = random.choices(
            list(TicketStatus),
            weights=[0.25, 0.2, 0.15, 0.2, 0.2],
            k=1,
        )[0]
        created_at = fake.date_time_between(start_date="-90d", end_date="now", tzinfo=timezone.utc)

        db.add(SupportTicket(
            id=uuid.uuid4(),
            customer_id=customer.id,
            order_id=linked_order.id if linked_order else None,
            subject=random.choice(TICKET_SUBJECTS),
            description=fake.paragraph(nb_sentences=3),
            priority=random.choice(list(TicketPriority)),
            status=status,
            assigned_to=fake.name() if status != TicketStatus.OPEN else None,
            created_at=created_at,
        ))

    db.flush()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    db = SessionLocal()
    try:
        print("Seeding customers...")
        customers = seed_customers(db)

        print("Seeding products...")
        products = seed_products(db)

        print("Seeding orders, payments, shipments...")
        orders = seed_orders(db, customers, products)

        print("Seeding returns and refunds...")
        seed_returns_and_refunds(db, orders)

        print("Seeding support tickets...")
        seed_support_tickets(db, customers, orders)

        db.commit()
        print(
            f"Done. Customers={len(customers)} Products={len(products)} "
            f"Orders={len(orders)}"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()