#shcedule_logic.py
#This module contains the main scheduling logic for processing an order request. It includes steps such as state overrides, hub selection, product matching, finishing days calculation, and date adjustments.
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
import pytz
from pathlib import Path
from pathlib import Path


from app.models import (
    ScheduleRequest,
    ScheduleResponse,
    FinishingRules,
    FinishingRule,
    CenterRule
)
from typing import Union
from app.data_manager import (
    get_product_info_data,
    get_product_keywords_data,
    get_cmyk_hubs_data,
    get_hub_data
)
from app.product_matcher import match_product_id, determine_grain_direction
from app.config import TIME_ADJUST, WA_TIME_ADJUST
from app.hub_selection import validate_hub_rules, choose_production_hub

logger = logging.getLogger("scheduler")
logger.setLevel(logging.DEBUG)

def process_order(req: ScheduleRequest) -> Optional[ScheduleResponse]:
    """
    Main function to schedule an order, including:
      1) State overrides for SA/TAS => VIC, ACT => NSW, and NQLD override.
      2) Postcode -> Hub override (if any).
      3) Product matching, finishing days, final production hub selection.
    """
    
    # Set default postcode if it's null or empty
    if not req.misDeliversToPostcode:
        req.misDeliversToPostcode = "0000"
    

    # ----------------------------------------------------------------
    # Step 1a) State override for SA, TAS, ACT, and NQLD
    # ----------------------------------------------------------------
    if req.misDeliversToState.lower() in ["sa", "tas"]:
        logger.debug("MIS Delivers to: %s => treating as 'vic'", req.misDeliversToState)
        req.misDeliversToState = "vic"

    if req.misDeliversToState.lower() == "act":
        logger.debug("MIS Delivers to: %s => treating as 'nsw'", req.misDeliversToState)
        req.misDeliversToState = "nsw"

    if req.misCurrentHub.lower() == "nqld":
        logger.debug("MIS Current hub is 'nqld' => setting misDeliversToState = 'nqld'")
        req.misDeliversToState = "nqld"

    # ----------------------------------------------------------------
    # Step 1b) Postcode-based Hub override (lookupHUB)
    # ----------------------------------------------------------------
    override_info = lookup_hub_by_postcode(req.misDeliversToPostcode, get_hub_data())
    if override_info:
        logger.debug("Postcode-based production override => %s", override_info)
        req.misDeliversToState = override_info["hubName"]
    else:
        logger.debug("No postcode override for postcode=%s => continuing with misDeliversToState=%s",
                     req.misDeliversToPostcode, req.misDeliversToState)

    # 2) Product matching
    product_keywords = get_product_keywords_data()
    found_product_id = match_product_id(req.description, product_keywords)
    if found_product_id is None:
        logger.debug("No matching product found => using fallback product_id=0")
        found_product_id = 0

    product_info = get_product_info_data()
    product_obj = product_info.get(str(found_product_id), None)
    if not product_obj:
        logger.debug("product_id=%s not found in product_info => fallback schedule", found_product_id)
        # fallback product with all required fields
        product_obj = {
            "Product_Group": "No Group Found",
            "Product_Category": "Unmatched Product",
            "Product_ID": 0,
            "Cutoff": "12",
            "Days_to_produce": "2",
            "Production_Hub": ["vic"],
            "Start_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
            "SynergyPreflight": 0,
            "SynergyImpose": 0,
            "EnableAutoHubTransfer": 1,
            "Modified_run_date": [],
            "Production_Hub": ["vic"]  # Ensure Production_Hub is always present
        }

    # 3) Determine grain direction
    grain_str, grain_id = determine_grain_direction(
        orientation=req.orientation,
        width=req.preflightedWidth,
        height=req.preflightedHeight,
        description=req.description
    )

    # 4) Current time (tz-aware)
    current_time = datetime.now(timezone.utc)  # instead of datetime.utcnow() to avoid warnings
    if req.misCurrentHub.lower() == "wa":
        current_time += timedelta(hours=WA_TIME_ADJUST)
    else:
        current_time += timedelta(hours=TIME_ADJUST)

    # 5) Cutoff check
    cutoff_hour = int(product_obj["Cutoff"])
    if current_time.hour >= cutoff_hour:
        start_date = (current_time + timedelta(days=1)).date()
        cutoff_status = "After Cutoff"
    else:
        start_date = current_time.date()
        cutoff_status = "Before Cutoff"

    # Adjust start_date to next valid start day
    allowed_start_days = product_obj["Start_days"]
    start_date = get_next_valid_start_day(start_date, allowed_start_days)

    # 6) Calculate finishing days
    finishing_days = calculate_finishing_days(req, product_obj)
    base_prod_days = int(product_obj["Days_to_produce"])
    total_prod_days = base_prod_days + finishing_days

    # 7) Choose final production hub with hub rules validation
    product_hubs = product_obj.get("Production_Hub", [])
    cmyk_hubs = get_cmyk_hubs_data()

    # First get optimal hub based on standard rules
    initial_hub = choose_production_hub(
        product_hubs,
        req.misDeliversToState.lower(),
        req.misCurrentHub.lower(),
        found_product_id,
        cmyk_hubs
    )
    
    # Then validate against hub rules and get final hub
    chosen_hub = validate_hub_rules(
        initial_hub=initial_hub,
        available_hubs=product_hubs,
        delivers_to_state=req.misDeliversToState.lower(),
        current_hub=req.misCurrentHub.lower(),
        description=req.description,
        width=req.preflightedWidth,
        height=req.preflightedHeight,
        quantity=req.misOrderQTY,
        product_id=found_product_id,
        product_group=product_obj["Product_Group"],
        cmyk_hubs=cmyk_hubs
    )
    
    logger.debug(f"Initial hub selection: {initial_hub}, Final hub after rules: {chosen_hub}")

    # Find the actual cmykHubID for that chosen hub
    chosen_hub_id = find_cmyk_hub_id(chosen_hub, cmyk_hubs)
    
    # 8) add business days for final dispatch
    closed_dates = get_closed_dates_for_state(chosen_hub, cmyk_hubs)
    adjusted_start_date, dispatch_date = add_business_days(start_date, total_prod_days, closed_dates)

    # 9) Check for modified run dates
    modified_start = check_modified_run_dates(
        adjusted_start_date,
        product_obj,
        req.misDeliversToState
    )
    
    if modified_start:
        logger.debug(f"Using modified start date: {modified_start}")
        adjusted_start_date = modified_start
        # Recalculate dispatch date from modified start
        _, dispatch_date = add_business_days(adjusted_start_date, total_prod_days, closed_dates)

    # Build a debug log
    debug_log = (
        f"CutoffStatus={cutoff_status}, StartDate={start_date}, "
        f"AdjustedStartDate={adjusted_start_date}, "  # Include the adjusted start date in the log
        f"ProdDays={base_prod_days}, FinishingDays={finishing_days}, "
        f"ChosenHub={chosen_hub}, DispatchDate={dispatch_date}"
    )
    logger.debug("SCHEDULE LOG: " + debug_log)

    # Return comprehensive response
    return ScheduleResponse(
        # Core Product Info
        productId=found_product_id,
        productGroup=product_obj["Product_Group"],
        productCategory=product_obj["Product_Category"],
        productionHubs=product_obj["Production_Hub"],
        
        # Production Details
        cutoffStatus=cutoff_status,
        productStartDays=product_obj["Start_days"],
        productCutoff=str(product_obj["Cutoff"]),
        daysToProduceBase=base_prod_days,
        finishingDays=finishing_days,
        totalProductionDays=total_prod_days,
        
        # Location Info
        orderPostcode=req.misDeliversToPostcode,
        chosenProductionHub=chosen_hub,
        hubTransferTo=chosen_hub_id,
        
        # Dates
        startDate=str(start_date),
        adjustedStartDate=str(adjusted_start_date),
        dispatchDate=str(dispatch_date),
        
        # Processing Info
        grainDirection=grain_str,
        orderQuantity=req.misOrderQTY,
        orderKinds=req.kinds,
        totalQuantity=req.misOrderQTY * req.kinds,
        
        # Configuration
        synergyPreflight=product_obj.get("SynergyPreflight"),
        synergyImpose=product_obj.get("SynergyImpose"),
        enableAutoHubTransfer=product_obj.get("EnableAutoHubTransfer")
    )

