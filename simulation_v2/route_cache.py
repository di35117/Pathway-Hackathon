"""
route_cache.py — Load / save pre-computed route polylines from JSON cache.
"""

import json
import os

_CACHE_PATH = os.path.join(os.path.dirname(__file__), "configs", "routes.json")
_cache = None  # in-memory singleton


def _ensure_loaded():
    global _cache
    if _cache is not None:
        return
    if os.path.exists(_CACHE_PATH):
        with open(_CACHE_PATH, "r") as f:
            _cache = json.load(f)
    else:
        _cache = {}


def load_route(shipment_id):
    """
    Return cached waypoint list for a shipment.
    Each waypoint is {"lat": float, "lng": float, "road_class": str}.
    Returns None if not cached.
    """
    _ensure_loaded()
    return _cache.get(shipment_id)


def save_routes(routes_dict):
    """Persist route dict to JSON cache file."""
    global _cache
    os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
    with open(_CACHE_PATH, "w") as f:
        json.dump(routes_dict, f, indent=2)
    _cache = routes_dict


def is_cached(shipment_id):
    """Check if a route is already cached."""
    _ensure_loaded()
    return shipment_id in _cache


def get_all_cached():
    """Return the full cache dict."""
    _ensure_loaded()
    return dict(_cache)
