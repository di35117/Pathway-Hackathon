"""
LiveCold — SOP Parser

Makes watched_docs/cold_chain_SOP.txt the single source of truth for product
temperature ranges. The SOP carries a machine-readable block that the humans
editing the document also see:

    <!-- PRODUCT_TEMP_RANGES
    Dairy:2:6
    Frozen_Meat:-18:-12
    ...
    -->

Everything downstream (shipment generation, risk profiles, dashboard display)
reads its safe ranges from here, so editing the SOP changes system behaviour.

The cache is invalidated on file mtime, so an SOP edit is picked up on the next
call without a restart — the same contract the Pathway RAG pipeline honours.

Usage:
    from core.sop_parser import get_product_temp_ranges, get_product_profile

    get_product_temp_ranges()      # {'Vaccines': (2.0, 8.0), ...}
    get_product_profile("Dairy")   # {'name': 'Dairy', 'safe_min': 2.0, 'safe_max': 6.0}
"""

import os
import re
import logging
import threading

log = logging.getLogger("sop_parser")

# watched_docs/ sits at the project root, one level above core/.
SOP_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "watched_docs",
    "cold_chain_SOP.txt",
)

# Used only when the SOP file is missing or its machine-readable block is
# unparseable. Kept in sync with the SOP; the SOP wins whenever it is readable.
_FALLBACK_RANGES = {
    "Vaccines":        (2.0, 8.0),
    "Frozen_Meat":     (-18.0, -12.0),
    "Dairy":           (2.0, 6.0),
    "Seafood":         (-1.0, 2.0),
    "Vegetables":      (7.0, 10.0),
    "Fruits":          (8.0, 12.0),
    "Pharmaceuticals": (2.0, 8.0),
    "Ice_Cream":       (-25.0, -18.0),
    "Flowers":         (2.0, 8.0),
}

_RANGE_BLOCK = re.compile(r"<!--\s*PRODUCT_TEMP_RANGES\s*\n(.*?)-->", re.DOTALL)

_lock = threading.Lock()
_cache = {"ranges": None, "mtime": None, "source": "none"}


def _parse_sop_file(filepath):
    """Extract the PRODUCT_TEMP_RANGES block. Returns dict or None."""
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as exc:
        log.warning("SOP file unreadable (%s): %s", filepath, exc)
        return None

    match = _RANGE_BLOCK.search(content)
    if not match:
        log.warning("No PRODUCT_TEMP_RANGES block found in %s", filepath)
        return None

    ranges = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split(":")
        if len(parts) != 3:
            log.warning("Skipping malformed SOP range line: %r", line)
            continue

        name = parts[0].strip()
        try:
            safe_min = float(parts[1].strip())
            safe_max = float(parts[2].strip())
        except ValueError:
            log.warning("Non-numeric temperatures in SOP line: %r", line)
            continue

        if safe_min > safe_max:
            log.warning("Inverted range in SOP line (min > max): %r", line)
            continue

        ranges[name] = (safe_min, safe_max)

    if not ranges:
        log.warning("PRODUCT_TEMP_RANGES block present but contained no valid rows")
        return None

    return ranges


def get_product_temp_ranges(force_reload=False):
    """
    All product temperature ranges, keyed by SOP product name.

    Re-reads the SOP whenever its mtime changes, so an edit takes effect on the
    next call. Falls back to _FALLBACK_RANGES only if the SOP cannot be parsed.
    """
    with _lock:
        try:
            mtime = os.path.getmtime(SOP_PATH)
        except OSError:
            mtime = None

        fresh = (
            not force_reload
            and _cache["ranges"] is not None
            and _cache["mtime"] == mtime
        )
        if fresh:
            return dict(_cache["ranges"])

        parsed = _parse_sop_file(SOP_PATH)
        if parsed:
            _cache.update(ranges=parsed, mtime=mtime, source="sop")
            log.info("Loaded %d product temp ranges from SOP", len(parsed))
        else:
            _cache.update(ranges=dict(_FALLBACK_RANGES), mtime=mtime, source="fallback")
            log.warning("Using fallback temperature ranges (SOP unavailable)")

        return dict(_cache["ranges"])


def get_source():
    """'sop' or 'fallback' — which one the last load actually used."""
    get_product_temp_ranges()
    return _cache["source"]


def _normalise(product_name):
    return product_name.strip().replace(" ", "_").replace("-", "_")


def get_product_profile(product_name):
    """
    Temperature profile for one product.

    Accepts 'Frozen Meat', 'frozen_meat', 'FROZEN-MEAT'. Falls back to a chilled
    2–8°C window for products the SOP does not list.
    """
    ranges = get_product_temp_ranges()
    key = _normalise(product_name)

    if key in ranges:
        safe_min, safe_max = ranges[key]
        return {"name": key, "safe_min": safe_min, "safe_max": safe_max}

    key_lower = key.lower()
    for name, (smin, smax) in ranges.items():
        if name.lower() == key_lower:
            return {"name": name, "safe_min": smin, "safe_max": smax}

    log.warning("Product %r not in SOP, defaulting to chilled 2-8C", product_name)
    return {"name": product_name, "safe_min": 2.0, "safe_max": 8.0}


def get_all_product_profiles():
    """Every SOP product as a list of profiles — used by the shipment factory."""
    return [
        {"name": name, "safe_min": smin, "safe_max": smax}
        for name, (smin, smax) in get_product_temp_ranges().items()
    ]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"\nSOP Parser — source: {get_source()}  ({SOP_PATH})\n")
    for product, (smin, smax) in get_product_temp_ranges().items():
        print(f"  {product:20s} {smin:>7}C -> {smax:>6}C")
    print(f"\n  Total: {len(get_product_temp_ranges())} products\n")
