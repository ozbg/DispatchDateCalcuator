from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path
import json
import logging

from app.models import HubSelectionRule, HubSizeConstraint, OrderMatchingCriteria

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------
# 1) LOAD AND HELPER FUNCTIONS
# ------------------------------------------------------------------------

def load_hub_rules() -> List[HubSelectionRule]:
    """
    Load hub selection rules from JSON file.
    Expects a structure like:
    {
      "rules": [
        {
          "id": "rule1",
          "hubId": "ABC",
          "description": "Some rule",
          "priority": 10,
          "enabled": true,
          "sizeConstraints": {
              "maxWidth": 650,
              "maxHeight": 450
          },
          "orderCriteria": {
              "maxQuantity": 300,
              "productIds": [1001, 1002],
              "keywords": ["postcard", "flyer"]
          },
          "startDate": "2025-01-01",
          "endDate": "2025-12-31"
        }
      ]
    }
    """
    rules_path = Path("data/hub_rules.json")
    if not rules_path.exists():
        return []

    with open(rules_path, "r") as f:
        data = json.load(f)
        rule_list = []
        for r in data.get("rules", []):
            # Build the sub-objects carefully
            size_c = None
            if "sizeConstraints" in r and r["sizeConstraints"]:
                size_c = HubSizeConstraint(
                    maxWidth=r["sizeConstraints"].get("maxWidth"),
                    maxHeight=r["sizeConstraints"].get("maxHeight")
                )

            order_c = None
            if "orderCriteria" in r and r["orderCriteria"]:
                order_c = OrderMatchingCriteria(
                    maxQuantity=r["orderCriteria"].get("maxQuantity"),
                    productIds=r["orderCriteria"].get("productIds"),
                    keywords=r["orderCriteria"].get("keywords")
                )

            rule_obj = HubSelectionRule(
                id=r["id"],
                hubId=r["hubId"],
                description=r.get("description", ""),
                priority=r.get("priority", 0),
                enabled=r.get("enabled", False),
                sizeConstraints=size_c,
                orderCriteria=order_c,
                startDate=r.get("startDate"),
                endDate=r.get("endDate")
            )
            rule_list.append(rule_obj)
        return rule_list


def check_size_constraints(width: float, height: float, constraints: HubSizeConstraint) -> bool:
    """
    Check if dimensions fit within constraints in either orientation.
    Returns True if dimensions are acceptable, False if they exceed constraints.
    """
    if not constraints or not constraints.maxWidth or not constraints.maxHeight:
        return True

    dim1, dim2 = width, height
    max1, max2 = constraints.maxWidth, constraints.maxHeight

    fits_normal = (dim1 <= max1 and dim2 <= max2)
    fits_rotated = (dim1 <= max2 and dim2 <= max1)

    if fits_normal or fits_rotated:
        logger.debug(f"Size {width}x{height} acceptable within max {max1}x{max2}")
        return True

    logger.debug(f"Size {width}x{height} exceeds limits {max1}x{max2}")
    return False


def check_dates(rule: HubSelectionRule) -> bool:
    """Check if a rule is valid for the current date (if start/end are provided)."""
    if not rule.startDate and not rule.endDate:
        return True

    current_date = datetime.now().date()

    if rule.startDate:
        start = datetime.strptime(rule.startDate, "%Y-%m-%d").date()
        if current_date < start:
            return False

    if rule.endDate:
        end = datetime.strptime(rule.endDate, "%Y-%m-%d").date()
        if current_date > end:
            return False

    return True


def get_equipment_data() -> Dict:
    """
    Load equipment and process data for hubs from hub_rules.json
    (assuming structure has an "equipment" section).
    """
    rules_path = Path("data/hub_rules.json")
    if not rules_path.exists():
        return {}
    with open(rules_path, "r") as f:
        data = json.load(f)
        return data.get("equipment", {})


def check_equipment_requirements(hub_id: str, required_equipment: List[str],
                                 required_processes: List[str]) -> bool:
    """
    Check if a hub has required equipment and processes based on "equipment" data.
    """
    equipment_data = get_equipment_data()
    hub_equipment = equipment_data.get(hub_id, {})

    if required_equipment:
        available_equipment = hub_equipment.get("equipment", [])
        if not all(eq in available_equipment for eq in required_equipment):
            return False

    if required_processes:
        available_processes = hub_equipment.get("processes", [])
        if not all(proc in available_processes for proc in required_processes):
            return False

    return True


# ------------------------------------------------------------------------
# 2) FIND NEXT BEST HUB
# ------------------------------------------------------------------------

def find_next_best_hub(
    current_hub: str,
    available_hubs: List[str],
    delivers_to_state: str,
    cmyk_hubs: List[dict]
) -> str:
    """
    Find the "next best" hub from the CMYK hubs list for the given state.
    cmyk_hubs structure might look like:
        [
          {
            "State": "NY",
            "Next_Best": ["NJHUB","PAHUB"]
          },
          {
            "State": "CA",
            "Next_Best": ["AZHUB","COHUB"]
          }
        ]
    If none is found, fallback to the first in available_hubs.
    """
    # Find the hub entry for current state
    for hub in cmyk_hubs:
        if hub["State"].lower() == delivers_to_state.lower():
            # Check each next best option
            for next_hub in hub["Next_Best"]:
                if next_hub.lower() in [h.lower() for h in available_hubs]:
                    logger.debug(f"Found next best hub: {next_hub}")
                    return next_hub.lower()

    # Fallback to first available hub if no next best found
    if available_hubs:
        logger.debug(f"No valid next best hub found, using first available: {available_hubs[0]}")
        return available_hubs[0].lower()
    else:
        # If there are no available hubs at all, just return current
        logger.debug("No available hubs provided, returning current hub.")
        return current_hub.lower()


