# app/hub_selection.py
from typing import List, Dict, Optional, Union, Set
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
        # logger.debug(f"Processing rule {rule_id_log}") # Verbose

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
                # Legacy fields are ignored during parsing now
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
    # logger.debug(f"Checking size constraints for dimensions {width}x{height} with constraints {constraints}") # Verbose
    if not constraints or (constraints.maxWidth is None and constraints.maxHeight is None):
        # logger.debug("No specific size constraints defined; automatically acceptable") # Verbose
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

# ------------------------------------------------------------------------
# 2) CHOOSE INITIAL PRODUCTION HUB (Moved from schedule_logic.py)
# ------------------------------------------------------------------------
def find_next_best(
    delivers_to_state: str,
    product_hubs_lower: list[str],
    cmyk_hubs: list[dict],
    current_hub_id: Optional[int] # Added current hub ID for fallback
) -> str:
    """
    Attempts to find the best production hub when the delivery state isn't directly listed.
    1. Finds the cmyk_hubs entry matching the delivery state.
    2. Iterates through its 'Next_Best' list, returning the first hub that's also in the product's allowed hubs.
    3. If no 'Next_Best' match is found (or the delivery state itself isn't in cmyk_hubs):
       a. Tries to find the hub name corresponding to the `current_hub_id`.
       b. If found and allowed for the product, returns that hub name.
    4. If all above fails, returns the first hub listed in the product's allowed hubs as a final fallback.
    """
    # 1 & 2: Try finding based on delivery state's Next_Best
    logger.debug(f"[find_next_best] Searching for state '{delivers_to_state}' in cmyk_hubs to find Next_Best match within {product_hubs_lower}")
    state_hub_config = next((entry for entry in cmyk_hubs if entry["State"].lower() == delivers_to_state.lower()), None)

    if state_hub_config:
        logger.debug(f"[find_next_best] Found state '{delivers_to_state}'. Checking Next_Best: {state_hub_config.get('Next_Best', [])}")
        for candidate in state_hub_config.get("Next_Best", []):
            candidate_lower = candidate.lower()
            if candidate_lower in product_hubs_lower:
                logger.info(f"[find_next_best] Found valid 'Next_Best' hub via state config: {candidate_lower}")
                return candidate_lower
        # Found the state, but no Next_Best matched the product's hubs
        logger.debug(f"[find_next_best] State '{delivers_to_state}' found, but no 'Next_Best' hub is in the product's allowed hubs {product_hubs_lower}.")
    else:
        logger.debug(f"[find_next_best] State '{delivers_to_state}' not found in cmyk_hubs config.")


    # 3: Fallback - Try using current_hub_id if state lookup failed
    logger.warning(f"[find_next_best] Could not find suitable 'Next_Best' hub for state '{delivers_to_state}'. Attempting fallback using current_hub_id: {current_hub_id}.")
    if current_hub_id is not None:
        current_hub_config = next((entry for entry in cmyk_hubs if entry.get("CMHKhubID") == current_hub_id), None)
        if current_hub_config:
            current_hub_name = current_hub_config.get("Hub", "").lower()
            if current_hub_name and current_hub_name in product_hubs_lower:
                logger.info(f"[find_next_best] Fallback successful: Found hub name '{current_hub_name}' for current_hub_id {current_hub_id} and it is allowed for the product.")
                return current_hub_name
            elif current_hub_name:
                 logger.warning(f"[find_next_best] Fallback found hub name '{current_hub_name}' for ID {current_hub_id}, but it's NOT in allowed product hubs {product_hubs_lower}.")
            else:
                logger.warning(f"[find_next_best] Found entry for current_hub_id {current_hub_id}, but it has no 'Hub' name.")
        else:
             logger.warning(f"[find_next_best] Fallback failed: Could not find a hub entry matching current_hub_id {current_hub_id}.")
    else:
        logger.warning("[find_next_best] Fallback using current_hub_id skipped: current_hub_id is None.")


    # 4: Final Fallback - Return the first hub listed for the product
    if product_hubs_lower:
        final_fallback_hub = product_hubs_lower[0]
        logger.error(f"[find_next_best] All fallbacks failed. Defaulting to the first listed product hub: {final_fallback_hub}")
        return final_fallback_hub
    else:
        # Absolute last resort if product has no hubs defined (should not happen with fallback product)
        logger.error("[find_next_best] CRITICAL FALLBACK: Product has no defined hubs. Defaulting to 'vic'.")
        return "vic"


