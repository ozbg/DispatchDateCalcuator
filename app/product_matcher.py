#product_matcher.py
#This module contains the logic for matching product IDs based on description and determining the grain direction based on orientation, width, height, and description.
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def match_product_id(description: str, product_keywords: list) -> int:
    logger.debug(f"Matching product ID for description: {description}")
    desc_lower = description.lower()

    for item in product_keywords:
        product_id = item["Product_ID"]

        # 1. Match all
        if not match_all(item.get("Match_All", []), desc_lower):
            logger.debug(f"Description '{description}' did not match all keywords for product ID {product_id}.")
            continue

        # 2. Exclude all
        if not exclude_all(item.get("Exclude_All", []), desc_lower):
            logger.debug(f"Description '{description}' excluded by keywords for product ID {product_id}.")
            continue

        # 3. Match any
        if not match_any(item.get("Match_Any", []), desc_lower):
            logger.debug(f"Description '{description}' did not match any keywords for product ID {product_id}.")
            continue

        logger.debug(f"Matched product ID {product_id} for description='{description}'.")
        return product_id

    logger.debug(f"No matching product ID found for description: {description}")
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

    # Each sub-list represents an OR group. At least one word from each group must be present.
    for sublist in list_of_lists:
        if not any(s.lower() in desc_lower for s in sublist):
            return False
    return True

def determine_grain_direction(orientation: str, width: float, height: float, description: str):
    logger.debug(f"Determining grain direction for orientation: {orientation}, width: {width}, height: {height}, description: {description}")
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

    logger.debug(f"Grain direction determined: {grain} (ID={grain_id})")
    return grain, grain_id
