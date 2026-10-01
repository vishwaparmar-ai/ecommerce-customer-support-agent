from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.db.dependency import get_db, require_role
from backend.db.models import Customer, CustomerRole
from backend.schemas.product import ProductCreate, ProductResponse, ProductUpdate
from backend.services.product_service import (
    create_product,
    delete_product,
    get_product_by_id,
    list_products,
    update_product,
)

router = APIRouter(
    prefix="/products",
    tags=["Products"],
)


@router.get("/", response_model=list[ProductResponse])
def get_products(
    category: str | None = Query(None, description="Filter by product category"),
    search: str | None = Query(None, description="Search by name or description"),
    is_active: bool | None = Query(True, description="Filter by active status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List and filter products in the catalog."""
    return list_products(
        db=db,
        category=category,
        search=search,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(
    product_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Retrieve detailed product information by ID."""
    return get_product_by_id(db=db, product_id=product_id)


@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_new_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    admin: Customer = Depends(require_role(CustomerRole.ADMIN)),
):
    """Admin only: Create a new product in the catalog."""
    return create_product(db=db, data=payload)


@router.patch("/{product_id}", response_model=ProductResponse)
def update_existing_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    admin: Customer = Depends(require_role(CustomerRole.ADMIN)),
):
    """Admin only: Update product details."""
    return update_product(db=db, product_id=product_id, data=payload)


@router.delete("/{product_id}", response_model=ProductResponse)
def deactivate_product(
    product_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Customer = Depends(require_role(CustomerRole.ADMIN)),
):
    """Admin only: Deactivate a product."""
    return delete_product(db=db, product_id=product_id)
