#shcedule_logic.py
#This module contains the main scheduling logic for processing an order request. It includes steps such as state overrides, hub selection, product matching, finishing days calculation, and date adjustments.
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
import pytz
from pathlib import Path
from pathlib import Path
from app.data_manager import get_production_groups_data
from app.production_group_mapper import match_production_groups


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
from app.hub_selection import validate_hub_rules, choose_production_hub

logger = logging.getLogger(__name__)
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
        
    # Load CMYK hubs data
    cmyk_hubs = get_cmyk_hubs_data()
    
    # Resolve current hub details
    from app.hub_utils import resolve_hub_details
    current_hub, current_hub_id = resolve_hub_details(
        current_hub=req.misCurrentHub,
        current_hub_id=req.misCurrentHubID,
        cmyk_hubs=cmyk_hubs
    )
    
    logger.debug(f"Resolved hub details: hub={current_hub}, id={current_hub_id}")
    
    # Update request with resolved values
    req.misCurrentHub = current_hub
    req.misCurrentHubID = current_hub_id
    

    # ----------------------------------------------------------------
    # Step 1a) State override for SA, TAS, ACT, and NQLD
    # ----------------------------------------------------------------
    if req.misDeliversToState.lower() in ["sa", "tas"]:
        logger.debug("MIS Delivers to: %s => treating as 'vic'", req.misDeliversToState)
        req.misDeliversToState = "vic"

    if req.misDeliversToState.lower() == "act":
        logger.debug("MIS Delivers to: %s => treating as 'nsw'", req.misDeliversToState)
        req.misDeliversToState = "nsw"

    if req.misCurrentHub.lower() == "nqld" and req.misDeliversToState.lower() == "qld":
        logger.debug("MIS Current hub is 'nqld' and delivers to QLD => setting misDeliversToState = 'nqld'")
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

    # ----------------------------------------------------------------
    # Step 1c) Add #wa tag to WA orders for special product matching
    # ----------------------------------------------------------------
    #if req.misCurrentHub.lower() == "wa":
    #    logger.debug("Current hub is WA => appending #wa tag to description")
    #    req.description = f"{req.description} #wa"    
    
    # ----------------------------------------------------------------
    # Step 1d) Assign production groups based on order description
    # ----------------------------------------------------------------
    production_groups_data = get_production_groups_data()
    assigned_groups = match_production_groups(req.description, production_groups_data)
    logger.debug(f"Assigned production groups: {assigned_groups}")
    
    # ----------------------------------------------------------------
    # Step 1e) Append additional tags to order description before product matching
    #         - If product is BC size, append " BC" to the description.
    #         - If description contains "premium uncoated", append " Digital" to the description.
    # ----------------------------------------------------------------
    # Check for BC size using dimensions similar to determine_grain_direction
    BC_LONG = 100
    BC_SHORT = 65
    if (max(req.preflightedWidth, req.preflightedHeight) <= BC_LONG and 
        min(req.preflightedWidth, req.preflightedHeight) <= BC_SHORT and 
        "bc" not in req.description.lower()):
        req.description += " BC"
        logger.debug("Appended ' BC' to description based on BC size criteria.")
    
    # Check for "premium uncoated" in description and add " Digital" if needed
    if "premium uncoated" in req.description.lower() and "digital" not in req.description.lower():
        req.description += " Digital"
        logger.debug("Appended ' Digital' to description based on premium uncoated condition.")
        

    # 2) Product matching
    product_keywords = get_product_keywords_data()

    logger.debug(f"Calling match_product_id with description='{req.description[:50]}...', "
             f"printType={req.printType}, hubID={req.misCurrentHubID}")
    found_product_id = match_product_id(req.description, product_keywords, req.printType, req.misCurrentHubID)

    if found_product_id is None:
        logger.debug("No matching product found => using fallback product_id=99")
        found_product_id = 99

    product_info = get_product_info_data()
    product_obj = product_info.get(str(found_product_id), None)
    if not product_obj:
        logger.debug("product_id=%s not found in product_info => fallback schedule, using product 99", found_product_id)
        # fallback product with all required fields
        product_obj = {
            "Product_Group": "No Group Found",
            "Product_Category": "Unmatched Product",
            "Product_ID": 99,
            "Cutoff": "12",
            "Days_to_produce": "2",
            "Production_Hub": ["vic"],
            "Start_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
            "SynergyPreflight": 0,
            "SynergyImpose": 0,
            "EnableAutoHubTransfer": 1,
            "Modified_run_date": [],
            "Production_Hub": ["vic"]
        }

    # 3) Determine grain direction
    grain_str, grain_id = determine_grain_direction(
        orientation=req.orientation,
        width=req.preflightedWidth,
        height=req.preflightedHeight,
        description=req.description
    )

    # 4) Get timezone from hub config
    cmyk_hubs = get_cmyk_hubs_data()
    hub_timezone = None
    for hub in cmyk_hubs:
        if hub["Hub"].lower() == req.misCurrentHub.lower():
            hub_timezone = pytz.timezone(hub["Timezone"])
            logger.debug(f"Found timezone {hub['Timezone']} for hub {req.misCurrentHub}")
            break
    
    if not hub_timezone:
        # Fallback to Melbourne time if hub not found
        logger.warning(f"No timezone found for hub {req.misCurrentHub}, falling back to Melbourne time")
        hub_timezone = pytz.timezone('Australia/Melbourne')
    
    # Get current time in hub's timezone
    current_time = datetime.now(hub_timezone)
    logger.debug(f"Current time in {hub_timezone}: {current_time}")

    # 5) Cutoff check
    cutoff_hour = int(product_obj["Cutoff"])
    logger.debug(f"Checking cutoff: current hour={current_time.hour} ({hub_timezone}), cutoff hour={cutoff_hour}")
    
    if current_time.hour >= cutoff_hour:
        start_date = (current_time + timedelta(days=1)).date()
        cutoff_status = "After Cutoff"
        logger.debug(f"After cutoff: current_time={current_time} ({hub_timezone}), moving start date to next day={start_date}")
    else:
        start_date = current_time.date()
        cutoff_status = "Before Cutoff"
        logger.debug(f"Before cutoff: current_time={current_time} ({hub_timezone}), keeping start date as today={start_date}")

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
        cmyk_hubs=cmyk_hubs,
        print_type=req.printType
    )
    
    logger.debug(f"Initial hub selection: {initial_hub}, Final hub after rules: {chosen_hub}")
    
    # Enable or disable hub transfer
    enable_auto_hub_transfer = 1 if chosen_hub.lower() != current_hub.lower() else 0
    logger.debug(f"Setting enableAutoHubTransfer={enable_auto_hub_transfer} (chosen_hub={chosen_hub}, current_hub={current_hub})")

    

    # Find the actual cmykHubID for that chosen hub
    chosen_hub_id = find_cmyk_hub_id(chosen_hub, cmyk_hubs)
    
    # 8) add business days for final dispatch
    closed_dates = get_closed_dates_for_state(chosen_hub, cmyk_hubs)
    adjusted_start_date, dispatch_date = add_business_days(start_date, total_prod_days, closed_dates)

    # 9) Check for modified run dates
    modified_start = check_modified_run_dates(
        adjusted_start_date,
        product_obj,
        chosen_hub
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
        orderId=req.orderId,
        orderDescription=req.description,
        currentHub=current_hub,
        currentHubId=current_hub_id,
        productId=found_product_id,
        productGroup=product_obj["Product_Group"],
        productCategory=product_obj["Product_Category"],
        productionHubs=product_obj["Production_Hub"],
        productionGroups=assigned_groups,
        preflightedWidth=req.preflightedWidth,
        preflightedHeight=req.preflightedHeight,
        
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
        enableAutoHubTransfer=enable_auto_hub_transfer
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

def check_modified_run_dates(adjusted_start_date: datetime.date, product_obj: dict, chosen_hub: str) -> Optional[datetime.date]: # MODIFIED: Renamed 'state' argument to 'chosen_hub'
    """
    Check if there's a modified run date that applies to this order based on
    original print date and the chosen production hub.
    Only returns the new print date if a modification applies.

    Args:
        adjusted_start_date: The calculated start date after weekday adjustments
        product_obj: The product object containing Modified_run_date array
        chosen_hub: The final selected production hub (e.g., 'vic', 'nsw') # MODIFIED: Description updated

    Returns:
        datetime.date: New start date if modified, None if no modification applies
    """
    modified_dates = product_obj.get("Modified_run_date", [])
    logger.debug(f"Checking modified run dates for product {product_obj.get('Product_ID', 'N/A')} against date {adjusted_start_date} and chosen hub {chosen_hub}") # MODIFIED: Log message updated

    for modified_date in modified_dates:
        # Expecting 3 elements: [OrigPrint, NewPrint, [States/Hubs]] - Assume the list contains hub names matching state abbreviations for now
        if not isinstance(modified_date, list) or len(modified_date) < 3:
            logger.warning(f"Skipping malformed override entry: {modified_date}")
            continue

        try:
            # Validate and parse dates
            scheduled_print_date_str = modified_date[0]
            new_print_date_str = modified_date[1]
            if not scheduled_print_date_str or not new_print_date_str:
                 logger.warning(f"Skipping override due to missing date(s): {modified_date}")
                 continue
            scheduled_print_date = datetime.strptime(scheduled_print_date_str, "%Y-%m-%d").date()
            new_print_date = datetime.strptime(new_print_date_str, "%Y-%m-%d").date()

            # Validate states/hubs list (assuming it contains hub names like 'vic', 'nsw')
            affected_hubs_raw = modified_date[2] # Renamed variable for clarity
            if not isinstance(affected_hubs_raw, list):
                 logger.warning(f"Skipping override due to invalid affected hubs format: {modified_date}")
                 continue
            affected_hubs = [h.lower() for h in affected_hubs_raw if isinstance(h, str)] # Renamed variable for clarity

        except (ValueError, TypeError, IndexError) as e:
            logger.warning(f"Skipping override due to parsing error ({e}): {modified_date}")
            continue

        logger.debug(f"Evaluating override: TargetDate={scheduled_print_date}, NewDate={new_print_date}, TargetHubs={affected_hubs}") # MODIFIED: Log message updated

        # MODIFIED: If this modification applies to our chosen hub and date
        if (chosen_hub.lower() in affected_hubs and
            adjusted_start_date == scheduled_print_date):
            logger.debug(f"Override MATCHED: Applying modified start date: {new_print_date} for original {scheduled_print_date} in hub {chosen_hub}") # MODIFIED: Log message updated
            return new_print_date
        else:
             # MODIFIED: Updated log condition check description
            logger.debug(f"Override NO MATCH: Hub match ({chosen_hub.lower()} in {affected_hubs}): {chosen_hub.lower() in affected_hubs}, Date match: {adjusted_start_date == scheduled_print_date}")

    logger.debug("No applicable modified run date found.")
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
        logger.debug("** QLD cards override. Leave NQLD cards in NQLD. QLD cards, send to VIC)")
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