def choose_production_hub(
    product_hubs: list[str],
    misDeliversToState: str,
    current_hub: str, # The resolved current hub name (lowercase)
    current_hub_id: Optional[int], # The resolved current hub ID
    product_id: int,
    cmyk_hubs: list[dict]
) -> str:
    """
    Determines the *initial* candidate production hub based on product definition,
    delivery state, and current hub location. This choice will then be validated.

    1. If only one hub is defined for the product, use it.
    2. If the delivery state is a valid production hub for the product, use it.
    3. Otherwise, find the 'next best' hub using find_next_best helper.
    4. Apply QLD cards override if applicable (specific product IDs, not NQLD, delivering to QLD).
    """
    logger.debug(f"[choose_production_hub] Choosing initial hub. ProductHubs: {product_hubs}, DeliversTo: {misDeliversToState}, CurrentHub: {current_hub}, ProductID: {product_id}")
    product_hubs_lower = [h.lower() for h in product_hubs]
    delivers_to_lower = misDeliversToState.lower()
    current_hub_lower = current_hub.lower()

    # Handle case where product_hubs might be empty (shouldn't happen with fallback)
    if not product_hubs_lower:
        logger.error(f"[choose_production_hub] Product ID {product_id} has no Production_Hub defined. Defaulting to 'vic'.")
        return "vic"

    # 1) Single production hub defined for the product
    if len(product_hubs_lower) == 1:
        chosen = product_hubs_lower[0]
        logger.debug(f"[choose_production_hub] Only one production hub defined: {chosen}")
    # 2) Delivery state is directly listed as a production hub for the product
    elif delivers_to_lower in product_hubs_lower:
        chosen = delivers_to_lower
        logger.debug(f"[choose_production_hub] Delivery state '{chosen}' is in product hubs.")
    # 3) Delivery state not in product hubs, find the next best
    else:
        logger.debug(f"[choose_production_hub] Delivery state '{delivers_to_lower}' not in product hubs {product_hubs_lower}. Finding next best...")
        chosen = find_next_best(
            delivers_to_state=delivers_to_lower,
            product_hubs_lower=product_hubs_lower,
            cmyk_hubs=cmyk_hubs,
            current_hub_id=current_hub_id
        )
        logger.debug(f"[choose_production_hub] Result from find_next_best: {chosen}")

    # 4) Apply QLD cards override *after* the initial choice
    # Product IDs 6, 7, 8, 9 are Business Cards (Gloss, Matt, Uncoated, Premium Uncoated)
    if product_id in [6, 7, 8, 9] and current_hub_lower != "nqld" and delivers_to_lower == "qld":
        # If the order originates outside NQLD but delivers to QLD, force it to VIC
        logger.info(f"Applying QLD cards override (Product ID {product_id}, Current Hub {current_hub}, DeliversTo {misDeliversToState}). Overriding initial choice '{chosen}' with 'vic'.")
        chosen = "vic"
    # else: # No need for else log, default behaviour is keeping 'chosen'
    #      logger.debug(f"QLD override conditions not met. Keeping initial choice: {chosen}")

    logger.info(f"[choose_production_hub] Initial hub choice determined: {chosen}")
    return chosen


# ------------------------------------------------------------------------
# 3) GENERATE HUB PREFERENCE LIST (NEW HELPER)
# ------------------------------------------------------------------------
def generate_hub_preference_list(
    initial_hub: str,
    available_hubs: List[str],
    delivers_to_state: str,
    cmyk_hubs: List[dict]
) -> List[str]:
    """
    Generates an ordered list of hubs to try for validation, starting with the
    initial hub, then following Next_Best logic (state, then initial hub's config),
    and finally adding any remaining available hubs.
    Ensures no duplicates and all hubs are lowercase.
    """
    preference_list: List[str] = []
    # Use a set for quick lookups and ensuring available hubs are lowercase and unique
    available_hubs_set: Set[str] = {h.lower() for h in available_hubs if h}
    initial_hub_lower = initial_hub.lower()
    delivers_to_state_lower = delivers_to_state.lower()

    # Function to safely add a hub if it's available and not already added
    def add_hub(hub: str):
        hub_lower = hub.lower()
        if hub_lower in available_hubs_set and hub_lower not in preference_list:
            preference_list.append(hub_lower)

    # 1. Start with the initial hub
    add_hub(initial_hub_lower)

    # 2. Add hubs from the delivery state's Next_Best list
    state_hub_config = next((h for h in cmyk_hubs if h["State"].lower() == delivers_to_state_lower), None)
    if state_hub_config and state_hub_config.get("Next_Best"):
        logger.debug(f"Adding Next_Best hubs from state '{delivers_to_state_lower}' config: {state_hub_config['Next_Best']}")
        for candidate in state_hub_config["Next_Best"]:
            add_hub(candidate)

    # 3. Add hubs from the initial hub's Next_Best list (if different from state config)
    #    This covers cases where the initial hub isn't the primary state hub.
    initial_hub_config = next((h for h in cmyk_hubs if h["Hub"].lower() == initial_hub_lower), None)
    if initial_hub_config and initial_hub_config.get("Next_Best"):
         # Avoid logging if it's the same config as the state one already processed
         if not (state_hub_config and state_hub_config["Hub"].lower() == initial_hub_config["Hub"].lower()):
              logger.debug(f"Adding Next_Best hubs from initial hub '{initial_hub_lower}' config: {initial_hub_config['Next_Best']}")
         for candidate in initial_hub_config["Next_Best"]:
             add_hub(candidate)

    # 4. Add any remaining available hubs not already in the list
    #    Iterate through the original available_hubs to maintain some semblance of original order if possible
    remaining_hubs = [h for h in available_hubs if h.lower() not in preference_list]
    if remaining_hubs:
        logger.debug(f"Adding remaining available hubs: {remaining_hubs}")
        for hub in remaining_hubs:
            add_hub(hub) # add_hub handles check for availability and duplicates

    # Ensure the list is not empty if there were available hubs
    if not preference_list and available_hubs_set:
        logger.warning(f"Preference list was empty, but available hubs exist ({available_hubs_set}). Populating with available hubs.")
        preference_list.extend(list(available_hubs_set))

    logger.debug(f"Generated Hub Preference List: {preference_list}")
    return preference_list


