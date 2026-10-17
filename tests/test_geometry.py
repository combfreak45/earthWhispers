"""
Unit tests for Catchment Geometry & Lower Brahmaputra Basin filtering.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data_pipeline")))

from catchment_geometry import (
    LOWER_BRAHMAPUTRA_BASIN_COORDINATES,
    CATCHMENT_METADATA,
    is_coordinate_in_catchment
)


def test_catchment_polygon_closure():
    """Verifies that the polygon coordinate list is properly closed."""
    assert LOWER_BRAHMAPUTRA_BASIN_COORDINATES[0] == LOWER_BRAHMAPUTRA_BASIN_COORDINATES[-1]
    assert len(LOWER_BRAHMAPUTRA_BASIN_COORDINATES) >= 5


def test_lower_brahmaputra_settlements_in_catchment():
    """Verifies that critical Lower Brahmaputra settlements fall inside the catchment bounding box."""
    # Dhubri (Western Terminus)
    assert is_coordinate_in_catchment(26.02, 89.98) is True
    # Barpeta (Floodplain Lowlands)
    assert is_coordinate_in_catchment(26.32, 91.00) is True
    # Goalpara (South River Bank)
    assert is_coordinate_in_catchment(26.18, 90.62) is True
    # Morigaon (Eastern Lower Basin Corridor)
    assert is_coordinate_in_catchment(26.25, 92.34) is True


def test_out_of_bounds_coordinates_excluded():
    """Verifies that non-catchment coordinates are excluded."""
    # Kolkata
    assert is_coordinate_in_catchment(22.57, 88.36) is False
    # New Delhi
    assert is_coordinate_in_catchment(28.61, 77.20) is False
    # Upper Himalayas (Tibet)
    assert is_coordinate_in_catchment(30.00, 91.00) is False


def test_catchment_metadata_completeness():
    """Verifies catchment metadata fields and district coverage."""
    assert CATCHMENT_METADATA["catchment_id"] == "brahmaputra_lower_assam"
    assert "Dhubri" in CATCHMENT_METADATA["districts"]
    assert "Barpeta" in CATCHMENT_METADATA["districts"]
    assert "Goalpara" in CATCHMENT_METADATA["districts"]
    assert "Morigaon" in CATCHMENT_METADATA["districts"]
    assert CATCHMENT_METADATA["river_system"] == "Brahmaputra"


if __name__ == "__main__":
    test_catchment_polygon_closure()
    print("  [PASS] test_catchment_polygon_closure")
    test_lower_brahmaputra_settlements_in_catchment()
    print("  [PASS] test_lower_brahmaputra_settlements_in_catchment")
    test_out_of_bounds_coordinates_excluded()
    print("  [PASS] test_out_of_bounds_coordinates_excluded")
    test_catchment_metadata_completeness()
    print("  [PASS] test_catchment_metadata_completeness")
    print("All geometry tests passed!")
