import pytest
from app.product_matcher import match_product_id

def test_match_product_id_success():
    description = "This product has feature alpha and beta."
    product_keywords = [
        {
            "Product_ID": 1,
            "Match_All": ["alpha", "beta"],
            "Exclude_All": [],
            "Match_Any": []
        }
    ]
    assert match_product_id(description, product_keywords) == 1 # Test match all keywords

def test_match_product_id_missing_match_all():
    description = "This product has feature alpha."
    product_keywords = [
        {
            "Product_ID": 1,
            "Match_All": ["feature alpha", "beta"],
            "Exclude_All": [],
            "Match_Any": []
        }
    ]
    assert match_product_id(description, product_keywords) is None # Test missing match all keywords

def test_match_product_id_excluded_keyword():
    description = "This product has feature alpha and gamma."
    product_keywords = [
        {
            "Product_ID": 1,
            "Match_All": ["feature alpha"],
            "Exclude_All": ["gamma"],
            "Match_Any": []
        }
    ]
    assert match_product_id(description, product_keywords) is None # Test exclude all keyword

def test_match_product_id_match_any_success():
    description = "This product has feature alpha."
    product_keywords = [
        {
            "Product_ID": 1,
            "Match_All": ["feature", "alpha"],
            "Exclude_All": [],
            "Match_Any": [["this"], ["gamma", "has"]]
        }
    ]
    assert match_product_id(description, product_keywords) == 1 # Test match any keyword with multiple groups

    product_keywords[0]["Match_Any"] = [["alpha"], ["has", "rad ripper"]]
    assert match_product_id(description, product_keywords) == 1 # Test match any keyword with multiple groups

    product_keywords[0]["Match_Any"] = [["alpha"], ["gamma", "missing"]]
    assert match_product_id(description, product_keywords) is None # Should fail because "missing" is not in the description

def test_match_product_id_no_matching_product():
    description = "Unknown product description."
    product_keywords = [
        {
            "Product_ID": 1,
            "Match_All": ["feature alpha"],
            "Exclude_All": [],
            "Match_Any": []
        }
    ]
    assert match_product_id(description, product_keywords) is None