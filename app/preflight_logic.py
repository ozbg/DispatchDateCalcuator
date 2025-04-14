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
DEFAULT_PREFLIGHT_PROFILE_ID = 0 # 0 = Do Not Preflight

# MODIFIED: Added chosen_hub argument
def determine_preflight_action(req: ScheduleRequest, product_id: int, chosen_hub: str) -> Tuple[int, Optional[str]]:
    """
    Determines the SynergyPreflight profile ID based on matching preflight rules.
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
             continue # Correct indentation

        # Check criteria match
        criteria_match = False
        if rule.orderCriteria:
            # MODIFIED: Pass chosen_hub here
            if check_order_criteria(rule.orderCriteria, req, product_id, order_product_group, chosen_hub):
                criteria_match = True
            else:
                logger.debug(f"Rule {rule.id} did not match order criteria.")
                continue # Skip to next rule if criteria defined but don't match
        else:
            # No criteria defined, so it matches this part
            criteria_match = True
            logger.debug(f"Rule {rule.id} has no orderCriteria defined, considering it a match.")

        # If criteria matched (or none were defined)
        if criteria_match:
            logger.info(f"Preflight rule {rule.id} matched. Setting profile ID to {rule.preflightProfileId}.")
            matched_profile = profile_map.get(rule.preflightProfileId)
            if matched_profile:
                return matched_profile.id, matched_profile.preflightProfileName
            else:
                logger.warning(f"Preflight rule {rule.id} matched, but Profile ID {rule.preflightProfileId} not found in profiles data. Returning ID with default name.")
                # Return the ID specified by the rule, but indicate the name is missing/default
                return rule.preflightProfileId, f"UnknownProfile_{rule.preflightProfileId}"


    logger.debug("No preflight rules matched. Using default action.")
    # Return default ID and Name
    default_profile = profile_map.get(DEFAULT_PREFLIGHT_PROFILE_ID)
    # Use a fixed default name string for consistency if profile 0 isn't found
    default_name = default_profile.preflightProfileName if default_profile else "NoPreflight"
    return DEFAULT_PREFLIGHT_PROFILE_ID, default_name