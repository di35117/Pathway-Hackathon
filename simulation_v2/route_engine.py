"""
route_engine.py — Generates real road polylines for all routes via OSRM.

Uses the public OSRM API (OpenStreetMap data) to get actual road geometry
for every city-to-city route. No API key required.

Priority:
1. OSRM public API  (real OpenStreetMap road geometry, no key needed)
2. ORS API          (if API key is set)
3. Synthetic polyline fallback
"""

import json
import logging
import math
import os
import random
import time
import requests

from simulation_v2.gps_simulator_v2 import haversine_distance as _haversine_m

logger = logging.getLogger(__name__)

ORS_API_KEY = os.getenv("ORS_API_KEY", "")
ORS_BASE_URL = "https://api.openrouteservice.org/v2/directions/driving-hgv"

OSRM_BASE_URL = "http://router.project-osrm.org/route/v1/driving"

# Use a module-level RNG so we don't clobber the global random state
_rng = random.Random(42)

def _haversine_distance(lat1, lng1, lat2, lng2):
    """Return distance in km between two GPS points (delegates to shared impl)."""
    return _haversine_m(lat1, lng1, lat2, lng2) / 1000.0


def _generate_synthetic_polyline(origin_lat, origin_lng, dest_lat, dest_lng,
                                 origin_name="", dest_name=""):
    """
    Generate a realistic polyline between origin and destination,
    following approximate highway geometry patterns.
    """
    total_dist = _haversine_distance(origin_lat, origin_lng, dest_lat, dest_lng)
    num_points = max(15, int(total_dist / 15))  # ~1 point per 15 km

    waypoints = []
    for i in range(num_points + 1):
        t = i / num_points
        lat = origin_lat + t * (dest_lat - origin_lat)
        lng = origin_lng + t * (dest_lng - origin_lng)

        if 0 < t < 1:
            curve = 0.06 * math.sin(t * math.pi * _rng.uniform(2, 5))
            noise = _rng.uniform(-0.015, 0.015)
            dx = dest_lng - origin_lng
            dy = dest_lat - origin_lat
            norm = math.sqrt(dx * dx + dy * dy) or 1
            perp_lat = -dx / norm
            perp_lng = dy / norm
            lat += perp_lat * (curve + noise)
            lng += perp_lng * (curve + noise)

        if t < 0.05 or t > 0.95:
            rc = "city"
        elif t < 0.10 or t > 0.90:
            rc = "state_road"
        else:
            rc = "highway"

        waypoints.append({"lat": round(lat, 6), "lng": round(lng, 6),
                          "road_class": rc})
    return waypoints


def fetch_route_from_osrm(origin_lat, origin_lng, dest_lat, dest_lng):
    """
    Call the public OSRM API to get a real road route.
    Uses OpenStreetMap data — no API key needed.
    Returns waypoint list or None.
    """
    url = (f"{OSRM_BASE_URL}/{origin_lng},{origin_lat}"
           f";{dest_lng},{dest_lat}"
           f"?geometries=geojson&overview=full")
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != "Ok" or not data.get("routes"):
            return None

        coords = data["routes"][0]["geometry"]["coordinates"]
        if len(coords) < 3:
            return None

        total_pts = len(coords)
        waypoints = []
        for idx, (lng, lat) in enumerate(coords):
            frac = idx / max(total_pts - 1, 1)
            if frac < 0.05 or frac > 0.95:
                rc = "city"
            elif frac < 0.10 or frac > 0.90:
                rc = "state_road"
            else:
                rc = "highway"
            waypoints.append({"lat": round(lat, 6), "lng": round(lng, 6),
                              "road_class": rc})

        logger.info("OSRM returned %d waypoints for (%s,%s)->(%s,%s)",
                     len(waypoints), origin_lat, origin_lng, dest_lat, dest_lng)
        return waypoints
    except Exception as exc:
        logger.warning("OSRM request failed: %s", exc)
        return None


def fetch_route_from_ors(origin_lat, origin_lng, dest_lat, dest_lng):
    """Call ORS API. Returns waypoint list or None."""
    if not ORS_API_KEY:
        return None
    try:
        headers = {
            "Authorization": f"Bearer {ORS_API_KEY}",
            "Content-Type": "application/json",
        }
        body = {"coordinates": [[origin_lng, origin_lat], [dest_lng, dest_lat]],
                "instructions": True, "geometry": True}
        resp = requests.post(ORS_BASE_URL, json=body, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        coords = data["routes"][0]["geometry"]["coordinates"]
        waypoints = []
        for lng, lat in coords:
            waypoints.append({"lat": round(lat, 6), "lng": round(lng, 6),
                              "road_class": "highway"})
        return waypoints
    except Exception as exc:
        logger.warning("ORS request failed: %s", exc)
        return None


def fetch_route(origin, destination):
    """
    Get a route polyline for origin -> destination.
    origin/destination are tuples: (name, lat, lng)

    Priority:
    1. OSRM public API (real OpenStreetMap road geometry)
    2. ORS API (if API key available)
    3. Synthetic polyline fallback
    """
    origin_name = origin[0]
    dest_name = destination[0]

    # 1. Try OSRM (real roads, no API key needed)
    route = fetch_route_from_osrm(origin[1], origin[2],
                                   destination[1], destination[2])
    if route and len(route) > 2:
        logger.info("Route %s → %s: OSRM (%d pts)",
                     origin_name, dest_name, len(route))
        return route

    # 2. Try ORS API
    route = fetch_route_from_ors(origin[1], origin[2],
                                  destination[1], destination[2])
    if route and len(route) > 2:
        logger.info("Route %s → %s: ORS (%d pts)",
                     origin_name, dest_name, len(route))
        return route

    # 3. Synthetic fallback
    logger.warning("Route %s → %s: using synthetic fallback",
                    origin_name, dest_name)
    return _generate_synthetic_polyline(origin[1], origin[2],
                                        destination[1], destination[2],
                                        origin_name, dest_name)


def fetch_and_cache_all_routes(shipments):
    """Fetch routes for all shipments and cache to disk + memory."""
    try:
        from sim.config import CITIES
    except ImportError:
        CITIES = []
    from simulation_v2.route_cache import save_routes

    city_lookup = {name: (name, lat, lng) for name, lat, lng in CITIES}
    routes = {}

    for idx, s in enumerate(shipments):
        sid = s["shipment_id"]
        origin = city_lookup.get(s["origin"])
        dest = city_lookup.get(s["destination"])
        if origin and dest:
            routes[sid] = fetch_route(origin, dest)
        else:
            routes[sid] = _generate_synthetic_polyline(
                s["current_lat"], s["current_lon"],
                s["end_lat"], s["end_lon"]
            )

        # Rate-limit OSRM: 1 request per second (public API fair-use)
        if idx < len(shipments) - 1:
            time.sleep(1.1)

    save_routes(routes)
    return routes
