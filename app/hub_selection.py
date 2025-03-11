from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path
import json
import logging

from app.models import HubSelectionRule, HubSizeConstraint, OrderMatchingCriteria

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

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
    logger.debug(f"Attempting to load hub rules from file: {rules_path}")
    if not rules_path.exists():
        logger.debug("Hub rules file does not exist; returning empty list")
        return []

    with open(rules_path, "r") as f:
        data = json.load(f)
        rule_list = []
        rules_data = data.get("rules", [])
        logger.debug(f"Found {len(rules_data)} rule(s) in the file")
        for r in rules_data:
            logger.debug(f"Processing rule with id: {r.get('id')}")
            # Build the sub-objects carefully
            size_c = None
            if "sizeConstraints" in r and r["sizeConstraints"]:
                size_c = HubSizeConstraint(
                    maxWidth=r["sizeConstraints"].get("maxWidth"),
                    maxHeight=r["sizeConstraints"].get("maxHeight")
                )
                logger.debug(f"Rule {r.get('id')} - sizeConstraints set to: {r['sizeConstraints']}")

            order_c = None
            if "orderCriteria" in r and r["orderCriteria"]:
                order_c = OrderMatchingCriteria(
                    maxQuantity=r["orderCriteria"].get("maxQuantity"),
                    productIds=r["orderCriteria"].get("productIds"),
                    keywords=r["orderCriteria"].get("keywords")
                )
                logger.debug(f"Rule {r.get('id')} - orderCriteria set to: {r['orderCriteria']}")

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
            logger.debug(f"Created HubSelectionRule object for rule id: {rule_obj.id}")
            rule_list.append(rule_obj)
        logger.debug(f"Total loaded hub rules: {len(rule_list)}")
        return rule_list


def check_size_constraints(width: float, height: float, constraints: HubSizeConstraint) -> bool:
    """
    Check if dimensions fit within constraints in either orientation.
    Returns True if dimensions are acceptable, False if they exceed constraints.
    """
    logger.debug(f"Checking size constraints for dimensions {width}x{height} with constraints {constraints}")
    if not constraints or not constraints.maxWidth or not constraints.maxHeight:
        logger.debug("No constraints provided; automatically acceptable")
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
    logger.debug(f"Checking date validity for rule {rule.id} with startDate: {rule.startDate} and endDate: {rule.endDate}")
    if not rule.startDate and not rule.endDate:
        logger.debug("No start or end dates provided; rule is automatically valid")
        return True

    current_date = datetime.now().date()
    logger.debug(f"Current date is: {current_date}")

    if rule.startDate:
        start = datetime.strptime(rule.startDate, "%Y-%m-%d").date()
        if current_date < start:
            logger.debug(f"Current date {current_date} is before start date {start} for rule {rule.id}")
            return False

    if rule.endDate:
        end = datetime.strptime(rule.endDate, "%Y-%m-%d").date()
        if current_date > end:
            logger.debug(f"Current date {current_date} is after end date {end} for rule {rule.id}")
            return False

    logger.debug(f"Rule {rule.id} is valid for the current date")
    return True


def get_equipment_data() -> Dict:
    """
    Load equipment and process data for hubs from hub_rules.json
    (assuming structure has an "equipment" section).
    """
    rules_path = Path("data/hub_rules.json")
    logger.debug(f"Loading equipment data from file: {rules_path}")
    if not rules_path.exists():
        logger.debug("Equipment data file does not exist; returning empty dict")
        return {}
    with open(rules_path, "r") as f:
        data = json.load(f)
        equipment = data.get("equipment", {})
        logger.debug(f"Equipment data loaded: {equipment}")
        return equipment


