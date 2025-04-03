# app/hub_selection.py
from typing import List, Dict, Optional, Union
from datetime import datetime
from pathlib import Path
import json
import logging

# Import necessary models used in type hints
from app.models import (
    HubSelectionRule,
    HubSizeConstraint,
    OrderMatchingCriteria,
    ImposingRule,      # Added for check_dates
    PreflightRule      # Added for check_dates
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# ------------------------------------------------------------------------
# 1) LOAD AND HELPER FUNCTIONS
# ------------------------------------------------------------------------

def load_hub_rules() -> List[HubSelectionRule]:
    """Load hub selection rules from JSON file."""
    rules_path = Path("data/hub_rules.json")
    logger.debug(f"Attempting to load hub rules from file: {rules_path}")
    if not rules_path.exists():
        logger.warning("Hub rules file not found; returning empty list.")
        return []

    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in hub rules file: {e}")
        raise # Re-raise to prevent using corrupted data

    rule_list = []
    rules_data = data.get("rules", [])
    logger.debug(f"Found {len(rules_data)} rule(s) in the hub rules file.")

    for r_idx, r_data in enumerate(rules_data):
        rule_id_log = r_data.get('id', f'RuleAtIndex_{r_idx}')
        logger.debug(f"Processing rule {rule_id_log}")

        # --- Parse Size Constraints ---
        size_c = None
        if r_data.get("sizeConstraints") and isinstance(r_data["sizeConstraints"], dict):
            try:
                 size_c = HubSizeConstraint(
                    maxWidth=r_data["sizeConstraints"].get("maxWidth"),
                    maxHeight=r_data["sizeConstraints"].get("maxHeight")
                )
                 # logger.debug(f"Rule {rule_id_log}: Parsed sizeConstraints: {size_c.dict()}") # Verbose
            except Exception as e:
                 logger.warning(f"Rule {rule_id_log}: Failed to parse sizeConstraints: {r_data['sizeConstraints']}. Error: {e}")


        # --- Parse Order Criteria ---
        order_c = None
        if r_data.get("orderCriteria") and isinstance(r_data["orderCriteria"], dict):
             criteria_data = r_data["orderCriteria"]
             try:
                # Explicitly get all expected fields from the criteria dict
                order_c = OrderMatchingCriteria(
                    maxQuantity=criteria_data.get("maxQuantity"),
                    minQuantity=criteria_data.get("minQuantity"),
                    keywords=criteria_data.get("keywords"),
                    excludeKeywords=criteria_data.get("excludeKeywords"),
                    productIds=criteria_data.get("productIds"),
                    excludeProductIds=criteria_data.get("excludeProductIds"), # Ensure this is loaded
                    productGroups=criteria_data.get("productGroups"),
                    excludeProductGroups=criteria_data.get("excludeProductGroups"),
                    printTypes=criteria_data.get("printTypes")
                )
                # logger.debug(f"Rule {rule_id_log}: Parsed orderCriteria: {order_c.dict(exclude_none=True)}") # Verbose
             except Exception as e:
                 logger.warning(f"Rule {rule_id_log}: Failed to parse orderCriteria: {criteria_data}. Error: {e}")

        # --- Instantiate Main Rule Object ---
        try:
            rule_obj = HubSelectionRule(
                id=r_data.get("id", f"generated_id_{r_idx}"), # Ensure ID exists
                hubId=r_data.get("hubId", ""), # Ensure hubId exists
                description=r_data.get("description", ""),
                priority=r_data.get("priority", 0),
                enabled=r_data.get("enabled", True), # Default to enabled
                sizeConstraints=size_c,
                orderCriteria=order_c,
                startDate=r_data.get("startDate"),
                endDate=r_data.get("endDate")
            )
            if not rule_obj.id or not rule_obj.hubId:
                 logger.error(f"Skipping rule due to missing ID or hubId: {r_data}")
                 continue
            # logger.debug(f"Created HubSelectionRule object: {rule_obj.dict(exclude_none=True)}") # Verbose
            rule_list.append(rule_obj)
        except Exception as e:
            logger.error(f"Failed to create HubSelectionRule object for rule {rule_id_log}. Data: {r_data}. Error: {e}")

    logger.debug(f"Successfully loaded and parsed {len(rule_list)} hub rules.")
    return rule_list


def check_size_constraints(width: float, height: float, constraints: HubSizeConstraint) -> bool:
    """
    Check if dimensions fit within constraints in either orientation.
    Returns True if dimensions are acceptable, False if they exceed constraints.
    """
    logger.debug(f"Checking size constraints for dimensions {width}x{height} with constraints {constraints}")
    if not constraints or (constraints.maxWidth is None and constraints.maxHeight is None):
        logger.debug("No specific size constraints defined; automatically acceptable")
        return True
    if constraints.maxWidth is None or constraints.maxHeight is None:
         logger.warning(f"Partial size constraints defined for {constraints}, may lead to unexpected behavior. Both maxWidth and maxHeight should be set.")
         return True # Treat partial constraints as passing for now

    dim1, dim2 = width, height
    max1, max2 = constraints.maxWidth, constraints.maxHeight

    fits_normal = (dim1 <= max1 and dim2 <= max2)
    fits_rotated = (dim1 <= max2 and dim2 <= max1)

    if fits_normal or fits_rotated:
        # logger.debug(f"Size {width}x{height} acceptable within max {max1}x{max2}") # Verbose
        return True

    logger.debug(f"Size {width}x{height} EXCEEDS limits {max1}x{max2}")
    return False

def check_dates(rule: Union[HubSelectionRule, ImposingRule, PreflightRule]) -> bool:
    """Check if a rule is valid for the current date (if start/end are provided)."""
    rule_id = getattr(rule, 'id', 'Unknown Rule') # Get ID safely
    start_date_str = getattr(rule, 'startDate', None)
    end_date_str = getattr(rule, 'endDate', None)

    # logger.debug(f"Checking date validity for rule {rule_id} with startDate: {start_date_str} and endDate: {end_date_str}") # Verbose
    if not start_date_str and not end_date_str:
        return True

    current_date = datetime.now().date()

    start_valid = True
    if start_date_str:
        try:
            start = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            if current_date < start:
                start_valid = False
        except (ValueError, TypeError):
            logger.warning(f"Invalid startDate format '{start_date_str}' for rule {rule_id}. Treating as invalid.")
            start_valid = False

    end_valid = True
    if end_date_str:
        try:
            end = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            if current_date > end:
                end_valid = False
        except (ValueError, TypeError):
             logger.warning(f"Invalid endDate format '{end_date_str}' for rule {rule_id}. Treating as invalid.")
             end_valid = False

    is_valid = start_valid and end_valid
    # logger.debug(f"Rule {rule_id} date validity: {is_valid}") # Verbose
    return is_valid


# ... (get_equipment_data, check_equipment_requirements - if still needed) ...


# ------------------------------------------------------------------------
# 2) FIND NEXT BEST HUB
# ------------------------------------------------------------------------
def find_next_best_hub(
    excluded_hub: str, # Renamed from current_hub for clarity
    available_hubs: List[str],
    delivers_to_state: str,
    cmyk_hubs: List[dict]
) -> str:
    """
    Find the "next best" hub from the CMYK hubs list for the given state or the excluded hub.
    """
    logger.debug(f"Finding next best hub after excluding: {excluded_hub}, available hubs: {available_hubs}, state: {delivers_to_state}")

    available_hubs_lower = [h.lower() for h in available_hubs if h.lower() != excluded_hub.lower()] # Exclude the one we are replacing
    if not available_hubs_lower:
        logger.warning(f"No alternative hubs available after excluding {excluded_hub}. Returning original excluded hub.")
        return excluded_hub.lower() # Fallback if no others are possible

    # Try finding the config for the *delivers_to_state* first
    state_hub_config = next((h for h in cmyk_hubs if h["State"].lower() == delivers_to_state.lower()), None)
    if state_hub_config and state_hub_config.get("Next_Best"):
        logger.debug(f"Using Next_Best list for state '{delivers_to_state}': {state_hub_config['Next_Best']}")
        for candidate in state_hub_config["Next_Best"]:
            if candidate.lower() in available_hubs_lower:
                logger.debug(f"Found valid next best hub: {candidate.lower()} from state config.")
                return candidate.lower()

    # If state config didn't yield a result, try the config for the *excluded_hub*
    excluded_hub_config = next((h for h in cmyk_hubs if h["Hub"].lower() == excluded_hub.lower()), None)
    if excluded_hub_config and excluded_hub_config.get("Next_Best"):
         logger.debug(f"Using Next_Best list for excluded hub '{excluded_hub}': {excluded_hub_config['Next_Best']}")
         for candidate in excluded_hub_config["Next_Best"]:
             if candidate.lower() in available_hubs_lower:
                 logger.debug(f"Found valid next best hub: {candidate.lower()} from excluded hub config.")
                 return candidate.lower()

    # If neither config yielded a result, return the first remaining available hub
    chosen_fallback = available_hubs_lower[0]
    logger.debug(f"No specific next best hub found, using first available alternative: {chosen_fallback}")
    return chosen_fallback


# ------------------------------------------------------------------------
# 3) VALIDATE HUB RULES (Revised Logic)
# ------------------------------------------------------------------------
def validate_hub_rules(
    initial_hub: str,
    available_hubs: List[str],
    delivers_to_state: str,
    current_hub: str, # The original hub from the request
    description: str,
    width: float,
    height: float,
    quantity: int,
    product_id: int,
    product_group: str,
    print_type: int,
    cmyk_hubs: List[dict],
) -> str:
    """
    Validates hub rules to potentially exclude the initial_hub.
    Rules are checked by priority. The first rule that matches its criteria
    (and is not overridden by excludeProductIds) will trigger exclusion.
    """
    logger.debug(f"Starting hub rule validation. Initial Hub: {initial_hub}, Available: {available_hubs}, Current Hub: {current_hub}")
    rules = load_hub_rules()
    rules.sort(key=lambda x: getattr(x, 'priority', 0), reverse=True) # Use getattr for safety
    logger.debug(f"Loaded and sorted {len(rules)} hub rules.")

    for rule in rules:
        rule_id = getattr(rule, 'id', 'Unknown') # Safe access to ID
        # logger.debug(f"Evaluating Rule ID: {rule_id}, Priority: {getattr(rule, 'priority', 0)} for Hub: {getattr(rule, 'hubId', 'N/A')}") # Verbose

        # --- Basic Rule Checks ---
        if not getattr(rule, 'enabled', False):
            # logger.debug(f"Skipping rule {rule_id} (disabled).")
            continue

        if getattr(rule, 'hubId', '').lower() != initial_hub.lower():
            # logger.debug(f"Skipping rule {rule_id} (Rule hub '{getattr(rule, 'hubId', '')}' != Initial hub '{initial_hub}').")
            continue

        if not check_dates(rule):
            logger.debug(f"Skipping rule {rule_id} (outside valid date range).")
            continue

        logger.debug(f"--- Checking Rule ID: {rule_id} ---")

        # --- Determine if Exclusion Conditions are Met ---
        rule_would_exclude = False # Reset for each rule

        # A) Check Size Constraints
        size_criteria_met_for_exclusion = False
        if rule.sizeConstraints:
            if not check_size_constraints(width, height, rule.sizeConstraints):
                size_criteria_met_for_exclusion = True
                logger.debug(f"Rule '{rule_id}': Size condition MET for exclusion.")
            else:
                 logger.debug(f"Rule '{rule_id}': Size condition NOT MET.")


        # B) Check Order Criteria
        order_criteria_met_for_exclusion = False
        if rule.orderCriteria:
            criteria = rule.orderCriteria
            criteria_defined = False
            all_positive_conditions_met = True # Assume true until a positive condition fails
            desc_lower = description.lower()

            # Check *positive* criteria first (those that *must* be true)
            if criteria.minQuantity is not None:
                criteria_defined = True
                if not (quantity >= criteria.minQuantity): all_positive_conditions_met = False; logger.debug(f"Rule {rule_id}: MinQ fail")
            if all_positive_conditions_met and criteria.maxQuantity is not None:
                 criteria_defined = True
                 if not (quantity <= criteria.maxQuantity): all_positive_conditions_met = False; logger.debug(f"Rule {rule_id}: MaxQ fail")
            if all_positive_conditions_met and criteria.productIds:
                criteria_defined = True
                if product_id not in criteria.productIds: all_positive_conditions_met = False; logger.debug(f"Rule {rule_id}: ProdID fail")
            if all_positive_conditions_met and criteria.keywords:
                criteria_defined = True
                if not any(kw.lower() in desc_lower for kw in criteria.keywords): all_positive_conditions_met = False; logger.debug(f"Rule {rule_id}: Keywords fail")
            if all_positive_conditions_met and criteria.printTypes:
                criteria_defined = True
                if print_type not in criteria.printTypes: all_positive_conditions_met = False; logger.debug(f"Rule {rule.id}: PrintType fail")
            # Add productGroups check here if needed

            # Check *negative* criteria (those that must *not* be true)
            if all_positive_conditions_met and criteria.excludeKeywords:
                criteria_defined = True # Still counts as defined criteria
                if any(kw.lower() in desc_lower for kw in criteria.excludeKeywords): all_positive_conditions_met = False; logger.debug(f"Rule '{rule_id}': ExclKeywords fail")
            # Add excludeProductGroups check here if needed

            if criteria_defined and all_positive_conditions_met:
                order_criteria_met_for_exclusion = True
                logger.debug(f"Rule '{rule_id}': Order criteria MET for exclusion.")
            elif criteria_defined:
                logger.debug(f"Rule '{rule_id}': Order criteria NOT MET (Defined: True, All Met: False).")
            else: # No order criteria were defined in this rule section
                 logger.debug(f"Rule '{rule_id}': No specific order criteria defined to check.")


        # --- Determine if Rule Triggers Exclusion ---
        # Rule excludes if EITHER size OR order criteria were met for exclusion
        rule_would_exclude = size_criteria_met_for_exclusion or order_criteria_met_for_exclusion

        if rule_would_exclude:
             # Check the product ID exclusion override
             if rule.orderCriteria and rule.orderCriteria.excludeProductIds and product_id in rule.orderCriteria.excludeProductIds:
                 logger.info(f"Rule '{rule_id}' would exclude hub, BUT exclusion overridden by excludeProductIds for Product ID {product_id}.")
                 continue # Exclusion cancelled for THIS rule, check next rule

             # Proceed with exclusion
             logger.info(f"Hub '{initial_hub}' EXCLUDED by Rule '{rule_id}' (Conditions met and no override).")
             next_hub = find_next_best_hub(initial_hub, available_hubs, delivers_to_state, cmyk_hubs)
             logger.info(f"Switching hub from '{initial_hub}' to next best '{next_hub}'.")
             return next_hub # EXCLUDE and RETURN
        else:
              # Conditions for this rule were not met for exclusion
              logger.debug(f"Rule '{rule_id}' conditions not met for exclusion. Continuing to next rule.")
              continue # Move to the next rule

    # If loop finishes without any rule causing exclusion
    logger.info(f"Hub '{initial_hub}' passed all applicable rules.")
    return initial_hub

# ------------------------------------------------------------------------
# 4) CHOOSE PRODUCTION HUB (Simplified - Now relies solely on validate_hub_rules)
# ------------------------------------------------------------------------
# This function might become redundant if validate_hub_rules handles the full logic,
# but keeping it for now if there's a conceptual separation needed.
# Consider removing if validate_hub_rules fully determines the final hub.
def choose_production_hub(
    available_hubs: List[str],
    delivers_to_state: str,
    current_hub: str,
    product_id: int, # Need product_id for QLD override check
    cmyk_hubs: List[dict] # Need cmyk_hubs for find_next_best lookup
) -> str:
    """
    Determines the *initial* best guess for the production hub based on state/next best.
    The result of this function is then validated by validate_hub_rules.
    """
    logger.debug(f"Choosing initial production hub. Available: {available_hubs}, DeliversTo: {delivers_to_state}, Current: {current_hub}")
    product_hubs_lower = [h.lower() for h in available_hubs]

    # 1) single production hub defined for the product
    if len(product_hubs_lower) == 1:
        chosen = product_hubs_lower[0]
        logger.debug(f"Only one production hub defined for product: {chosen}")
        # QLD override check will happen *after* this initial choice if needed (though unlikely for single-hub products)
    # 2) if misDeliversToState is in the product's allowed hubs
    elif delivers_to_state.lower() in product_hubs_lower:
        chosen = delivers_to_state.lower()
        logger.debug(f"DeliversToState ('{chosen}') is in product hubs.")
    # 3) else find the next best from cmykHubs config
    else:
        chosen = find_next_best(delivers_to_state, product_hubs_lower, cmyk_hubs)
        logger.debug(f"Using next best hub based on state '{delivers_to_state}': {chosen}")

    # 4) Apply QLD cards override *based on the initial choice*
    # This override seems specific and might be better placed elsewhere,
    # but mimicking the original description's flow for now.
    if product_id in [6, 7, 8, 9] and current_hub.lower() != "nqld" and delivers_to_state.lower() == "qld":
        logger.debug(f"Applying QLD cards override (Product ID {product_id}, Current Hub {current_hub}, DeliversTo {delivers_to_state}). Overriding initial choice '{chosen}' with 'vic'.")
        chosen = "vic"
    else:
         logger.debug(f"QLD override conditions not met (ProductID: {product_id}, CurrentHub: {current_hub}, DeliversTo: {delivers_to_state}). Keeping initial choice: {chosen}")


    logger.debug(f"Initial hub choice before validation: {chosen}")
    return chosen