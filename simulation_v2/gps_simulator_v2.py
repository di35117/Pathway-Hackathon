"""
gps_simulator_v2.py — Road-following GPS movement along polyline waypoints.

Each truck maintains a pointer (segment_index, progress) and advances
along its route polyline using haversine math. This replaces the V1
straight-line interpolation.
"""

import math


def haversine_distance(lat1, lng1, lat2, lng2):
    """Distance in metres between two GPS points."""
    R = 6_371_000  # Earth radius in metres
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def interpolate_point(p1, p2, fraction):
    """Linearly interpolate between two waypoint dicts by given fraction [0,1]."""
    return {
        "lat": p1["lat"] + fraction * (p2["lat"] - p1["lat"]),
        "lng": p1["lng"] + fraction * (p2["lng"] - p1["lng"]),
        "road_class": p1.get("road_class", "highway"),
    }


class TruckState:
    """
    Tracks a truck's position along a polyline route.

    Attributes
    ----------
    polyline : list[dict]
        List of {"lat", "lng", "road_class"} waypoints.
    segment_index : int
        Index of the current polyline segment the truck is on.
    segment_progress : float
        Metres already covered within current segment.
    finished : bool
        True once the truck reaches the last waypoint.
    total_distance_m : float
        Sum of all segment distances.
    distance_covered_m : float
        Total cumulative distance covered so far.
    """

    def __init__(self, polyline):
        if not polyline or len(polyline) < 2:
            raise ValueError("Polyline must have at least 2 waypoints")
        self.polyline = polyline
        self.segment_index = 0
        self.segment_progress = 0.0
        self.finished = False

        # Pre-compute segment distances
        self._segment_distances = []
        for i in range(len(polyline) - 1):
            d = haversine_distance(
                polyline[i]["lat"], polyline[i]["lng"],
                polyline[i + 1]["lat"], polyline[i + 1]["lng"],
            )
            self._segment_distances.append(d)

        self.total_distance_m = sum(self._segment_distances)
        self.distance_covered_m = 0.0

    @property
    def progress_fraction(self):
        """Overall route progress as fraction [0, 1]."""
        if self.total_distance_m == 0:
            return 1.0
        return min(1.0, self.distance_covered_m / self.total_distance_m)

    @property
    def current_road_class(self):
        """Road class at current position."""
        idx = min(self.segment_index, len(self.polyline) - 1)
        return self.polyline[idx].get("road_class", "highway")

    def get_position(self):
        """
        Return current interpolated position as {"lat", "lng", "road_class"}.
        """
        if self.finished:
            last = self.polyline[-1]
            return {"lat": last["lat"], "lng": last["lng"],
                    "road_class": last.get("road_class", "highway")}

        p1 = self.polyline[self.segment_index]
        p2 = self.polyline[self.segment_index + 1]
        seg_dist = self._segment_distances[self.segment_index]

        if seg_dist == 0:
            fraction = 1.0
        else:
            fraction = min(1.0, self.segment_progress / seg_dist)

        return interpolate_point(p1, p2, fraction)

    def advance(self, delta_t_seconds, speed_kmh):
        """
        Move the truck forward along the polyline.

        Parameters
        ----------
        delta_t_seconds : float
            Time step in seconds.
        speed_kmh : float
            Current speed in km/h.

        Returns
        -------
        dict  {"lat", "lng", "road_class"} — the new position.
        """
        if self.finished:
            return self.get_position()

        distance_to_cover = (speed_kmh / 3.6) * delta_t_seconds  # metres

        remaining = distance_to_cover
        while remaining > 0 and not self.finished:
            seg_dist = self._segment_distances[self.segment_index]
            left_in_segment = seg_dist - self.segment_progress

            if remaining < left_in_segment:
                self.segment_progress += remaining
                self.distance_covered_m += remaining
                remaining = 0
            else:
                # Move to next segment
                self.distance_covered_m += left_in_segment
                remaining -= left_in_segment
                self.segment_index += 1
                self.segment_progress = 0.0

                if self.segment_index >= len(self._segment_distances):
                    self.finished = True

        return self.get_position()

    def remaining_distance_km(self):
        """Distance remaining to destination in km."""
        return max(0.0, (self.total_distance_m - self.distance_covered_m) / 1000)