def check_equipment_requirements(hub_id: str, required_equipment: List[str],
                                 required_processes: List[str]) -> bool:
    """
    Check if a hub has required equipment and processes based on "equipment" data.
    """
    logger.debug(f"Checking equipment requirements for hub {hub_id}. Required equipment: {required_equipment}, Required processes: {required_processes}")
    equipment_data = get_equipment_data()
    hub_equipment = equipment_data.get(hub_id, {})
    logger.debug(f"Hub {hub_id} equipment data: {hub_equipment}")

    if required_equipment:
        available_equipment = hub_equipment.get("equipment", [])
        if not all(eq in available_equipment for eq in required_equipment):
            logger.debug(f"Hub {hub_id} does not have all required equipment: {required_equipment}")
            return False

    if required_processes:
        available_processes = hub_equipment.get("processes", [])
        if not all(proc in available_processes for proc in required_processes):
            logger.debug(f"Hub {hub_id} does not have all required processes: {required_processes}")
            return False

    logger.debug(f"Hub {hub_id} meets all equipment requirements")
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
    Find the "next best" hub from the CMYK hubs list for the given state or current hub.
    If state is not provided, uses current hub's Next_Best list.
    """
    logger.debug(f"Finding next best hub for current hub: {current_hub}, available hubs: {available_hubs}, state: {delivers_to_state}")
    
    # Convert available_hubs to lowercase for comparison
    available_hubs_lower = [h.lower() for h in available_hubs]
    current_hub_lower = current_hub.lower()
    
    # If state is empty, look up Next_Best from current hub
    if not delivers_to_state:
        logger.debug("No state provided, looking up Next_Best from current hub")
        # Find current hub entry
        current_hub_entry = next((h for h in cmyk_hubs if h["Hub"].lower() == current_hub_lower), None)
        if current_hub_entry and current_hub_entry.get("Next_Best"):
            logger.debug(f"Found Next_Best list for current hub: {current_hub_entry['Next_Best']}")
            # Check each next best option
            for next_hub in current_hub_entry["Next_Best"]:
                if next_hub.lower() in available_hubs_lower:
                    logger.debug(f"Found valid next best hub: {next_hub} from current hub's Next_Best list")
                    return next_hub.lower()
    else:
        # Look up by state
        state_lower = delivers_to_state.lower()
        state_hub = next((h for h in cmyk_hubs if h["State"].lower() == state_lower), None)
        if state_hub and state_hub.get("Next_Best"):
            logger.debug(f"Found Next_Best list for state {delivers_to_state}: {state_hub['Next_Best']}")
            # Check each next best option
            for next_hub in state_hub["Next_Best"]:
                if next_hub.lower() in available_hubs_lower:
                    logger.debug(f"Found valid next best hub: {next_hub} for state: {delivers_to_state}")
                    return next_hub.lower()
                else:
                    logger.debug(f"Next best hub {next_hub} not in available hubs: {available_hubs}")

    # If we get here, no valid next best hub was found
    # Return first available hub that isn't the current hub
    for hub in available_hubs_lower:
        if hub != current_hub_lower:
            logger.debug(f"No next best hub found, using first different available hub: {hub}")
            return hub

    # If all else fails, return current hub
    logger.debug(f"No alternative hub found, keeping current hub: {current_hub}")
    return current_hub_lower


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
    logger.debug(f"Starting validation of hub rules for initial hub: {initial_hub}")
    rules = load_hub_rules()
    logger.debug(f"Sorting {len(rules)} loaded rule(s) by priority (highest first)")
    # Highest priority first
    rules.sort(key=lambda x: x.priority, reverse=True)

    for rule in rules:
        logger.debug(f"Evaluating rule {rule.id} for hub {initial_hub}")
        if not rule.enabled:
            logger.debug(f"Skipping rule {rule.id} because it is not enabled")
            continue

        # Must match the same hubId in the rule
        if rule.hubId.lower() != initial_hub.lower():
            logger.debug(f"Skipping rule {rule.id} because rule hubId ({rule.hubId}) does not match initial hub ({initial_hub})")
            continue

        # Check date validity
        if not check_dates(rule):
            logger.debug(f"Skipping rule {rule.id} because it is not valid for the current date")
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
                selected_hub = find_next_best_hub(initial_hub, available_hubs, delivers_to_state, cmyk_hubs)
                logger.debug(f"Switching hub from {initial_hub} to {selected_hub} based on size constraints")
                return selected_hub
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
                logger.debug(f"Rule {rule.id} - Checking quantity: order quantity {quantity} vs maxQuantity {rule.orderCriteria.maxQuantity} => match: {qty_match}")
                all_conditions_met &= qty_match

            # productIds => exclude if product_id is in the list
            if rule.orderCriteria.productIds:
                criteria_defined = True
                pid_match = (product_id in rule.orderCriteria.productIds)
                logger.debug(f"Rule {rule.id} - Checking product_id: {product_id} in {rule.orderCriteria.productIds} => match: {pid_match}")
                all_conditions_met &= pid_match

            # keywords => exclude if any of them appear in the description
            if rule.orderCriteria.keywords:
                criteria_defined = True
                kw_match = any(kw.lower() in description.lower() for kw in rule.orderCriteria.keywords)
                logger.debug(f"Rule {rule.id} - Checking keywords in description: '{description}' against {rule.orderCriteria.keywords} => match: {kw_match}")
                all_conditions_met &= kw_match

            # If we actually had criteria and all matched => exclude
            if criteria_defined and all_conditions_met:
                logger.debug(f"Hub {initial_hub} excluded by rule {rule.id}: matched all order criteria.")
                selected_hub = find_next_best_hub(initial_hub, available_hubs, delivers_to_state, cmyk_hubs)
                logger.debug(f"Switching hub from {initial_hub} to {selected_hub} based on order criteria")
                return selected_hub

        logger.debug(f"Hub {initial_hub} not excluded by rule {rule.id}")

    logger.debug(f"Hub {initial_hub} passed all rules; final selection is {initial_hub}")
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
    logger.debug(f"Starting production hub selection with available hubs: {available_hubs}, current hub: {current_hub}")
    # Create set of valid hubs from available hubs
    valid_hubs = set(available_hubs)
    logger.debug(f"Initial valid hubs set: {valid_hubs}")

    # Load and sort rules by priority (highest first)
    rules = load_hub_rules()
    logger.debug(f"Applying {len(rules)} rule(s) for production hub selection")
    rules.sort(key=lambda x: x.priority, reverse=True)

    for rule in rules:
        logger.debug(f"Evaluating production rule {rule.id} for hub {rule.hubId}")
        # Only apply enabled rules that match a hub in our valid set
        if not rule.enabled or rule.hubId not in valid_hubs:
            logger.debug(f"Skipping rule {rule.id}: either not enabled or hub {rule.hubId} not in valid hubs")
            continue

        # Also skip if rule is not valid for current date
        if not check_dates(rule):
            logger.debug(f"Skipping rule {rule.id} because it is not valid for the current date")
            continue

        should_remove = False

        # Size constraints: remove if not satisfied
        if rule.sizeConstraints:
            if not check_size_constraints(width, height, rule.sizeConstraints):
                should_remove = True
                logger.debug(f"Rule {rule.id} indicates removal of hub {rule.hubId} due to size constraints")

        # (You could add more checks here for quantity, productID, etc., 
        #  if you need to filter out hubs entirely rather than do a "redirect".)

        if should_remove:
            valid_hubs.discard(rule.hubId)
            logger.debug(f"Removed hub {rule.hubId} from valid hubs based on rule {rule.id}")

    logger.debug(f"Remaining valid hubs after applying production rules: {valid_hubs}")

    # If the current hub is still valid, keep it
    if current_hub in valid_hubs:
        logger.debug(f"Current hub {current_hub} remains valid after rule filtering")
        return current_hub

    # Otherwise, pick any valid hub or fallback
    if valid_hubs:
        chosen = next(iter(valid_hubs))
        logger.debug(f"Chose production hub {chosen} from remaining valid hubs")
        return chosen

    # If no valid hubs remain, fallback
    logger.error("No valid hubs found; returning current hub as last resort.")
    return current_hub