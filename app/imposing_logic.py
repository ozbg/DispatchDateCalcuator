# app/imposing_logic.py

import logging
from typing import List, Optional

from app.models import ScheduleRequest, OrderMatchingCriteria, ImposingRule
from app.data_manager import get_imposing_rules_data, get_product_info_data
from app.hub_selection import check_dates # Reuse date checking logic

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

DEFAULT_IMPOSING_ACTION = 0 # 0 = No Impose

# MODIFIED: Updated function signature
def check_order_criteria(criteria: OrderMatchingCriteria, req: ScheduleRequest, order_product_id: Optional[int], product_group: Optional[str]) -> bool:
    """
    Checks if the order matches the given criteria using the directly provided product ID and group.
    Returns True if all defined criteria match, False otherwise.
    """
    if not criteria:
        logger.debug("No orderCriteria defined for rule, matching.")
        return True # No criteria means it always matches this part

    desc_lower = req.description.lower() if req.description else ""
    total_quantity = req.misOrderQTY * req.kinds

    # --- Check each defined criterion ---

    # Quantity (No change)
    if criteria.maxQuantity is not None and total_quantity > criteria.maxQuantity:
        logger.debug(f"Criteria Check Failed: Quantity {total_quantity} > maxQuantity {criteria.maxQuantity}")
        return False
    if criteria.minQuantity is not None and total_quantity < criteria.minQuantity:
        logger.debug(f"Criteria Check Failed: Quantity {total_quantity} < minQuantity {criteria.minQuantity}")
        return False

    # Keywords (No change)
    if criteria.keywords:
        if not any(kw.lower() in desc_lower for kw in criteria.keywords):
            logger.debug(f"Criteria Check Failed: None of keywords {criteria.keywords} found in description.")
            return False
    if criteria.excludeKeywords:
        if any(kw.lower() in desc_lower for kw in criteria.excludeKeywords):
            logger.debug(f"Criteria Check Failed: Found excluded keyword from {criteria.excludeKeywords} in description.")
            return False

    # --- MODIFIED: Product IDs check uses the passed integer 'order_product_id' ---
    if criteria.productIds:
        # Pydantic ensures criteria.productIds contains integers
        if order_product_id is None or order_product_id not in criteria.productIds:
            logger.debug(f"Criteria Check Failed: Order Product ID '{order_product_id}' not in required list {criteria.productIds}")
            return False
        else:
             logger.debug(f"Criteria Check Passed: Order Product ID '{order_product_id}' is in required list {criteria.productIds}")

    if criteria.excludeProductIds:
        # Pydantic ensures criteria.excludeProductIds contains integers
        if order_product_id is not None and order_product_id in criteria.excludeProductIds:
            logger.debug(f"Criteria Check Failed: Order Product ID '{order_product_id}' is in excluded list {criteria.excludeProductIds}")
            return False
        else:
             logger.debug(f"Criteria Check Passed: Order Product ID '{order_product_id}' is not in excluded list {criteria.excludeProductIds}")
    # --- End Product IDs modification ---

    # --- MODIFIED: Product Groups check uses the passed string 'product_group' ---
    product_group_lower = product_group.lower() if product_group else ""
    if criteria.productGroups:
        # Convert criteria product groups to lowercase for comparison
        criteria_groups_lower = [pg.lower() for pg in criteria.productGroups]
        if product_group_lower not in criteria_groups_lower:
            logger.debug(f"Criteria Check Failed: Product Group '{product_group_lower}' not in required list {criteria.productGroups}")
            return False
    if criteria.excludeProductGroups:
        # Convert criteria excluded product groups to lowercase for comparison
        criteria_exclude_groups_lower = [pg.lower() for pg in criteria.excludeProductGroups]
        if product_group_lower in criteria_exclude_groups_lower:
            logger.debug(f"Criteria Check Failed: Product Group '{product_group_lower}' is in excluded list {criteria.excludeProductGroups}")
            return False
    # --- End Product Groups modification ---

    # Print Types (No change)
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
        product_id: The matched product ID (int) for the order.

    Returns:
        int: The imposing action (0, 1, or 2). Defaults to 0.
    """
    logger.debug(f"Determining imposing action for OrderID: {req.orderId}, ProductID: {product_id}")

    try:
        rules_data = get_imposing_rules_data()
        rules: List[ImposingRule] = [ImposingRule(**r) for r in rules_data]
        logger.debug(f"Loaded {len(rules)} imposing rules.")
    except Exception as e:
        logger.error(f"Failed to load or parse imposing rules: {e}. Using default action.")
        return DEFAULT_IMPOSING_ACTION

    rules.sort(key=lambda x: x.priority, reverse=True)

    # --- MODIFIED: Fetch product group needed for the check function ---
    all_product_info = get_product_info_data()
    product_obj = all_product_info.get(str(product_id)) # Still need product_obj for group
    order_product_group: Optional[str] = product_obj.get("Product_Group") if product_obj else None
    if not product_obj:
        logger.warning(f"Product object not found for Product ID {product_id} when checking imposing rules. Product Group checks may fail.")
    # --- End modification ---

    for rule in rules:
        logger.debug(f"Evaluating imposing rule ID: {rule.id}, Priority: {rule.priority}")

        if not rule.enabled:
            logger.debug(f"Skipping rule {rule.id} (disabled).")
            continue

        if not check_dates(rule):
             logger.debug(f"Skipping rule {rule.id} (outside valid date range).")
             continue

        # --- MODIFIED: Pass the integer product_id and fetched product_group ---
        if check_order_criteria(rule.orderCriteria, req, product_id, order_product_group):
            logger.info(f"Imposing rule {rule.id} matched. Setting action to {rule.imposingAction}.")
            return rule.imposingAction
        else:
             logger.debug(f"Rule {rule.id} did not match order criteria.")


    logger.debug("No imposing rules matched. Using default action.")
    return DEFAULT_IMPOSING_ACTION