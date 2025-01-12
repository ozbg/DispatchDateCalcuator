from app.schedule_logic import find_next_best

def test_find_next_best_single_match():
        cmyk_hubs = [
            {"State": "vic", "Next_Best": ["nsw", "qld"]},
            {"State": "nsw", "Next_Best": ["vic", "qld"]},
            {"State": "qld", "Next_Best": ["vic", "nsw"]}
        ]
        product_hubs_lower = ["vic", "nsw"]
        result = find_next_best("nsw", product_hubs_lower, cmyk_hubs)
        assert result == "vic"

def test_find_next_best_no_match():
        cmyk_hubs = [
            {"State": "vic", "Next_Best": ["nsw", "qld"]},
            {"State": "nsw", "Next_Best": ["vic", "qld"]},
            {"State": "qld", "Next_Best": ["vic", "nsw"]}
        ]
        product_hubs_lower = ["wa"]
        result = find_next_best("nsw", product_hubs_lower, cmyk_hubs)
        assert result == "wa"

def test_find_next_best_fallback():
        cmyk_hubs = [
            {"State": "vic", "Next_Best": ["nsw", "qld"]},
            {"State": "nsw", "Next_Best": ["qld"]},
            {"State": "qld", "Next_Best": ["vic", "nsw"]}
        ]
        product_hubs_lower = ["sa"]
        result = find_next_best("nsw", product_hubs_lower, cmyk_hubs)
        assert result == "sa"

def test_find_next_best_multiple_matches():
        cmyk_hubs = [
            {"State": "vic", "Next_Best": ["nsw", "qld"]},
            {"State": "nsw", "Next_Best": ["vic", "qld"]},
            {"State": "qld", "Next_Best": ["vic", "nsw"]}
        ]
        product_hubs_lower = ["qld", "vic"]
        result = find_next_best("nsw", product_hubs_lower, cmyk_hubs)
        assert result == "vic"

def test_find_next_best_empty_next_best():
        cmyk_hubs = [
            {"State": "vic", "Next_Best": ["nsw", "qld"]},
            {"State": "nsw", "Next_Best": []},
            {"State": "qld", "Next_Best": ["vic", "nsw"]}
        ]
        product_hubs_lower = ["vic", "nsw"]
        result = find_next_best("nsw", product_hubs_lower, cmyk_hubs)
        assert result == "vic"

   