# ------------------------------------------------------------------------
# 4) VALIDATE HUB RULES (Revised Iterative Logic)
# ------------------------------------------------------------------------
def validate_hub_rules(
    initial_hub: str,
    available_hubs: List[str],
    delivers_to_state: str,
    # --- Order details needed for criteria checks ---
    description: str,
    width: float,
    height: float,
    quantity: int,
    product_id: int,
    product_group: str, # Added product_group
    print_type: int,
    # --- Config data ---
    cmyk_hubs: List[dict],
) -> str:
    """
    Validates potential production hubs against defined rules iteratively.
    Starts with the initial_hub, then checks hubs from a generated preference list.
    Returns the first hub that passes all applicable rules.
    If no hub passes, returns the first hub from the preference list as a fallback.
    """
    logger.info(f"--- Starting Iterative Hub Rule Validation ---")
    logger.debug(f"Initial Hub: {initial_hub}, Available: {available_hubs}, DeliversTo: {delivers_to_state}, ProductID: {product_id}, Qty: {quantity}, Size: {width}x{height}")

    rules = load_hub_rules()
    # Sort rules by priority (highest first)
    rules.sort(key=lambda x: getattr(x, 'priority', 0), reverse=True)
    logger.debug(f"Loaded and sorted {len(rules)} hub rules by priority.")

    # Generate the ordered list of hubs to try
    potential_hubs_to_try = generate_hub_preference_list(initial_hub, available_hubs, delivers_to_state, cmyk_hubs)
    logger.info(f"Hub preference list for validation: {potential_hubs_to_try}")

    if not potential_hubs_to_try:
        logger.error("Cannot validate hubs: No potential hubs generated (available_hubs might be empty). Falling back to 'vic'.")
        return "vic" # Absolute fallback

    excluded_by_rule = {} # Store {hub_name: rule_id} for logging

    # Iterate through the preferred hubs
    for hub_candidate in potential_hubs_to_try:
        logger.info(f"--- Validating Hub Candidate: {hub_candidate} ---")
        is_candidate_valid = True # Assume valid until a rule excludes it

        # Check this candidate against all applicable rules
        for rule in rules:
            rule_id = getattr(rule, 'id', 'Unknown')

            # --- Basic Rule Checks ---
            if not getattr(rule, 'enabled', False):
                # logger.debug(f"Skipping rule {rule_id} (disabled).") # Verbose
                continue

            # Check if rule applies specifically TO this hub candidate
            if getattr(rule, 'hubId', '').lower() != hub_candidate.lower():
                # logger.debug(f"Skipping rule {rule_id} (Rule hub '{getattr(rule, 'hubId', '')}' != Candidate '{hub_candidate}').") # Verbose
                continue

            # Check date range AFTER confirming the rule applies to this hub
            if not check_dates(rule):
                logger.debug(f"Skipping rule {rule_id} for hub {hub_candidate} (outside valid date range).")
                continue

            logger.debug(f"Evaluating Rule ID: {rule_id} (Priority: {getattr(rule, 'priority', 0)}) against Hub: {hub_candidate}")

            # --- Determine if Exclusion Conditions are Met for THIS rule ---
            rule_would_exclude = False
            size_constraint_defined = rule.sizeConstraints is not None
            order_criteria_defined = rule.orderCriteria is not None

            # A) Check Size Constraints (only if defined)
            size_criteria_met_for_exclusion = False
            if size_constraint_defined:
                if not check_size_constraints(width, height, rule.sizeConstraints):
                    size_criteria_met_for_exclusion = True
                    logger.debug(f"Rule '{rule_id}': Size condition MET for potential exclusion of {hub_candidate}.")
                # else: # Verbose
                #      logger.debug(f"Rule '{rule_id}': Size condition NOT MET for {hub_candidate}.")

            # B) Check Order Criteria (only if defined)
            order_criteria_met_for_exclusion = False
            if order_criteria_defined:
                criteria = rule.orderCriteria
                criteria_defined = False # Track if any specific order criteria were actually checked
                all_positive_conditions_met = True # Assume true until a positive condition fails
                desc_lower = description.lower()
                pg_lower = product_group.lower() # Use lowercase product group

                # Check *positive* criteria first (those that *must* be true)
                if criteria.minQuantity is not None:
                    criteria_defined = True
                    if not (quantity >= criteria.minQuantity): all_positive_conditions_met = False; logger.debug(f"Rule {rule_id}: MinQ fail ({quantity} < {criteria.minQuantity})")
                # REMOVED MaxQuantity check from here - handled separately below
                if all_positive_conditions_met and criteria.productIds:
                    criteria_defined = True
                    if product_id not in criteria.productIds: all_positive_conditions_met = False; logger.debug(f"Rule {rule_id}: ProdID fail ({product_id} not in {criteria.productIds})")
                if all_positive_conditions_met and criteria.keywords:
                    criteria_defined = True
                    if not any(kw.lower() in desc_lower for kw in criteria.keywords): all_positive_conditions_met = False; logger.debug(f"Rule {rule_id}: Keywords fail (None of {criteria.keywords} in desc)")
                if all_positive_conditions_met and criteria.printTypes:
                    criteria_defined = True
                    if print_type not in criteria.printTypes: all_positive_conditions_met = False; logger.debug(f"Rule {rule.id}: PrintType fail ({print_type} not in {criteria.printTypes})")
                if all_positive_conditions_met and criteria.productGroups:
                    criteria_defined = True
                    if not any(pg.lower() == pg_lower for pg in criteria.productGroups): all_positive_conditions_met = False; logger.debug(f"Rule {rule.id}: ProductGroup fail ('{pg_lower}' not in {criteria.productGroups})")

                # Check *negative* criteria (those that must *not* be true)
                if all_positive_conditions_met and criteria.excludeKeywords:
                    criteria_defined = True # Still counts as defined criteria
                    if any(kw.lower() in desc_lower for kw in criteria.excludeKeywords): all_positive_conditions_met = False; logger.debug(f"Rule '{rule_id}': ExclKeywords fail (Found one of {criteria.excludeKeywords} in desc)")
                if all_positive_conditions_met and criteria.excludeProductGroups:
                     criteria_defined = True
                     if any(pg.lower() == pg_lower for pg in criteria.excludeProductGroups): all_positive_conditions_met = False; logger.debug(f"Rule '{rule_id}': ExclProductGroup fail ('{pg_lower}' is in {criteria.excludeProductGroups})")
                # excludeProductIds is handled separately as an override below

                # --- NEW: Check maxQuantity separately ---
                max_quantity_exceeded = False
                if criteria.maxQuantity is not None:
                    criteria_defined = True # Mark that maxQ was checked
                    if quantity > criteria.maxQuantity:
                        max_quantity_exceeded = True
                        logger.debug(f"Rule {rule_id}: MaxQ condition MET ({quantity} > {criteria.maxQuantity})")
                    # else: # No need to log if not exceeded, as it doesn't cause failure here

                # --- Determine if order criteria are met for exclusion (Revised Logic) ---
                order_criteria_met_for_exclusion = False
                if criteria_defined and all_positive_conditions_met:
                    # All *other* positive/negative conditions passed.
                    # Now check if the maxQuantity condition (if defined) also allows exclusion.
                    if criteria.maxQuantity is not None:
                        # If maxQ is defined, it must be exceeded for the rule to apply based on order criteria
                        if max_quantity_exceeded:
                            order_criteria_met_for_exclusion = True
                            logger.debug(f"Rule '{rule_id}': Order criteria MET (incl. MaxQ exceeded) for potential exclusion.")
                        else:
                             logger.debug(f"Rule '{rule_id}': Order criteria NOT MET (MaxQ defined but not exceeded).")
                    else:
                        # If maxQ is not defined, meeting other criteria is enough
                        order_criteria_met_for_exclusion = True
                        logger.debug(f"Rule '{rule_id}': Order criteria MET (MaxQ not defined) for potential exclusion.")
                elif criteria_defined:
                     logger.debug(f"Rule '{rule_id}': Order criteria NOT MET (one or more positive/negative conditions failed).")
                # else: # No criteria defined, already handled


            # --- Determine if Rule Triggers Exclusion (NEW LOGIC) ---
            if size_constraint_defined and order_criteria_defined:
                # Both are defined: Exclude only if BOTH conditions are met
                if size_criteria_met_for_exclusion and order_criteria_met_for_exclusion:
                    rule_would_exclude = True
                    logger.debug(f"Rule '{rule_id}': Excluded because BOTH size and order criteria were met.")
                else:
                    logger.debug(f"Rule '{rule_id}': Not excluded because BOTH size ({size_criteria_met_for_exclusion}) and order ({order_criteria_met_for_exclusion}) criteria were not met.")
            elif size_constraint_defined:
                # Only size defined: Exclude if size condition met
                if size_criteria_met_for_exclusion:
                    rule_would_exclude = True
                    logger.debug(f"Rule '{rule_id}': Excluded because size criterion was met (only size defined).")
                else:
                    logger.debug(f"Rule '{rule_id}': Not excluded because size criterion was not met (only size defined).")
            elif order_criteria_defined:
                # Only order criteria defined: Exclude if order criteria met
                if order_criteria_met_for_exclusion:
                    rule_would_exclude = True
                    logger.debug(f"Rule '{rule_id}': Excluded because order criterion was met (only order criteria defined).")
                else:
                    logger.debug(f"Rule '{rule_id}': Not excluded because order criterion was not met (only order criteria defined).")
            else:
                # Neither defined: Rule cannot exclude based on these criteria
                 logger.debug(f"Rule '{rule_id}': No size or order criteria defined, cannot exclude based on these.")
                 rule_would_exclude = False


            # --- Apply Exclusion Override and Final Decision ---
            if rule_would_exclude:
                 # Check the product ID exclusion override
                 if rule.orderCriteria and rule.orderCriteria.excludeProductIds and product_id in rule.orderCriteria.excludeProductIds:
                     logger.info(f"Rule '{rule_id}' would exclude hub {hub_candidate}, BUT exclusion overridden by excludeProductIds for Product ID {product_id}.")
                     # This rule doesn't exclude, but others might. Continue checking other rules for this hub_candidate.
                     continue # Skip to the next rule for this hub
                 else:
                     # Exclusion confirmed for this hub_candidate by this rule
                     # Determine reason string based on what triggered the exclusion
                     reason_parts = []
                     if size_constraint_defined and order_criteria_defined:
                         reason_parts.append("Size AND Order Criteria")
                     elif size_constraint_defined:
                          reason_parts.append("Size")
                     elif order_criteria_defined:
                          reason_parts.append("Order Criteria")

                     reason_str = " AND ".join(reason_parts) if reason_parts else "Unknown" # Should have a reason if rule_would_exclude is True

                     logger.info(f"Hub Candidate '{hub_candidate}' EXCLUDED by Rule '{rule_id}'. Reason: {reason_str}.")
                     is_candidate_valid = False
                     excluded_by_rule[hub_candidate] = rule_id # Record why it was excluded
                     break # Stop checking rules for this invalid candidate, move to next candidate

            # else: # Rule conditions not met for exclusion # Verbose
            #      logger.debug(f"Rule '{rule_id}' conditions not met for exclusion of {hub_candidate}. Continuing rule check.")

        # --- End of rule loop for this candidate ---
        if is_candidate_valid:
            logger.info(f"Hub Candidate '{hub_candidate}' PASSED all applicable rules. Selecting this hub.")
            return hub_candidate # Found a valid hub, return it immediately

        # If loop finished and candidate is invalid (is_candidate_valid is False),
        # the outer loop will proceed to the next candidate in potential_hubs_to_try

    # --- End of candidate loop ---
    # If we get here, no hub passed validation
    logger.warning(f"No suitable hub found after checking all candidates: {potential_hubs_to_try}.")
    logger.warning(f"Exclusion reasons: {excluded_by_rule}")

    # Fallback: Return the first hub from the preference list
    fallback_hub = potential_hubs_to_try[0]
    logger.warning(f"FALLBACK: Returning the first preferred hub: {fallback_hub}")
    return fallback_hub