# --------------------------------------------------------------------
# Postcode-based override (Step 1)
# --------------------------------------------------------------------
def is_postcode_in_range(postcode: str, range_string: str) -> bool:
    """
    Check if postcode is within the given range string.
    Range string can be comma-separated values or dash ranges like "4737-4895".
    """
    postcode_segments = range_string.split(",")
    for segment in postcode_segments:
        segment = segment.strip()
        if "-" in segment:
            # Handle range like "4737-4895"
            start, end = segment.split("-")
            try:
                p = int(postcode)
                s = int(start)
                e = int(end)
                if s <= p <= e:
                    return True
            except ValueError:
                continue
        else:
            # Handle exact match
            if postcode == segment:
                return True
    return False

def lookup_hub_by_postcode(postcode: str, hub_data: list[dict]) -> Optional[dict]:
    """
    Mirrors your JS logic to check if 'postcode' is in the comma-separated or dash range
    in hub_data. If found, return e.g. {"hubName": "vic", "hubId": 1}, else None.
    """
    for entry in hub_data:
        if is_postcode_in_range(postcode, entry["postcode"]):
            return {"hubName": entry["hubName"], "hubId": entry["hubId"]}
    return None

def get_next_valid_start_day(date, allowed_start_days):
    """
    Find the next allowed start day from the given date.
    
    Args:
        date: datetime.date object
        allowed_start_days: list of allowed days (e.g., ["Monday", "Wednesday"])
    
    Returns:
        datetime.date: The next valid start date
    """
    # Map weekday numbers to day names
    day_map = {
        0: "Monday", 1: "Tuesday", 2: "Wednesday",
        3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"
    }
    
    current_date = date
    while True:
        current_day_name = day_map[current_date.weekday()]
        if current_day_name in allowed_start_days:
            return current_date
        current_date += timedelta(days=1)

