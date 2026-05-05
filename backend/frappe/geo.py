from __future__ import annotations

import math
import re
from typing import Any, Optional, Tuple

import frappe


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EARTH_RADIUS_KM = 6371.0
"""Mean Earth radius in kilometres."""

KM_PER_DEGREE_LAT = 110.574
"""Approximate kilometres per degree of latitude."""


# ---------------------------------------------------------------------------
# Distance calculations
# ---------------------------------------------------------------------------


def get_distance_between_coordinates(
    coord1: tuple[float, float],
    coord2: tuple[float, float],
) -> float:
    """Calculate the great-circle distance in km between two lat/lng points.

    Uses the Haversine formula.

    Args:
        coord1: ``(latitude, longitude)`` of the first point.
        coord2: ``(latitude, longitude)`` of the second point.

    Returns:
        Distance in kilometres.
    """
    lat1, lng1 = coord1
    lat2, lng2 = coord2
    return get_coordinates_distance_km(lat1, lng1, lat2, lng2)


def get_coordinates_distance_km(
    lat1: float,
    lng1: float,
    lat2: float,
    lng2: float,
) -> float:
    """Haversine distance between two latitude/longitude pairs.

    Args:
        lat1: Latitude of point 1 (degrees).
        lng1: Longitude of point 1 (degrees).
        lat2: Latitude of point 2 (degrees).
        lng2: Longitude of point 2 (degrees).

    Returns:
        Distance in kilometres.
    """
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)

    sin_dlat = math.sin(dlat / 2)
    sin_dlng = math.sin(dlng / 2)

    a = (
        sin_dlat * sin_dlat
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * sin_dlng
        * sin_dlng
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return EARTH_RADIUS_KM * c


# ---------------------------------------------------------------------------
# Nearest-document lookup
# ---------------------------------------------------------------------------


def get_nearest(
    lat: float,
    lng: float,
    doctype: str,
    filters: Optional[dict] = None,
    fieldname: str = "location",
    radius: float = 10.0,
) -> list[dict]:
    """Find the nearest documents to the given coordinates.

    This is a best-effort implementation.  For SQLite backends without
    spatial indexing it fetches candidate rows and computes distances in
    Python.  Results are sorted by ascending distance and filtered to
    *radius* km.

    Args:
        lat: Reference latitude.
        lng: Reference longitude.
        doctype: DocType to search.
        filters: Additional ``frappe.get_all`` filters.
        fieldname: Field containing the coordinates (comma-separated
            ``lat,lng`` string or JSON).
        radius: Maximum distance in kilometres.

    Returns:
        List of dicts with ``name``, ``distance_km``, and the document's
        fields.
    """
    filters = filters or {}

    # Fetch candidate records – limit to a rough bounding box for efficiency
    lat_delta = radius / KM_PER_DEGREE_LAT
    lng_delta = radius / (KM_PER_DEGREE_LAT * math.cos(math.radians(lat)))

    bbox_filters = dict(filters)
    # We cannot use range filters on the location field directly,
    # so we fetch all and filter in Python.  Override this in
    # sub-classes if your backend supports spatial queries.
    candidates = frappe.get_all(
        doctype,
        fields=["name", fieldname, "*"],
        filters=bbox_filters,
        limit_page_length=500,
    )

    results: list[dict] = []
    for row in candidates:
        raw = row.get(fieldname)
        if not raw:
            continue

        parsed = parse_coordinates(raw)
        if parsed is None:
            continue

        row_lat, row_lng = parsed
        distance = get_coordinates_distance_km(lat, lng, row_lat, row_lng)
        if distance <= radius:
            results.append({
                **row,
                "distance_km": round(distance, 2),
            })

    results.sort(key=lambda r: r["distance_km"])
    return results


# ---------------------------------------------------------------------------
# Coordinate formatting / parsing
# ---------------------------------------------------------------------------


def format_coordinates(coordinates: Any) -> str:
    """Format coordinates for display.

    Accepts a ``"lat,lng"`` string, a ``(lat, lng)`` tuple, or a
    ``{"lat": …, "lng": …}`` dict.

    Args:
        coordinates: The coordinate value to format.

    Returns:
        Human-readable string like ``"40.7128° N, 74.0060° W"``.
    """
    parsed = parse_coordinates(coordinates)
    if parsed is None:
        return ""

    lat, lng = parsed
    lat_dir = "N" if lat >= 0 else "S"
    lng_dir = "E" if lng >= 0 else "W"
    return f"{abs(lat):.4f}° {lat_dir}, {abs(lng):.4f}° {lng_dir}"


def parse_coordinates(coord_string: Any) -> Optional[Tuple[float, float]]:
    """Parse a coordinate value to a ``(lat, lng)`` tuple.

    Supported inputs:
    - ``"40.7128,-74.0060"`` (comma-separated)
    - ``"40.7128, -74.0060"`` (with space)
    - ``(40.7128, -74.0060)`` (tuple/list)
    - ``{"lat": 40.7128, "lng": -74.0060}`` (dict)
    - JSON string representations of the above

    Args:
        coord_string: The value to parse.

    Returns:
        ``(latitude, longitude)`` tuple, or ``None`` if unparseable.
    """
    if coord_string is None:
        return None

    # Already a tuple or list
    if isinstance(coord_string, (tuple, list)) and len(coord_string) >= 2:
        try:
            return (float(coord_string[0]), float(coord_string[1]))
        except (ValueError, TypeError):
            return None

    # Dict
    if isinstance(coord_string, dict):
        lat = coord_string.get("lat") or coord_string.get("latitude")
        lng = coord_string.get("lng") or coord_string.get("lon") or coord_string.get("longitude")
        if lat is not None and lng is not None:
            try:
                return (float(lat), float(lng))
            except (ValueError, TypeError):
                return None
        return None

    # String
    if isinstance(coord_string, str):
        coord_string = coord_string.strip()
        if not coord_string:
            return None

        # Try JSON
        if coord_string.startswith("{"):
            try:
                import json
                data = json.loads(coord_string)
                return parse_coordinates(data)
            except (json.JSONDecodeError, ValueError):
                pass

        # Comma-separated
        parts = coord_string.split(",")
        if len(parts) >= 2:
            try:
                return (float(parts[0].strip()), float(parts[1].strip()))
            except (ValueError, TypeError):
                pass

    return None


def validate_coordinates(coordinates: Any) -> bool:
    """Validate that *coordinates* is a well-formed lat/lng pair.

    Checks:
    - Latitude is between ``-90`` and ``90``.
    - Longitude is between ``-180`` and ``180``.

    Args:
        coordinates: Value to validate (any format accepted by
            :func:`parse_coordinates`).

    Returns:
        ``True`` if the coordinates are valid.
    """
    parsed = parse_coordinates(coordinates)
    if parsed is None:
        return False

    lat, lng = parsed
    return -90 <= lat <= 90 and -180 <= lng <= 180


# ---------------------------------------------------------------------------
# Route distance (placeholder for external maps API)
# ---------------------------------------------------------------------------


def get_route_distance(
    origin: tuple[float, float] | str,
    destination: tuple[float, float] | str,
) -> Optional[dict]:
    """Get driving distance between two points.

    This is a **placeholder** that returns the straight-line (Haversine)
    distance.  Override or replace with a call to an external routing
    service (Google Maps, OpenRouteService, etc.) for real road distances.

    Args:
        origin: ``(lat, lng)`` or location string.
        destination: ``(lat, lng)`` or location string.

    Returns:
        Dict with ``distance_km`` and ``duration_minutes`` (estimated),
        or ``None``.
    """
    origin_parsed = parse_coordinates(origin)
    dest_parsed = parse_coordinates(destination)

    if origin_parsed is None or dest_parsed is None:
        return None

    straight_km = get_coordinates_distance_km(
        origin_parsed[0], origin_parsed[1],
        dest_parsed[0], dest_parsed[1],
    )

    # Rough heuristic: road distance ~ 1.2x straight line, speed ~ 40 km/h
    road_km = straight_km * 1.2
    duration_min = (road_km / 40.0) * 60.0

    return {
        "distance_km": round(road_km, 2),
        "straight_line_km": round(straight_km, 2),
        "duration_minutes": round(duration_min, 1),
    }


# ---------------------------------------------------------------------------
# GeoJSON helpers
# ---------------------------------------------------------------------------


def to_geojson_point(lat: float, lng: float) -> dict:
    """Create a GeoJSON Point geometry dict.

    Args:
        lat: Latitude.
        lng: Longitude.

    Returns:
        GeoJSON Point dict.
    """
    return {
        "type": "Point",
        "coordinates": [lng, lat],
    }


def from_geojson_point(geojson: dict) -> Optional[Tuple[float, float]]:
    """Extract ``(lat, lng)`` from a GeoJSON Point geometry.

    Args:
        geojson: GeoJSON geometry dict.

    Returns:
        ``(latitude, longitude)`` tuple, or ``None``.
    """
    if geojson.get("type") == "Point" and "coordinates" in geojson:
        coords = geojson["coordinates"]
        if isinstance(coords, (list, tuple)) and len(coords) >= 2:
            return (float(coords[1]), float(coords[0]))
    return None


def to_dms(degrees: float) -> Tuple[int, int, float, str]:
    """Convert decimal degrees to degrees, minutes, seconds.

    Args:
        degrees: Decimal degrees (positive or negative).

    Returns:
        ``(degrees, minutes, seconds, direction)`` where direction is
        ``'N'``, ``'S'``, ``'E'``, or ``'W'``.
    """
    direction = "N" if degrees >= 0 else "S"
    if abs(degrees) > 90:
        direction = "E" if degrees >= 0 else "W"

    abs_deg = abs(degrees)
    d = int(abs_deg)
    m_float = (abs_deg - d) * 60
    m = int(m_float)
    s = (m_float - m) * 60
    return d, m, round(s, 2), direction


def format_dms(degrees: float, is_latitude: bool = True) -> str:
    """Format decimal degrees as a DMS string.

    Args:
        degrees: Decimal degrees.
        is_latitude: Whether this is a latitude (affects N/S vs E/W).

    Returns:
        String like ``"40° 42' 51.12\" N"``.
    """
    d, m, s, _ = to_dms(degrees)
    direction = "N" if degrees >= 0 else "S"
    if not is_latitude:
        direction = "E" if degrees >= 0 else "W"
    return f"{d}° {m}' {s:.2f}\" {direction}"
