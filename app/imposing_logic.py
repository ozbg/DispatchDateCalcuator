# app/imposing_logic.py
import logging
from datetime import datetime
from typing import List, Optional

from app.models import ScheduleRequest, OrderMatchingCriteria, ImposingRule
from app.data_manager import get_imposing_rules_data, get_product_info_data
from app.hub_selection import check_dates # Reuse date checking logic

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

DEFAULT_IMPOSING_ACTION = 0 # 0 = No Impose

def check_order_criteria(criteria: OrderMatchingCriteria, req: ScheduleRequest, product_obj: dict) -> bool:
    """
    Checks if the order matches the given criteria.
    Returns True if all defined criteria match, False otherwise.
    """
    if not criteria:
        logger.debug("No orderCriteria defined for rule, matching.")
        return True # No criteria means it always matches this part

    desc_lower = req.description.lower() if req.description else ""
    total_quantity = req.misOrderQTY * req.kinds

    # --- Check each defined criterion ---

    # Quantity
    if criteria.maxQuantity is not None and total_quantity > criteria.maxQuantity:
        logger.debug(f"Criteria Check Failed: Quantity {total_quantity} > maxQuantity {criteria.maxQuantity}")
        return False
    if criteria.minQuantity is not None and total_quantity < criteria.minQuantity:
        logger.debug(f"Criteria Check Failed: Quantity {total_quantity} < minQuantity {criteria.minQuantity}")
        return False

    # Keywords
    if criteria.keywords:
        if not any(kw.lower() in desc_lower for kw in criteria.keywords):
            logger.debug(f"Criteria Check Failed: None of keywords {criteria.keywords} found in description.")
            return False
    if criteria.excludeKeywords:
        if any(kw.lower() in desc_lower for kw in criteria.excludeKeywords):
            logger.debug(f"Criteria Check Failed: Found excluded keyword from {criteria.excludeKeywords} in description.")
            return False

    # Product IDs
    if criteria.productIds:
        # product_obj might be None if fallback was used, handle gracefully
        product_id = product_obj.get("Product_ID") if product_obj else None
        if product_id not in criteria.productIds:
            logger.debug(f"Criteria Check Failed: Product ID {product_id} not in {criteria.productIds}")
            return False
    if criteria.excludeProductIds:
        product_id = product_obj.get("Product_ID") if product_obj else None
        if product_id in criteria.excludeProductIds:
            logger.debug(f"Criteria Check Failed: Product ID {product_id} is in excluded list {criteria.excludeProductIds}")
            return False

    # Product Groups
    if criteria.productGroups:
        product_group = product_obj.get("Product_Group", "").lower() if product_obj else ""
        if not any(pg.lower() == product_group for pg in criteria.productGroups):
            logger.debug(f"Criteria Check Failed: Product Group '{product_group}' not in {criteria.productGroups}")
            return False
    if criteria.excludeProductGroups:
        product_group = product_obj.get("Product_Group", "").lower() if product_obj else ""
        if any(pg.lower() == product_group for pg in criteria.excludeProductGroups):
            logger.debug(f"Criteria Check Failed: Product Group '{product_group}' is in excluded list {criteria.excludeProductGroups}")
            return False

    # Print Types
    if criteria.printTypes:
        if req.printType not in criteria.printTypes:
            logger.debug(f"Criteria Check Failed: Print Type {req.printType} not in {criteria.printTypes}")
            return False

    # If we passed all checks
    logger.debug("All defined orderCriteria matched.")
    return True


def determine_imposing_action(req: ScheduleRequest, product_id: int) -> int:
    """
    Determines the SynergyImpose action based on matching imposing rules.
    Args:
        req: The incoming ScheduleRequest object.
        product_id: The matched product ID for the order.

    Returns:
        int: The imposing action (0, 1, or 2). Defaults to 0.
    """
    logger.debug(f"Determining imposing action for OrderID: {req.orderId}, ProductID: {product_id}")

    try:
        rules_data = get_imposing_rules_data()
        # Convert raw data list to list of Pydantic models for validation and easier access
        rules: List[ImposingRule] = [ImposingRule(**r) for r in rules_data]
        logger.debug(f"Loaded {len(rules)} imposing rules.")
    except Exception as e:
        logger.error(f"Failed to load or parse imposing rules: {e}. Using default action.")
        return DEFAULT_IMPOSING_ACTION

    # Sort rules by priority (highest first)
    rules.sort(key=lambda x: x.priority, reverse=True)

    # Get the product object details needed for criteria checking
    all_product_info = get_product_info_data()
    product_obj = all_product_info.get(str(product_id)) # Product info uses string keys

    for rule in rules:
        logger.debug(f"Evaluating imposing rule ID: {rule.id}, Priority: {rule.priority}")

        if not rule.enabled:
            logger.debug(f"Skipping rule {rule.id} (disabled).")
            continue

        # Check date validity (reusing check_dates from hub_selection)
        if not check_dates(rule):
             logger.debug(f"Skipping rule {rule.id} (outside valid date range).")
             continue

        # Check if order criteria match
        if check_order_criteria(rule.orderCriteria, req, product_obj):
            logger.info(f"Imposing rule {rule.id} matched. Setting action to {rule.imposingAction}.")
            return rule.imposingAction
        else:
             logger.debug(f"Rule {rule.id} did not match order criteria.")


    logger.debug("No imposing rules matched. Using default action.")
    return DEFAULT_IMPOSING_ACTION