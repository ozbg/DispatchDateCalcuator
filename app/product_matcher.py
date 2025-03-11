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
    """
    Determines the grain direction for a given order based on orientation, dimensions, and BC size conditions.

    If the product meets BC size conditions:
      - Trust the given grain setting.
      - Adjust the long and short edges to match the expected grain.

    If the product does NOT meet BC size conditions:
      - The grain is set to "Either".
      - The given orientation is used without correction.

    Parameters:
    - orientation (str): Expected orientation ("portrait", "landscape", or other).
    - width (float): Incoming width of the product.
    - height (float): Incoming height of the product.
    - description (str): Text description of the product.

    Returns:
    - grain (str): The final grain direction ("Vertical", "Horizontal", or "Either").
    - grain_id (int): The grain direction ID (3 = Vertical, 2 = Horizontal, 1 = Either).
    """

    logger.debug(f"Determining grain direction for orientation: {orientation}, width: {width}, height: {height}, description: {description}")

    # BC size thresholds
    BC_LONG = 100
    BC_SHORT = 65
    desc_lower = description.lower()

    # Determine if product meets BC size conditions
    is_bc_size = (max(width, height) <= BC_LONG and min(width, height) <= BC_SHORT) or ("bc" in desc_lower)

    # Ensure valid orientation
    valid_orientations = ["portrait", "landscape"]
    orientation = orientation.lower()  # Normalize casing

    if orientation not in valid_orientations:
        logger.warning(f"Unexpected orientation '{orientation}'. Inferring from dimensions.")
        if height > width:
            orientation = "portrait"
        elif width > height:
            orientation = "landscape"
        else:
            # Square case, default to portrait
            orientation = "portrait"

    # Assign long and short edges based on orientation
    if orientation == "portrait":
        long_edge = height
        short_edge = width
        grain = "Vertical"
        grain_id = 3
    elif orientation == "landscape":
        long_edge = width
        short_edge = height
        grain = "Horizontal"
        grain_id = 2
    else:
        # Fallback (should not be hit due to earlier correction)
        long_edge = max(width, height)
        short_edge = min(width, height)
        grain = "Either"
        grain_id = 1

    # If it's BC size, trust the grain setting
    if is_bc_size:
        logger.debug("BC size detected. Trusting grain setting and adjusting size accordingly.")
        # No changes to grain, but ensure size alignment
        if grain == "Vertical":
            long_edge, short_edge = max(width, height), min(width, height)
        elif grain == "Horizontal":
            long_edge, short_edge = max(width, height), min(width, height)
    else:
        # Not BC size: Default to "Either" grain direction
        logger.debug("Not BC size. Setting grain direction to Either.")
        grain = "Either"
        grain_id = 1

    logger.debug(f"Final grain direction: {grain} (ID={grain_id}), final orientation: {orientation}, long edge: {long_edge}, short edge: {short_edge}")

    return grain, grain_id
