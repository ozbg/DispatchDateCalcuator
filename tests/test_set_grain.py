import pytest
from app.product_matcher import match_product_id, determine_grain_direction

# BC size requries grain Vertical or Horizontal
# Non BC size must be either
# BC AND..  Portrait = Vertical, Horizontal = Landscape, Square = Landscape

# BC thresholds 92 x 57
    
# 1 = Either, 2 = Horizontal, 3 = Vertical
# orinetation is fed via API (based on preflight result)

def test_determine_grain_direction_portrait():
        orientation = "portrait"
        width = 50
        height = 90
        description = "Standard product"
        grain, grain_id = determine_grain_direction(orientation, width, height, description)
        assert grain == "Vertical"
        assert grain_id == 3

def test_determine_grain_direction_landscape():
        orientation = "landscape"
        width = 90
        height = 50
        description = "Standard product"
        grain, grain_id = determine_grain_direction(orientation, width, height, description)
        assert grain == "Horizontal"
        assert grain_id == 2

def test_determine_grain_direction_bc_thresholds():
        orientation = "portrait"
        width = 50
        height = 90
        description = "Standard product"
        grain, grain_id = determine_grain_direction(orientation, width, height, description)
        assert grain == "Vertical"
        assert grain_id == 3

        width = 93
        height = 58
        grain, grain_id = determine_grain_direction(orientation, width, height, description)
        assert grain == "Either"
        assert grain_id == 1

def test_determine_grain_direction_bc_in_description():
        orientation = "landscape"
        width = 100
        height = 50
        description = "BC product"
        grain, grain_id = determine_grain_direction(orientation, width, height, description)
        assert grain == "Horizontal"
        assert grain_id == 2