def check_modified_run_dates(adjusted_start_date: datetime.date, product_obj: dict, state: str) -> datetime.date:
    """
    Check if there's a modified run date that applies to this order.
    Only returns the new print date if a modification applies.
    
    Args:
        adjusted_start_date: The calculated start date after weekday adjustments
        product_obj: The product object containing Modified_run_date array
        state: The delivery state (e.g., 'vic', 'nsw')
    
    Returns:
        datetime.date: New start date if modified, None if no modification applies
    """
    modified_dates = product_obj.get("Modified_run_date", [])
    
    for modified_date in modified_dates:
        if len(modified_date) < 5:  # Ensure array has all required elements
            continue
            
        scheduled_print_date = datetime.strptime(modified_date[0], "%Y-%m-%d").date()
        new_print_date = datetime.strptime(modified_date[1], "%Y-%m-%d").date()
        affected_states = [s.lower() for s in modified_date[3]]
        
        # If this modification applies to our state and date
        if (state.lower() in affected_states and
            adjusted_start_date == scheduled_print_date):
            logger.debug(f"Found modified start date: {new_print_date}")
            return new_print_date
            
    return None

def add_business_days(start_date, total_prod_days, closed_dates):
    """
    Split the range by commas, handle possible dash range (e.g. '4737-4895').
    If 'postcode' is found or in range, return True.
    """
    postcodes = range_string.split(",")
    for segment in postcodes:
        segment = segment.strip()
        if "-" in segment:
            # e.g. "4737-4895"
            start, end = segment.split("-")
            # convert to int to compare numerically
            try:
                p = int(postcode)
                s = int(start)
                e = int(end)
                if p >= s and p <= e:
                    return True
            except ValueError:
                # if we can't parse as int, skip
                continue
        else:
            # single postcode
            if postcode == segment:
                return True
    return False

