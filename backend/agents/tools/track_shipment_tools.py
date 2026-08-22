"""
Agent tools: shipments.

"""

from __future__ import annotations

import uuid

from langchain_core.tools import StructuredTool
from sqlalchemy.orm import Session
from backend.db.models import Customer
from backend.schemas.order_tools import TrackShipmentInput
from backend.services.order_service import get_order_for_customer




def _serialize_shipment(order) -> dict:
    """
    Converts an Order's shipment into a plain, JSON-safe dict for the LLM.
    Handles the case where no shipment exists yet (order hasn't progressed
    past payment/preparation).
    """
    if order.shipment is None:
        return {
            "has_shipment": False,
            "order_status": order.status.value,
            "message": "This order does not have a shipment yet.",
        }

    shipment = order.shipment
    return {
        "has_shipment": True,
        "carrier": shipment.carrier,
        "tracking_number": shipment.tracking_number,
        "status": shipment.status.value,
        "estimated_delivery": shipment.estimated_delivery.isoformat() if shipment.estimated_delivery else None,
        "actual_delivery": shipment.actual_delivery.isoformat() if shipment.actual_delivery else None,
    }


def make_track_shipment_tool(db: Session, current_user: Customer) -> StructuredTool:
    """
    Builds a track_shipment tool scoped to current_user. Reuses
    get_order_for_customer for the same ownership enforcement as get_order --
    a customer can only track shipments for orders they actually own.
    """

    def _track_shipment(order_id: uuid.UUID) -> dict:
        try:
            order = get_order_for_customer(db, order_id, current_user.id)
            result = _serialize_shipment(order)
           
            return result
        
        except Exception as exc:
            return {"error": str(getattr(exc, "detail", exc))}

    return StructuredTool.from_function(
        func=_track_shipment,
        name="track_shipment",
        description=(
            "Track the shipment status of the current customer's own order "
            "by its order_id. Returns carrier, tracking number, current "
            "status (e.g. in_transit, delayed, delivered), and estimated/"
            "actual delivery dates. Only works for orders the customer owns."
        ),
        args_schema=TrackShipmentInput,
    )