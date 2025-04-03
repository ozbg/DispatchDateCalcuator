# app/preflight_logic.py
import logging
from typing import List, Optional

from app.models import ScheduleRequest, PreflightRule, OrderMatchingCriteria
from app.data_manager import get_preflight_rules_data, get_product_info_data
from app.imposing_logic import check_order_criteria # Reuse criteria checking logic
from app.hub_selection import check_dates # Reuse date checking logic

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

DEFAULT_PREFLIGHT_PROFILE_ID = 0 # 0 = Do Not Preflight

def determine_preflight_action(req: ScheduleRequest, product_id: int) -> int:
    """
    Determines the SynergyPreflight profile ID based on matching preflight rules.
    Args:
        req: The incoming ScheduleRequest object.
        product_id: The matched product ID for the order.

    Returns:
        int: The preflight profile ID. Defaults to 0.
    """
    logger.debug(f"Determining preflight action for OrderID: {req.orderId}, ProductID: {product_id}")

    try:
        rules_data = get_preflight_rules_data()
        # Convert raw data list to list of Pydantic models for validation and easier access
        rules: List[PreflightRule] = [PreflightRule(**r) for r in rules_data]
        logger.debug(f"Loaded {len(rules)} preflight rules.")
    except Exception as e:
        logger.error(f"Failed to load or parse preflight rules: {e}. Using default action.")
        return DEFAULT_PREFLIGHT_PROFILE_ID

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

        if rule.orderCriteria and check_order_criteria(rule.orderCriteria, req, product_id, order_product_group):
            logger.info(f"Preflight rule {rule.id} matched. Setting action to Profile ID {rule.preflightProfileId}.")
            return rule.preflightProfileId
        else:
             # Handle cases where rule.orderCriteria is None or the check fails
             if not rule.orderCriteria:
                 logger.debug(f"Rule {rule.id} has no orderCriteria defined.")
             else:
                 logger.debug(f"Rule {rule.id} did not match order criteria.")


    logger.debug("No preflight rules matched. Using default action.")
    return DEFAULT_PREFLIGHT_PROFILE_ID