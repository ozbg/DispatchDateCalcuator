# app/preflight_logic.py
import logging
from typing import List, Optional, Tuple

from app.models import ScheduleRequest, PreflightRule, OrderMatchingCriteria, PreflightProfile
from app.data_manager import get_preflight_rules_data, get_product_info_data, get_preflight_profiles_data
from app.imposing_logic import check_order_criteria # Reuse criteria checking logic
from app.hub_selection import check_dates # Reuse date checking logic

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

DEFAULT_PREFLIGHT_PROFILE_ID = 0 # 0 = Do Not Preflight
DEFAULT_PREFLIGHT_PROFILE_NAME = "NoPreflight" # Default name

def determine_preflight_action(req: ScheduleRequest, product_id: int) -> Tuple[int, Optional[str]]:
    """
    Determines the SynergyPreflight profile ID and name based on matching preflight rules.
    Args:
        req: The incoming ScheduleRequest object.
        product_id: The matched product ID for the order.

    Returns:
        Tuple[int, Optional[str]]: The preflight profile ID and its corresponding name.
                                   Defaults to (0, "NoPreflight").
    """
    logger.debug(f"Determining preflight action for OrderID: {req.orderId}, ProductID: {product_id}")

    try:
        rules_data = get_preflight_rules_data()
        profiles_data = get_preflight_profiles_data() # Load profiles to get names
        # Convert raw data list to list of Pydantic models for validation and easier access
        rules: List[PreflightRule] = [PreflightRule(**r) for r in rules_data]
        profiles: List[PreflightProfile] = [PreflightProfile(**p) for p in profiles_data]
        profile_map = {p.id: p for p in profiles} # Create a map for easy lookup
        logger.debug(f"Loaded {len(rules)} preflight rules and {len(profiles)} profiles.")
    except Exception as e:
        logger.error(f"Failed to load or parse preflight rules/profiles: {e}. Using default action.")
        return DEFAULT_PREFLIGHT_PROFILE_ID, DEFAULT_PREFLIGHT_PROFILE_NAME

    # Sort rules by priority (highest first)
    rules.sort(key=lambda x: x.priority, reverse=True)
    all_product_info = get_product_info_data()
    product_obj = all_product_info.get(str(product_id)) # Product info uses string keys
    order_product_group: Optional[str] = product_obj.get("Product_Group") if product_obj else None
    if not product_obj:
        logger.warning(f"Product object not found for Product ID {product_id} when checking preflight rules. Product Group checks may fail.")

    for rule in rules:
        logger.debug(f"Evaluating preflight rule ID: {rule.id}, Priority: {rule.priority}")

        if not rule.enabled:
            logger.debug(f"Skipping rule {rule.id} (disabled).")
            continue

        if not check_dates(rule):
             logger.debug(f"Skipping rule {rule.id} (outside valid date range).")
             continue

        # Check criteria match
        criteria_match = False
        if rule.orderCriteria:
            criteria_match = check_order_criteria(rule.orderCriteria, req, product_id, order_product_group)
        else:
            # If a rule has no criteria, it matches any order (unless disabled or out of date)
            criteria_match = True
            logger.debug(f"Rule {rule.id} has no orderCriteria defined, considering it a match.")

        if criteria_match:
            matched_profile_id = rule.preflightProfileId
            matched_profile = profile_map.get(matched_profile_id)
            if matched_profile:
                profile_name = matched_profile.preflightProfileName
                logger.info(f"Preflight rule {rule.id} matched. Setting action to Profile ID {matched_profile_id} (Name: {profile_name}).")
                return matched_profile_id, profile_name
            else:
                logger.warning(f"Preflight rule {rule.id} matched, but Profile ID {matched_profile_id} not found in profiles data. Returning ID with default name.")
                # Return the ID specified by the rule, but indicate the name is missing/default
                return matched_profile_id, f"UnknownProfile_{matched_profile_id}" # Or return None, or DEFAULT_PREFLIGHT_PROFILE_NAME
        else:
            logger.debug(f"Rule {rule.id} did not match order criteria.")


    logger.debug("No preflight rules matched. Using default action.")
    # Return default ID and Name
    default_profile = profile_map.get(DEFAULT_PREFLIGHT_PROFILE_ID)
    default_name = default_profile.preflightProfileName if default_profile else DEFAULT_PREFLIGHT_PROFILE_NAME
    return DEFAULT_PREFLIGHT_PROFILE_ID, default_name