# ------------------------------------------------------------------------
# 3) VALIDATE HUB RULES (SINGLE, CORRECTED VERSION)
# ------------------------------------------------------------------------

def validate_hub_rules(
    initial_hub: str,
    available_hubs: List[str],
    delivers_to_state: str,
    current_hub: str,
    description: str,
    width: float,
    height: float,
    quantity: int,
    product_id: int,
    product_group: str,
    cmyk_hubs: List[dict]
) -> str:
    """
    Validates hub rules (one hub at a time) and returns the appropriate hub.
    1) We check size constraints first (independent).
    2) Then check the orderCriteria as a group (AND logic):
       - If all specified criteria match (e.g. quantity >= maxQuantity, productID in the list,
         any listed keyword found in description), then we exclude the hub.
    3) If no rule excludes the hub, we keep it.
    """
    logger.debug(f"Validating hub rules for initial hub: {initial_hub}")

    rules = load_hub_rules()
    # Highest priority first
    rules.sort(key=lambda x: x.priority, reverse=True)

    for rule in rules:
        if not rule.enabled:
            continue

        # Must match the same hubId in the rule
        if rule.hubId.lower() != initial_hub.lower():
            continue

        # Check date validity
        if not check_dates(rule):
            continue

        logger.debug(f"Checking rule: {rule.id} - {rule.description}")

        # --------------------------
        # 1) SIZE CONSTRAINTS FIRST
        # --------------------------
        if rule.sizeConstraints:
            if not check_size_constraints(width, height, rule.sizeConstraints):
                logger.debug(f"Hub {initial_hub} excluded by rule {rule.id}: "
                             f"size {width}x{height} fails constraints "
                             f"{rule.sizeConstraints.maxWidth}x{rule.sizeConstraints.maxHeight}")
                return find_next_best_hub(initial_hub, available_hubs, delivers_to_state, cmyk_hubs)
            else:
                logger.debug(f"Hub {initial_hub} passed size check for rule {rule.id}")

        # --------------------------
        # 2) ORDER CRITERIA (AND logic)
        #    If all specified sub-criteria match, exclude the hub
        # --------------------------
        if rule.orderCriteria:
            criteria_defined = False
            all_conditions_met = True

            # maxQuantity => exclude if quantity >= maxQuantity
            if rule.orderCriteria.maxQuantity is not None:
                criteria_defined = True
                qty_match = (quantity >= rule.orderCriteria.maxQuantity)
                all_conditions_met &= qty_match

            # productIds => exclude if product_id is in the list
            if rule.orderCriteria.productIds:
                criteria_defined = True
                pid_match = (product_id in rule.orderCriteria.productIds)
                all_conditions_met &= pid_match

            # keywords => exclude if any of them appear in the description
            if rule.orderCriteria.keywords:
                criteria_defined = True
                kw_match = any(kw.lower() in description.lower() for kw in rule.orderCriteria.keywords)
                all_conditions_met &= kw_match

            # If we actually had criteria and all matched => exclude
            if criteria_defined and all_conditions_met:
                logger.debug(f"Hub {initial_hub} excluded by rule {rule.id}: matched all order criteria.")
                return find_next_best_hub(initial_hub, available_hubs, delivers_to_state, cmyk_hubs)

        # If we get here, this rule did not exclude the hub
        logger.debug(f"Hub {initial_hub} not excluded by rule {rule.id}")

    # If no rule triggered an exclusion, return the initial hub
    logger.debug(f"Hub {initial_hub} passed all rules")
    return initial_hub


# ------------------------------------------------------------------------
# 4) CHOOSE PRODUCTION HUB (optional example usage)
# ------------------------------------------------------------------------

def choose_production_hub(
    available_hubs: List[str],
    delivers_to_state: str,
    current_hub: str,
    description: str,
    width: float,
    height: float,
    quantity: int,
    product_id: int,
    product_group: str
) -> str:
    """
    Example function that uses the loaded rules to pick among multiple hubs.
    This code will attempt to remove hubs that fail certain constraints 
    and then pick among the remaining. (Optional usage, can be tailored further.)
    """
    logger.debug(f"Starting hub selection with available hubs: {available_hubs}")

    # Create set of valid hubs from available hubs
    valid_hubs = set(available_hubs)

    # Load and sort rules by priority (highest first)
    rules = load_hub_rules()
    rules.sort(key=lambda x: x.priority, reverse=True)

    for rule in rules:
        # Only apply enabled rules that match a hub in our valid set
        if not rule.enabled or rule.hubId not in valid_hubs:
            continue

        # Also skip if rule is not valid for current date
        if not check_dates(rule):
            continue

        should_remove = False

        # Size constraints: remove if not satisfied
        if rule.sizeConstraints:
            if not check_size_constraints(width, height, rule.sizeConstraints):
                should_remove = True

        # (You could add more checks here for quantity, productID, etc., 
        #  if you need to filter out hubs entirely rather than do a "redirect".)

        if should_remove:
            valid_hubs.discard(rule.hubId)
            logger.debug(f"Removed hub {rule.hubId} due to rule {rule.id}")

    logger.debug(f"Remaining valid hubs after applying rules: {valid_hubs}")

    # If the current hub is still valid, keep it
    if current_hub in valid_hubs:
        logger.debug(f"Current hub {current_hub} remains valid")
        return current_hub

    # Otherwise, pick any valid hub or fallback
    if valid_hubs:
        chosen = next(iter(valid_hubs))
        logger.debug(f"Chose first valid hub: {chosen}")
        return chosen

    # If no valid hubs remain, fallback
    logger.error("No valid hubs found; returning current hub as last resort.")
    return current_hub