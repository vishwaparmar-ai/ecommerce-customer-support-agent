from __future__ import annotations

import uuid
from decimal import Decimal
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.core.logging import logger
from backend.db.models import Product
from backend.schemas.product import ProductCreate, ProductUpdate


def list_products(
    db: Session,
    category: str | None = None,
    search: str | None = None,
    is_active: bool | None = True,
    limit: int = 50,
    offset: int = 0,
) -> list[Product]:
    query = db.query(Product)
    if is_active is not None:
        query = query.filter(Product.is_active == is_active)
    if category:
        query = query.filter(Product.category.ilike(f"%{category}%"))
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            Product.name.ilike(search_filter) | Product.description.ilike(search_filter)
        )
    return query.order_by(Product.name).offset(offset).limit(limit).all()


def get_product_by_id(db: Session, product_id: uuid.UUID) -> Product:
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    return product


def create_product(db: Session, data: ProductCreate) -> Product:
    product = Product(
        id=uuid.uuid4(),
        name=data.name.strip(),
        description=data.description.strip() if data.description else None,
        category=data.category.strip() if data.category else None,
        price=data.price,
        stock_quantity=data.stock_quantity,
        is_active=data.is_active,
    )
    db.add(product)
    db.commit()
    db.refresh(product)

    logger.info("product_created", extra={"product_id": str(product.id), "name": product.name})
    return product


def update_product(db: Session, product_id: uuid.UUID, data: ProductUpdate) -> Product:
    product = get_product_by_id(db, product_id)

    update_dict = data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        if isinstance(value, str):
            value = value.strip()
        setattr(product, field, value)

    db.commit()
    db.refresh(product)

    logger.info("product_updated", extra={"product_id": str(product.id)})
    return product


def delete_product(db: Session, product_id: uuid.UUID) -> Product:
    """Soft delete: deactivates the product rather than destroying historical order references."""
    product = get_product_by_id(db, product_id)
    product.is_active = False
    db.commit()
    db.refresh(product)

    logger.info("product_deactivated", extra={"product_id": str(product.id)})
    return product
