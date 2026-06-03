"""
Watchlist router.

GET    /api/watchlist
POST   /api/watchlist
DELETE /api/watchlist/{id}
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.watchlist import WatchlistItem
from app.schemas.watchlist import WatchlistItemCreate, WatchlistItemRead

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("", response_model=list[WatchlistItemRead])
def list_watchlist(db: Session = Depends(get_db)):
    """Return all watchlist items."""
    return db.query(WatchlistItem).order_by(WatchlistItem.created_at.desc()).all()


@router.post("", response_model=WatchlistItemRead, status_code=201)
def add_watchlist_item(body: WatchlistItemCreate, db: Session = Depends(get_db)):
    """Add a symbol to the watchlist."""
    item = WatchlistItem(
        symbol=body.symbol.upper(),
        exchange=body.exchange.upper(),
        note=body.note,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=204)
def delete_watchlist_item(item_id: int, db: Session = Depends(get_db)):
    """Remove a symbol from the watchlist."""
    item = db.get(WatchlistItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Watchlist item {item_id} not found")
    db.delete(item)
    db.commit()