# --------------------------------------------------------------------
# Hub selection logic (Step 7)
# --------------------------------------------------------------------
def choose_production_hub(
    product_hubs: list[str],
    misDeliversToState: str,
    misCurrentHub: str,
    product_id: int,
    cmyk_hubs: list[dict]
) -> str:
    """
    Recreates your old JS snippet:
      1) if product_hubs has exactly one => use it
      2) else if misDeliversToState in product_hubs => use it
      3) else find the next best in cmykHubsJSON => pick the first that matches
      4) special QLD override => if product_id in [6,7,8,9], misCurrentHub != 'nqld', misDeliversToState='qld' => 'vic'
    """
    product_hubs_lower = [h.lower() for h in product_hubs]

    # 1) single production hub
    if len(product_hubs_lower) == 1:
        chosen = product_hubs_lower[0]
        logger.debug("Only one production hub => %s", chosen)
        # but let's apply the QLD override afterwards if needed
    else:
        # 2) if misDeliversToState is in product_hubs
        if misDeliversToState in product_hubs_lower:
            chosen = misDeliversToState
            logger.debug("DeliversToState is in product hubs => chosen=%s", chosen)
        else:
            # 3) next best from cmykHubs
            chosen = find_next_best(misDeliversToState, product_hubs_lower, cmyk_hubs)
            logger.debug("Next best => %s", chosen)

    # 4) QLD cards override. Leave NQLD cards in NQLD. QLD cards, send to VIC.
    if product_id in [6,7,8,9] and misCurrentHub != "nqld" and misDeliversToState == "qld":
        logger.debug("** QLD Card produce in => vic (overriding...)")
        chosen = "vic"

    return chosen

def find_next_best(delivers_to_state: str, product_hubs_lower: list[str], cmyk_hubs: list[dict]) -> str:
    """
    Looks in cmyk_hubs for the entry matching delivers_to_state, then loops its Next_Best
    array to find the first that is in product_hubs_lower. If none found, fallback to
    the first in product_hubs_lower.
    """
    fallback = None
    for entry in cmyk_hubs:
        if entry["State"].lower() == delivers_to_state:
            # check Next_Best
            for candidate in entry["Next_Best"]:
                if candidate.lower() in product_hubs_lower:
                    return candidate.lower()
            break
    # if no next best found, fallback
    return product_hubs_lower[0]

# --------------------------------------------------------------------
# Finishing + closed-date logic
# --------------------------------------------------------------------
def load_finishing_rules() -> FinishingRules:
    """Load finishing rules from JSON configuration"""
    try:
        rules_path = Path(__file__).parent.parent / "data" / "finishing_rules.json"
        with open(rules_path, "r") as f:
            rules_data = json.load(f)
        return FinishingRules(**rules_data)
    except Exception as e:
        logger.error(f"Error loading finishing rules: {e}")
        raise





