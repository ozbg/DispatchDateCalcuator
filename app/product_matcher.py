import logging

logger = logging.getLogger("scheduler")

def match_product_id(description: str, product_keywords: list) -> int:
    """
    Attempt to find a matching Product_ID based on 'description'.
    Follows the 'Match_All', 'Exclude_All', and 'Match_Any' approach.
    Returns the product ID or None if no match is found.
    """
    desc_lower = description.lower()

    for item in product_keywords:
        product_id = item["Product_ID"]

        # 1. Match all
        if not match_all(item.get("Match_All", []), desc_lower):
            continue

        # 2. Exclude all
        if not exclude_all(item.get("Exclude_All", []), desc_lower):
            continue

        # 3. Match any
        if not match_any(item.get("Match_Any", []), desc_lower):
            continue

        logger.debug(f"Matched product ID {product_id} for description='{description}'.")
        return product_id

    return None

def match_all(keywords, desc_lower):
    for kw in keywords:
        if kw.lower() not in desc_lower:
            return False
    return True

def exclude_all(keywords, desc_lower):
    for kw in keywords:
        if kw.lower() in desc_lower:
            return False
    return True

def match_any(list_of_lists, desc_lower):
    if not list_of_lists:
        # If no 'Match_Any', we skip
        return True

    # Each sub-list represents an OR group. If at least one group is fully matched, return True.
    for sublist in list_of_lists:
        if all(s.lower() in desc_lower for s in sublist):
            return True
    return False

def determine_grain_direction(orientation: str, width: float, height: float, description: str):
    """
    - portrait => grain=Vertical (ID=3)
    - landscape or square => grain=Horizontal (ID=2)
    - if not BC size => grain=Either (ID=1)
    """
    if orientation.lower() == "portrait":
        grain = "Vertical"
        grain_id = 3
        long_edge = height
        short_edge = width
    else:
        grain = "Horizontal"
        grain_id = 2
        long_edge = width
        short_edge = height

    # BC thresholds
    BC_LONG = 92
    BC_SHORT = 57
    desc_lower = description.lower()

    if (long_edge <= BC_LONG and short_edge <= BC_SHORT) or ("bc" in desc_lower):
        # Keep the previously assigned grain
        pass
    else:
        grain = "Either"
        grain_id = 1

    return grain, grain_id
