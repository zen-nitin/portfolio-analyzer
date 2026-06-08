"""
Watchlist router.

GET    /api/watchlist
POST   /api/watchlist
PUT    /api/watchlist/{id}/entry-zone
DELETE /api/watchlist/{id}
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.watchlist import WatchlistEntryZone, WatchlistItem, WatchlistPosition
from app.schemas.watchlist import (
    WatchlistEntryZoneUpdate,
    WatchlistItemCreate,
    WatchlistItemRead,
    WatchlistReorder,
)

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


def _normalize_zone(
    low: Optional[float], high: Optional[float]
) -> tuple[Optional[float], Optional[float]]:
    """Validate and tidy a price range: reject negatives, order low<=high."""
    for v in (low, high):
        if v is not None and v < 0:
            raise HTTPException(status_code=400, detail="Entry prices cannot be negative.")
    if low is not None and high is not None and low > high:
        low, high = high, low
    return low, high


@router.get("", response_model=list[WatchlistItemRead])
def list_watchlist(db: Session = Depends(get_db)):
    """Return all watchlist items, ordered by manual position (top first).

    Items without a manual position (e.g. freshly added, or before the first
    reorder) sort first, newest-first — so a new item appears at the top.
    """
    items = db.query(WatchlistItem).order_by(WatchlistItem.created_at.desc()).all()
    # Stable sort: positioned items in position order; unpositioned keep the
    # created_at-desc order above and sort ahead of positioned ones.
    items.sort(key=lambda i: (i.sort_position is not None, i.sort_position or 0))
    return items


@router.post("", response_model=WatchlistItemRead, status_code=201)
def add_watchlist_item(body: WatchlistItemCreate, db: Session = Depends(get_db)):
    """Add a symbol to the watchlist, optionally with a buy entry zone."""
    item = WatchlistItem(
        symbol=body.symbol.upper(),
        exchange=body.exchange.upper(),
        note=body.note,
    )
    low, high = _normalize_zone(body.entry_low, body.entry_high)
    if low is not None or high is not None:
        item.entry_zone = WatchlistEntryZone(low=low, high=high)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/{item_id}/entry-zone", response_model=WatchlistItemRead)
def set_entry_zone(
    item_id: int, body: WatchlistEntryZoneUpdate, db: Session = Depends(get_db)
):
    """Set, update, or clear an item's buy entry zone.

    Passing both bounds as null removes the zone.
    """
    item = db.get(WatchlistItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Watchlist item {item_id} not found")

    low, high = _normalize_zone(body.entry_low, body.entry_high)

    if low is None and high is None:
        # Clear — delete-orphan removes the row on commit.
        item.entry_zone = None
    elif item.entry_zone is None:
        item.entry_zone = WatchlistEntryZone(low=low, high=high)
    else:
        item.entry_zone.low = low
        item.entry_zone.high = high

    db.commit()
    db.refresh(item)
    return item


@router.put("/reorder", response_model=list[WatchlistItemRead])
def reorder_watchlist(body: WatchlistReorder, db: Session = Depends(get_db)):
    """Persist a new manual order. ``ids`` is the full list, top first.

    Assigns each listed id a position equal to its index; ids not present in
    the watchlist are ignored. Returns the freshly ordered list.
    """
    existing = {item.id: item for item in db.query(WatchlistItem).all()}
    for pos, item_id in enumerate(body.ids):
        item = existing.get(item_id)
        if item is None:
            continue
        if item.order is None:
            item.order = WatchlistPosition(position=pos)
        else:
            item.order.position = pos
    db.commit()
    return list_watchlist(db)


@router.delete("/{item_id}", status_code=204)
def delete_watchlist_item(item_id: int, db: Session = Depends(get_db)):
    """Remove a symbol from the watchlist (and its entry zone, via cascade)."""
    item = db.get(WatchlistItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Watchlist item {item_id} not found")
    db.delete(item)
    db.commit()