def calculate_finishing_days(req: ScheduleRequest, product_obj: dict) -> int:
    """Calculate finishing days based on rules"""
    finishing_days = 0
    total_qty = req.misOrderQTY * req.kinds
    
    try:
        rules = load_finishing_rules()
    except Exception as e:
        logger.error(f"Failed to load finishing rules, using fallback logic: {e}")
        return calculate_finishing_days_fallback(req)
        
    # Process keyword rules
    for rule in rules.keywordRules:
        if not rule.enabled:
            continue
            
        # Check conditions and keywords
        if check_rule_conditions(rule, req, product_obj, total_qty) and check_keywords(rule, req.description):
            base_days = rule.addDays
            
            # Check for hub-specific overrides
            if rule.conditions and rule.conditions.hubOverrides:
                hub_days = rule.conditions.hubOverrides.get(req.misCurrentHub.lower())
                if hub_days is not None:
                    base_days = hub_days
                    
            finishing_days += base_days
            logger.debug(f"Rule '{rule.id}' applied: {rule.description} (+{base_days} days)")
            
    # Process center rules
    for rule in rules.centerRules:
        if not rule.enabled:
            continue
            
        # Check center ID and keywords
        if req.misCurrentHubID == rule.centerId and check_keywords(rule, req.description):
            finishing_days += rule.addDays
            logger.debug(f"Center rule '{rule.id}' applied: {rule.description} ({rule.addDays} days)")
            
    # Add any additional production days
    if req.additionalProductionDays > 0:
        finishing_days += req.additionalProductionDays
        logger.debug(f"Added {req.additionalProductionDays} additional production days")
        
    return finishing_days
    """Calculate finishing days based on rules"""
    total_qty = req.misOrderQTY * req.kinds
    
    try:
        rules = load_finishing_rules()
    except Exception as e:
        logger.error(f"Failed to load finishing rules, using fallback logic: {e}")
        return calculate_finishing_days_fallback(req)
        
    finishing_days = 0
    
    # Process keyword rules
    for rule in rules.keywordRules:
        if not rule.enabled:
            continue
            
        # Check conditions and keywords
        if check_rule_conditions(rule, req, product_obj, total_qty) and check_keywords(rule, req.description):
            base_days = rule.addDays
            
            # Check for hub-specific overrides
            if rule.conditions and rule.conditions.hubOverrides:
                hub_days = rule.conditions.hubOverrides.get(req.misCurrentHub.lower())
                if hub_days is not None:
                    base_days = hub_days
                    
            finishing_days += base_days
            logger.debug(f"Rule '{rule.id}' applied: {rule.description} (+{base_days} days)")
            
    # Process center rules
    for rule in rules.centerRules:
        if not rule.enabled:
            continue
            
        # Check center ID and keywords
        if req.misCurrentHubID == rule.centerId and check_keywords(rule, req.description):
            finishing_days += rule.addDays
            logger.debug(f"Center rule '{rule.id}' applied: {rule.description} ({rule.addDays} days)")
            
    # Add any additional production days
    if req.additionalProductionDays > 0:
        finishing_days += req.additionalProductionDays
        logger.debug(f"Added {req.additionalProductionDays} additional production days")
        
    return finishing_days

def calculate_finishing_days(req: ScheduleRequest, product_obj: dict) -> int:
    """Calculate finishing days based on rules"""
    finishing_days = 0
    total_qty = req.misOrderQTY * req.kinds
    
    try:
        rules = load_finishing_rules()
    except Exception as e:
        logger.error(f"Failed to load finishing rules, using fallback logic: {e}")
        return calculate_finishing_days_fallback(req)
        
    # Process keyword rules
    for rule in rules.keywordRules:
        if not rule.enabled:
            continue
            
        # Check conditions and keywords
        if check_rule_conditions(rule, req, product_obj, total_qty) and check_keywords(rule, req.description):
            base_days = rule.addDays
            
            # Check for hub-specific overrides
            if rule.conditions and rule.conditions.hubOverrides:
                hub_days = rule.conditions.hubOverrides.get(req.misCurrentHub.lower())
                if hub_days is not None:
                    base_days = hub_days
                    
            finishing_days += base_days
            logger.debug(f"Rule '{rule.id}' applied: {rule.description} (+{base_days} days)")
            
    # Process center rules
    for rule in rules.centerRules:
        if not rule.enabled:
            continue
            
        # Check center ID and keywords
        if req.misCurrentHubID == rule.centerId and check_keywords(rule, req.description):
            finishing_days += rule.addDays
            logger.debug(f"Center rule '{rule.id}' applied: {rule.description} ({rule.addDays} days)")
            
    # Add any additional production days
    if req.additionalProductionDays > 0:
        finishing_days += req.additionalProductionDays
        logger.debug(f"Added {req.additionalProductionDays} additional production days")
        
    return finishing_days

def check_rule_conditions(rule: FinishingRule, req: ScheduleRequest, product_obj: dict, total_qty: int) -> bool:
    """Check if conditions for a rule are met"""
    if not rule.conditions:
        return True
        
    conditions = rule.conditions
    
    # Quantity checks
    if conditions.quantityLessThan and total_qty >= conditions.quantityLessThan:
        return False
    if conditions.quantityGreaterThan and total_qty <= conditions.quantityGreaterThan:
        return False
    if conditions.quantityGreaterOrEqual and total_qty < conditions.quantityGreaterOrEqual:
        return False
        
    # Product ID checks
    if conditions.productIdEqual and product_obj["Product_ID"] != conditions.productIdEqual:
        return False
    if conditions.productIdNotEqual and product_obj["Product_ID"] == conditions.productIdNotEqual:
        return False
    if conditions.productIdIn and product_obj["Product_ID"] not in conditions.productIdIn:
        return False
        
    # Product group check
    if conditions.productGroupNotContains:
        if conditions.productGroupNotContains.lower() in product_obj["Product_Group"].lower():
            return False
            
    return True

def check_keywords(rule: Union[FinishingRule, CenterRule], description: str) -> bool:
    """Check if keywords match the description"""
    if not rule.keywords:
        return True
        
    desc = description if rule.caseSensitive else description.lower()
    keywords = rule.keywords
    if not rule.caseSensitive:
        keywords = [k.lower() for k in keywords]
        
    # Check excluded keywords first
    if rule.excludeKeywords:
        exclude_keywords = rule.excludeKeywords
        if not rule.caseSensitive:
            exclude_keywords = [k.lower() for k in exclude_keywords]
        if any(k in desc for k in exclude_keywords):
            return False
            
    # Check required keywords
    if rule.matchType == "all":
        return all(k in desc for k in keywords)
    else:  # "any"
        return any(k in desc for k in keywords)

def calculate_finishing_days_fallback(req: ScheduleRequest) -> int:
    """Fallback calculation if rules fail to load"""
    finishing_days = 0
    desc_lower = req.description.lower()
    total_qty = req.misOrderQTY * req.kinds

    if any(k in desc_lower for k in ["fold", "crease", "perf", "score"]):
        finishing_days += 1
        logger.debug("Fallback: +1 for fold/crease/perf/score")

    if any(k in desc_lower for k in ["round corner", "dril"]):
        finishing_days += 1
        logger.debug("Fallback: +1 for round corner/drill")

    if total_qty > 10000:
        finishing_days += 1
        logger.debug("Fallback: +1 for qty>10k")

    finishing_days += req.additionalProductionDays
    if req.additionalProductionDays > 0:
        logger.debug("Fallback: +%d from additionalProductionDays", req.additionalProductionDays)

    return finishing_days

def load_finishing_rules() -> FinishingRules:
    """Load finishing rules from JSON configuration"""
    try:
        rules_path = Path(__file__).parent.parent / "data" / "finishing_rules.json"
        with open(rules_path, "r") as f:
            rules_data = json.load(f)
        return FinishingRules(**rules_data)
    except Exception as e:
        logger.error(f"Error loading finishing rules: {e}")
        raise

def get_closed_dates_for_state(chosen_hub: str, cmyk_hubs: list[dict]) -> list[str]:
    """
    The 'chosen_hub' might be 'vic', 'qld', etc. We find the matching
    cmyk_hub entry => return its 'Closed_Dates'.
    """
    for entry in cmyk_hubs:
        if entry["Hub"].lower() == chosen_hub:
            return entry.get("Closed_Dates", [])
    # or maybe we also check if entry["State"].lower() == chosen_hub
    return []

def add_business_days(start_date, days_to_add, closed_dates):
    current_date = start_date

    # Initial check to move forward if start_date is on a weekend or closed date
    while current_date.weekday() in [5, 6] or str(current_date) in closed_dates:
        current_date += timedelta(days=1)

    adjusted_start_date = current_date  # Capture the adjusted start date

    days_count = 0

    while days_count < days_to_add:
        current_date += timedelta(days=1)
        # skip weekends
        if current_date.weekday() in [5, 6]:
            continue
        # skip closed dates
        if str(current_date) in closed_dates:
            continue
        days_count += 1

    return adjusted_start_date, current_date


def find_cmyk_hub_id(chosen_hub: str, cmyk_hubs: list[dict]) -> int:
    """
    Looks up 'chosen_hub' (e.g. 'vic', 'wa', 'qld') in cmyk_hubs
    and returns the corresponding CMHKhubID. If not found, returns 0.
    """
    for entry in cmyk_hubs:
        if entry["Hub"].lower() == chosen_hub.lower():
            return entry["CMHKhubID"]
    return 0  # fallback if no match