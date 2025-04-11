#shcedule_logic.py
#This module contains the main scheduling logic for processing an order request. It includes steps such as state overrides, hub selection, product matching, finishing days calculation, and date adjustments.
import json
import logging
from datetime import datetime, timedelta, timezone, date
from typing import Optional, Tuple
import pytz
from pathlib import Path
from pathlib import Path
from app.data_manager import get_production_groups_data
from app.production_group_mapper import match_production_groups
from app.imposing_logic import determine_imposing_action
from app.preflight_logic import determine_preflight_action 
from app.hub_utils import resolve_hub_details


from app.models import (
    ScheduleRequest,
    ScheduleResponse,
    FinishingRules,
    FinishingRule,
    CenterRule,
    RuleConditions

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

# --- NEW HELPER FUNCTION ---
def find_last_natural_run_date(target_date: date, allowed_start_days: list[str]) -> date:
    """
    Find the most recent past or current allowed start day relative to the target_date.
    """
    day_map = {
        0: "Monday", 1: "Tuesday", 2: "Wednesday",
        3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"
    }
    current_date = target_date
    # Iterate backwards up to 7 days (guarantees finding the last run day in the cycle)
    for _ in range(7):
        current_day_name = day_map[current_date.weekday()]
        if current_day_name in allowed_start_days:
            logger.debug(f"[find_last_natural_run_date] Found last natural run date relative to {target_date}: {current_date}")
            return current_date
        current_date -= timedelta(days=1)
    # Should ideally not be reached if allowed_start_days is valid, but return original date as fallback
    logger.warning(f"[find_last_natural_run_date] Could not find a recent run day for {target_date} and {allowed_start_days}. Returning original date.")
    return target_date

# --- NEW HELPER FUNCTION ---
def find_next_natural_run_date(target_date: datetime.date, allowed_start_days: list[str]) -> datetime.date:
    """
    Find the next allowed start day on or after the target_date.
    Similar to get_next_valid_start_day but finds the *next occurrence*.
    """
    day_map = {
        0: "Monday", 1: "Tuesday", 2: "Wednesday",
        3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"
    }
    current_date = target_date
    while True:
        current_day_name = day_map[current_date.weekday()]
        if current_day_name in allowed_start_days:
            logger.debug(f"[find_next_natural_run_date] Found next natural run date: {current_date} (Allowed: {allowed_start_days})")
            return current_date
        current_date += timedelta(days=1)

# --- MODIFIED HELPER FUNCTION ---
def check_and_apply_override(
    potential_run_date: datetime.date,
    product_obj: dict,
    chosen_hub: str
) -> Optional[datetime.date]:
    """
    Checks if an override applies to the potential_run_date for the chosen_hub.
    Returns the *new* print date if an override exists, otherwise None.
    """
    modified_dates = product_obj.get("Modified_run_date", [])
    logger.debug(f"[check_and_apply_override] Checking overrides for Product {product_obj.get('Product_ID', 'N/A')} on potential date {potential_run_date} for Hub {chosen_hub}")

    for override_entry in modified_dates:
        if not isinstance(override_entry, list) or len(override_entry) < 3:
            logger.warning(f"Skipping malformed override entry: {override_entry}")
            continue

        try:
            orig_print_str = override_entry[0]
            new_print_str = override_entry[1]
            affected_hubs_raw = override_entry[2]

            if not orig_print_str or not new_print_str or not isinstance(affected_hubs_raw, list):
                logger.warning(f"Skipping override due to missing/invalid data: {override_entry}")
                continue

            orig_print_date = datetime.strptime(orig_print_str, "%Y-%m-%d").date()
            new_print_date = datetime.strptime(new_print_str, "%Y-%m-%d").date()
            affected_hubs = [h.lower() for h in affected_hubs_raw if isinstance(h, str)]

        except (ValueError, TypeError, IndexError) as e:
            logger.warning(f"Skipping override due to parsing error ({e}): {override_entry}")
            continue

        # Check if the override matches the potential run date and the chosen hub
        if potential_run_date == orig_print_date and chosen_hub.lower() in affected_hubs:
            logger.info(f"Override MATCHED: Product {product_obj.get('Product_ID', 'N/A')} run on {orig_print_date} for hub {chosen_hub} moved to {new_print_date}.")
            return new_print_date # Return the NEW date

    logger.debug(f"No applicable override found for {potential_run_date} in hub {chosen_hub}.")
    return None # No override applies to this specific date/hub


# --- process_order Function ---
def process_order(req: ScheduleRequest) -> Optional[ScheduleResponse]:
    """
    Main function to schedule an order... (docstring unchanged)
    """
    # ... (Steps 1-4: Initial setup, Product Matching, Hub Selection, Timezone/Sim Time remain the same) ...
    # --- GET ACTUAL PROCESSING TIME (UTC first) ---
    actual_now_utc = datetime.now(timezone.utc)
    log_payload = req.dict()
    logger.info(f"--- Received /schedule request (OrderID: {req.orderId or 'N/A'}) ---")
    if req.timeOffsetHours != 0:
        logger.info(f"Time Offset Hours specified: {req.timeOffsetHours}")
    logger.debug(f"Request Payload Data: {log_payload}")

    # Set default postcode if it's null or empty
    if not req.misDeliversToPostcode:
        req.misDeliversToPostcode = "0000"

    # Load core data
    cmyk_hubs = get_cmyk_hubs_data()
    hub_data = get_hub_data()
    product_info = get_product_info_data()
    product_keywords = get_product_keywords_data()

    # Resolve current hub details
    current_hub, current_hub_id = resolve_hub_details(
        current_hub=req.misCurrentHub,
        current_hub_id=req.misCurrentHubID,
        cmyk_hubs=cmyk_hubs
    )
    logger.info(f"Resolved Current Hub: Name='{current_hub}', ID={current_hub_id}")
    req.misCurrentHub = current_hub
    req.misCurrentHubID = current_hub_id

    # ----------------------------------------------------------------
    # Step 1: State/Postcode Overrides & Initial Setup
    # ----------------------------------------------------------------
    original_delivers_to_state = req.misDeliversToState

    # --- NEW: Handle missing/invalid misDeliversToState ---
    # Check for None, or string "null"/"undefined" (case-insensitive)
    if req.misDeliversToState is None or \
       (isinstance(req.misDeliversToState, str) and req.misDeliversToState.lower() in ["null", "undefined"]):
        logger.warning(f"misDeliversToState is missing or invalid ('{original_delivers_to_state}'). Using currentHub ('{current_hub}') as fallback.")
        req.misDeliversToState = current_hub # Use the resolved current_hub name
        original_delivers_to_state = req.misDeliversToState # Update original_delivers_to_state for logging consistency if needed later
    # --- END NEW ---

    # Existing state overrides (now checks the potentially updated misDeliversToState)
    if req.misDeliversToState.lower() in ["sa", "tas"]:
        logger.debug(f"State Override: {original_delivers_to_state} -> vic")
        req.misDeliversToState = "vic"
    elif req.misDeliversToState.lower() == "act":
        logger.debug(f"State Override: {original_delivers_to_state} -> nsw")
        req.misDeliversToState = "nsw"
    if current_hub.lower() == "nqld" and req.misDeliversToState.lower() == "qld":
         logger.debug("NQLD Override: Current Hub is NQLD delivering to QLD -> Treating misDeliversToState as 'nqld' for hub selection.")
         req.misDeliversToState = "nqld"

    override_info = lookup_hub_by_postcode(req.misDeliversToPostcode, hub_data)
    if override_info:
        logger.debug(f"Postcode Override: {req.misDeliversToPostcode} -> {override_info['hubName']}")
        req.misDeliversToState = override_info["hubName"]

    original_description = req.description
    BC_LONG = 100
    BC_SHORT = 65
    if (max(req.preflightedWidth, req.preflightedHeight) <= BC_LONG and
        min(req.preflightedWidth, req.preflightedHeight) <= BC_SHORT and
        "bc" not in req.description.lower()):
        req.description += " BC"
        logger.debug("Appended ' BC' to description based on size.")

    # --- NEW: Check for Premium Uncoated BC and force Digital printType ---
    desc_lower = req.description.lower()
    if "premium uncoated" in desc_lower and "bc" in desc_lower:
        if req.printType != 2:
            logger.info(f"Order description contains 'premium uncoated' and 'bc'. Overriding printType from {req.printType} to 2 (Digital).")
            req.printType = 2
        else:
            logger.debug("Order description contains 'premium uncoated' and 'bc', and printType is already 2 (Digital). No change needed.")
    # --- END NEW ---


    # ----------------------------------------------------------------
    # Step 2: Product Matching & Production Group Assignment
    # ----------------------------------------------------------------
    logger.debug(f"Matching Product: Desc='{req.description[:50]}...', PrintType={req.printType}, HubID={current_hub_id}")
    found_product_id = match_product_id(req.description, product_keywords, req.printType, current_hub_id)
    if found_product_id is None:
        logger.warning("No matching product found => using fallback product_id=99")
        found_product_id = 99

    product_obj = product_info.get(str(found_product_id))
    if not product_obj:
        logger.error(f"Product ID {found_product_id} not found in product_info.json! Using hardcoded fallback.")
        product_obj = {
            "Product_Category": "Default Fallback Product", "Product_Group": "Unknown", "Product_ID": 99,
            "Production_Hub": ["vic", "nsw", "qld", "wa", "nqld"], "Cutoff": "12", "SynergyPreflight": 0, "SynergyImpose": 0,
            "EnableAutoHubTransfer": 1, "scheduleAppliesTo": [1, 2, 3, 5, 24], "Start_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
            "Days_to_produce": "3", "Modified_run_date": [], "printTypes": [1, 2, 3]
        }
    logger.info(f"Matched Product: ID={found_product_id}, Group='{product_obj.get('Product_Group')}', Category='{product_obj.get('Product_Category')}'")

    production_groups_data = get_production_groups_data()
    assigned_groups = match_production_groups(original_description, production_groups_data)
    logger.debug(f"Assigned Production Groups: {assigned_groups}")

    grain_str, grain_id = determine_grain_direction(
        orientation=req.orientation, width=req.preflightedWidth, height=req.preflightedHeight, description=original_description
    )
    logger.debug(f"Determined Grain: {grain_str} (ID: {grain_id})")

    # ----------------------------------------------------------------
    # Step 3: Choose Final Production Hub
    # ----------------------------------------------------------------
    product_hubs = product_obj.get("Production_Hub", [])
    # Call the choose_production_hub function (now imported from hub_selection.py)
    # to get the *initial* candidate hub.
    initial_hub = choose_production_hub(
        product_hubs=product_hubs,
        misDeliversToState=req.misDeliversToState, # Pass the potentially modified state
        current_hub=current_hub, # Pass the resolved current hub name
        current_hub_id=current_hub_id, # Pass the resolved current hub ID
        product_id=found_product_id,
        cmyk_hubs=cmyk_hubs
    )
    logger.debug(f"Initial Hub Choice determined by choose_production_hub: {initial_hub}")

    # Call validate_hub_rules (now imported from hub_selection.py)
    # This function now performs the iterative validation starting with initial_hub.
    chosen_hub = validate_hub_rules(
        initial_hub=initial_hub,
        available_hubs=product_hubs,
        delivers_to_state=req.misDeliversToState, # Pass the potentially modified state
        # Pass necessary order details for rule evaluation
        description=req.description,
        width=req.preflightedWidth,
        height=req.preflightedHeight,
        quantity=req.misOrderQTY * req.kinds,
        product_id=found_product_id,
        product_group=product_obj.get("Product_Group", "Unknown"),
        print_type=req.printType,
        # Pass config data
        cmyk_hubs=cmyk_hubs
    )
    logger.info(f"Final Chosen Production Hub (after iterative rules validation): {chosen_hub}")
    chosen_hub_id = find_cmyk_hub_id(chosen_hub, cmyk_hubs)
    logger.debug(f"Chosen Hub ID: {chosen_hub_id}")
    enable_auto_hub_transfer = 1 if chosen_hub.lower() != current_hub.lower() else 0
    logger.debug(f"EnableAutoHubTransfer: {enable_auto_hub_transfer} (Chosen: {chosen_hub}, Current: {current_hub})")

    # ----------------------------------------------------------------
    # Step 4: Determine Hub Timezone and Simulated Time
    # ----------------------------------------------------------------
    hub_timezone_str = 'Australia/Melbourne'
    for hub_config in cmyk_hubs:
        if hub_config["Hub"].lower() == chosen_hub.lower():
            hub_timezone_str = hub_config.get("Timezone", hub_timezone_str)
            break
    try: hub_timezone = pytz.timezone(hub_timezone_str)
    except pytz.UnknownTimeZoneError:
        logger.error(f"Invalid timezone '{hub_timezone_str}' for hub {chosen_hub}. Falling back to Melbourne.")
        hub_timezone = pytz.timezone('Australia/Melbourne')

    actual_time_hub_tz = actual_now_utc.astimezone(hub_timezone)
    offset_hours = req.timeOffsetHours or 0
    simulated_time = actual_time_hub_tz + timedelta(hours=offset_hours)
    logger.info(f"Actual Time ({hub_timezone.zone}): {actual_time_hub_tz.strftime('%Y-%m-%d %H:%M:%S %Z%z')}")
    if offset_hours != 0: logger.info(f"Simulated Time ({hub_timezone.zone}, Offset: {offset_hours}h): {simulated_time.strftime('%Y-%m-%d %H:%M:%S %Z%z')}")
    else: logger.debug("No time offset applied. Using actual hub time for calculations.")

    current_processing_time = simulated_time

    # ----------------------------------------------------------------
   # ----------------------------------------------------------------
    # Step 5: Determine Effective Run Date & Apply Cutoff (REVISED LOGIC)
    # ----------------------------------------------------------------
    allowed_start_days = product_obj.get("Start_days", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
    cutoff_hour = int(product_obj.get("Cutoff", "12"))
    today_date = current_processing_time.date()

    # 5a. Find the natural run dates surrounding today
    last_natural_run_date = find_last_natural_run_date(today_date, allowed_start_days)
    next_natural_run_date = find_next_natural_run_date(today_date, allowed_start_days)
    logger.debug(f"Relevant Natural Run Dates: Last/Current Cycle = {last_natural_run_date}, Next Cycle = {next_natural_run_date}")

    # 5b. Check for overrides affecting these dates
    overridden_last_to_future_date = None
    override_from_last_run = check_and_apply_override(last_natural_run_date, product_obj, chosen_hub)
    if override_from_last_run and override_from_last_run >= today_date:
        overridden_last_to_future_date = override_from_last_run
        logger.debug(f"Last natural run ({last_natural_run_date}) was overridden to a relevant future date: {overridden_last_to_future_date}")

    overridden_next_run_date = check_and_apply_override(next_natural_run_date, product_obj, chosen_hub)
    if overridden_next_run_date:
         logger.debug(f"Next natural run ({next_natural_run_date}) is overridden to: {overridden_next_run_date}")

    # 5c. Determine the date to check cutoff against AND the corresponding natural date
    effective_run_date_for_cutoff = None
    natural_date_for_this_cycle = None # Track which natural date this effective date corresponds to

    if overridden_last_to_future_date:
        effective_run_date_for_cutoff = overridden_last_to_future_date
        natural_date_for_this_cycle = last_natural_run_date # This effective date came from the last cycle
        logger.info(f"Using overridden last run ({natural_date_for_this_cycle}) as effective date for cutoff: {effective_run_date_for_cutoff}")
    elif overridden_next_run_date:
        effective_run_date_for_cutoff = overridden_next_run_date
        natural_date_for_this_cycle = next_natural_run_date # This effective date came from the next cycle
        logger.info(f"Using overridden next run ({natural_date_for_this_cycle}) as effective date for cutoff: {effective_run_date_for_cutoff}")
    else:
        effective_run_date_for_cutoff = next_natural_run_date
        natural_date_for_this_cycle = next_natural_run_date # This effective date IS the next natural date
        logger.info(f"Using next natural run ({natural_date_for_this_cycle}) as effective date for cutoff: {effective_run_date_for_cutoff}")

    # 5d. Apply cutoff logic using the effective_run_date_for_cutoff
    cutoff_status = "Unknown"
    calculated_start_date = None # This will be the date production *starts*

    if today_date < effective_run_date_for_cutoff:
        cutoff_status = "Before Cutoff (Scheduled for Effective Run)"
        calculated_start_date = effective_run_date_for_cutoff
        logger.debug(f"Cutoff Check: Today ({today_date}) is before effective run {effective_run_date_for_cutoff}. Scheduling for {calculated_start_date}.")
    elif today_date == effective_run_date_for_cutoff:
        if current_processing_time.hour < cutoff_hour:
            cutoff_status = "Before Cutoff"
            calculated_start_date = effective_run_date_for_cutoff
            logger.debug(f"Cutoff Check: Order time ({current_processing_time.strftime('%H:%M')}) on effective run date ({effective_run_date_for_cutoff}) is BEFORE cutoff ({cutoff_hour}:00). Scheduling for {calculated_start_date}.")
        else:
            # --- AFTER CUTOFF on Effective Day ---
            cutoff_status = "After Cutoff"
            # Find the *next* natural run date STRICTLY AFTER the natural date corresponding to the missed run
            next_cycle_natural_run_date = find_next_natural_run_date(natural_date_for_this_cycle + timedelta(days=1), allowed_start_days)
            # Check if THAT subsequent run is also overridden
            overridden_next_cycle_run = check_and_apply_override(next_cycle_natural_run_date, product_obj, chosen_hub)
            calculated_start_date = overridden_next_cycle_run if overridden_next_cycle_run else next_cycle_natural_run_date
            logger.debug(f"Cutoff Check: Order time ({current_processing_time.strftime('%H:%M')}) on effective run date ({effective_run_date_for_cutoff}) is AFTER cutoff ({cutoff_hour}:00). Scheduling for next cycle starting {calculated_start_date} (Based on natural date {next_cycle_natural_run_date}, Overridden: {overridden_next_cycle_run})")
            # --- End After Cutoff on Effective Day ---
    else: # today_date > effective_run_date_for_cutoff
        # --- AFTER CUTOFF because Effective Day Passed ---
        cutoff_status = "After Cutoff (Effective Run Date Passed)"
        # Find the *next* natural run date STRICTLY AFTER the natural date corresponding to the missed run
        next_cycle_natural_run_date = find_next_natural_run_date(natural_date_for_this_cycle + timedelta(days=1), allowed_start_days)
        # Check if THAT subsequent run is overridden
        overridden_next_cycle_run = check_and_apply_override(next_cycle_natural_run_date, product_obj, chosen_hub)
        calculated_start_date = overridden_next_cycle_run if overridden_next_cycle_run else next_cycle_natural_run_date
        logger.debug(f"Cutoff Check: Today ({today_date}) is AFTER the effective run date ({effective_run_date_for_cutoff}). Scheduling for next cycle starting {calculated_start_date} (Based on natural date {next_cycle_natural_run_date}, Overridden: {overridden_next_cycle_run})")
        # --- End After Cutoff Effective Day Passed ---


    # ----------------------------------------------------------------
    # Step 6: Calculate Finishing Days & Total Production Days
    # ----------------------------------------------------------------
    base_prod_days = int(product_obj.get("Days_to_produce", 1))
    finishing_days = calculate_finishing_days(req, product_obj, chosen_hub) # Pass final chosen_hub
    total_prod_days = base_prod_days + finishing_days
    logger.info(f"Production Days: Base={base_prod_days}, Finishing={finishing_days}, Total={total_prod_days}")

    # ----------------------------------------------------------------
    # Step 7: Calculate Final Adjusted Start and Dispatch Dates
    # ----------------------------------------------------------------
    closed_dates = get_closed_dates_for_state(chosen_hub, cmyk_hubs)
    logger.debug(f"Closed dates for Hub {chosen_hub}: {closed_dates}")

    # Adjust the calculated_start_date for weekends/closed dates, and calculate dispatch date
    adjusted_start_date, dispatch_date = add_business_days(calculated_start_date, total_prod_days, closed_dates)
    logger.info(f"Final Schedule: Adjusted Start Date={adjusted_start_date}, Dispatch Date={dispatch_date}")


    # Build debug log (updated)
    debug_log = (
        f"CutoffStatus='{cutoff_status}' (EffectiveRunDate={effective_run_date_for_cutoff}, CutoffHour={cutoff_hour}), "
        f"CalculatedStartDate={calculated_start_date}, AdjustedStartDate={adjusted_start_date}, "
        f"ProdDaysBase={base_prod_days}, FinishingDays={finishing_days}, TotalProdDays={total_prod_days}, "
        f"ChosenHub={chosen_hub}, DispatchDate={dispatch_date}"
    )
    logger.debug("SCHEDULE LOG: " + debug_log)

    # ----------------------------------------------------------------
    # Step 8: Determine Imposing and Preflight Actions
    # ----------------------------------------------------------------
    final_synergy_impose = determine_imposing_action(req, found_product_id)
    # Now returns a tuple: (profile_id, profile_name)
    final_synergy_preflight_id, final_preflight_profile_name = determine_preflight_action(req, found_product_id)
    logger.debug(f"SynergyImpose={final_synergy_impose}, SynergyPreflightID={final_synergy_preflight_id}, PreflightProfileName={final_preflight_profile_name} (after rules)")

    # ----------------------------------------------------------------
    # Step 9: Prepare Response
    # ----------------------------------------------------------------
    time_format = '%A, %Y-%m-%d %H:%M:%S %Z (%z)'
    actual_processing_time_str = actual_time_hub_tz.strftime(time_format)
    simulated_processing_time_str = simulated_time.strftime(time_format) if offset_hours != 0 else None

    # --- NEW: Handle Fallback Product 99 ---
    dispatch_date_str: Optional[str] = str(dispatch_date) # Convert date to string initially, add Optional type hint
    if found_product_id == 99:
        logger.warning("Fallback Product ID 99 detected. Setting dispatchDate to null and disabling auto hub transfer.")
        dispatch_date_str = None # Set to None, which serializes to null
        enable_auto_hub_transfer = 0
    # --- END NEW ---

    return ScheduleResponse(
        # Pass through request details + calculated values
        orderId=req.orderId,
        orderDescription=original_description, # Return original description
        currentHub=current_hub,
        currentHubId=current_hub_id,
        # --- POPULATE NEW FIELDS ---
        misDeliversToState=req.misDeliversToState, # Use the potentially modified state
        misDeliversToPostcode=req.misDeliversToPostcode,
        printType=req.printType,
        # --- END POPULATE NEW FIELDS ---
        productId=found_product_id,
        productGroup=product_obj.get("Product_Group", "Unknown"),
        productCategory=product_obj.get("Product_Category", "Unknown"),
        productionHubs=product_obj.get("Production_Hub", []),
        productionGroups=assigned_groups,
        preflightedWidth=req.preflightedWidth,
        preflightedHeight=req.preflightedHeight,

        cutoffStatus=cutoff_status,
        productStartDays=allowed_start_days,
        productCutoff=str(cutoff_hour),
        daysToProduceBase=base_prod_days,
        finishingDays=finishing_days,
        totalProductionDays=total_prod_days,

        orderPostcode=req.misDeliversToPostcode,
        chosenProductionHub=chosen_hub,
        hubTransferTo=chosen_hub_id,

        # Use the final calculated dates
        startDate=str(calculated_start_date), # The date *before* weekend/holiday adjustment
        adjustedStartDate=str(adjusted_start_date), # The date *after* weekend/holiday adjustment
        dispatchDate=dispatch_date_str, # Use the potentially overridden string value

        grainDirection=grain_str,
        orderQuantity=req.misOrderQTY,
        orderKinds=req.kinds,
        totalQuantity=req.misOrderQTY * req.kinds,

        synergyPreflight=final_synergy_preflight_id, # Use the ID returned by determine_preflight_action
        preflightProfileName=final_preflight_profile_name, # Use the name returned by determine_preflight_action
        synergyImpose=final_synergy_impose,
        enableAutoHubTransfer=enable_auto_hub_transfer,

        actualProcessingTime=actual_processing_time_str,
        simulatedProcessingTime=simulated_processing_time_str
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

def get_first_valid_production_day(date_to_check: datetime.date, allowed_start_days: list[str]) -> datetime.date:
    """
    Find the first allowed production day on or after the given date.

    Args:
        date_to_check: The date to start checking from.
        allowed_start_days: List of allowed weekdays (e.g., ["Monday", "Wednesday"]).

    Returns:
        datetime.date: The first valid production date.
    """
    day_map = {
        0: "Monday", 1: "Tuesday", 2: "Wednesday",
        3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"
    }
    current_date = date_to_check
    while True:
        current_day_name = day_map[current_date.weekday()]
        if current_day_name in allowed_start_days:
             logger.debug(f"[get_first_valid_production_day] Found valid production day: {current_date} (Allowed: {allowed_start_days})")
             return current_date
        # logger.debug(f"[get_first_valid_production_day] Skipping {current_date} ({current_day_name})")
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


def check_rule_conditions(rule: FinishingRule, req: ScheduleRequest, product_obj: dict, total_qty: int, chosen_production_hub: str) -> bool:
    """Check if conditions for a rule are met"""
    if not rule.conditions:
        return True
        
    conditions = rule.conditions # type: RuleConditions # Add type hint for clarity

    # Production Hub Check 
    if conditions.productionHubIs:
        # Ensure comparison is case-insensitive
        if chosen_production_hub.lower() not in [h.lower() for h in conditions.productionHubIs]:
            logger.debug(f"Condition Check Failed: Chosen hub '{chosen_production_hub}' not in {conditions.productionHubIs}")
            return False
    
    
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
     # Simple fallback if rules file fails - maybe add 1 day for common finishing?
     logger.warning("Using fallback finishing days calculation (returning 0).")
     return 0

def calculate_finishing_days(req: ScheduleRequest, product_obj: dict, chosen_hub: str) -> int:
    """Calculate finishing days based on rules"""
    finishing_days = 0
    total_qty = req.misOrderQTY * req.kinds
    logger.debug(f"[calculate_finishing_days] Starting calculation for Order: {req.orderId}, ChosenHub: {chosen_hub}") # Log entry point

    try:
        rules = load_finishing_rules()
    except Exception as e:
        logger.error(f"Failed to load finishing rules, using fallback logic: {e}")
        return calculate_finishing_days_fallback(req)

    # --- Process keyword rules (No change here) ---
    logger.debug("[calculate_finishing_days] Processing Keyword Rules...")
    for rule in rules.keywordRules:
        if not rule.enabled:
            continue

        if check_rule_conditions(rule, req, product_obj, total_qty, chosen_hub) and check_keywords(rule, req.description):
            base_days = rule.addDays
            if rule.conditions and rule.conditions.hubOverrides:
                hub_days = rule.conditions.hubOverrides.get(req.misCurrentHub.lower())
                if hub_days is not None:
                    logger.debug(f"Applying hubOverride for rule '{rule.id}' in hub '{req.misCurrentHub.lower()}': {hub_days} days instead of {base_days}")
                    base_days = hub_days
            finishing_days += base_days
            logger.debug(f"Rule '{rule.id}' applied: {rule.description} (+{base_days} days)")

    # --- Process center rules ---
    logger.debug("[calculate_finishing_days] Processing Center Rules...")
# --- Process center rules ---
    logger.debug("[calculate_finishing_days] Processing Center Rules...")
    logger.debug(f"[calculate_finishing_days] Value of req.centerId before check: {req.centerId}, Type: {type(req.centerId)}")

    if req.centerId is not None:
        logger.debug(f"[calculate_finishing_days] Evaluating Center Rules against provided centerId: {req.centerId}")
        for rule in rules.centerRules: # rule is now guaranteed to be a CenterRule
            if not rule.enabled:
                logger.debug(f"[calculate_finishing_days] Center rule '{rule.id}' skipped (disabled).")
                continue

            logger.debug(f"[calculate_finishing_days] Comparing Request centerId ({req.centerId}, type={type(req.centerId)}) with Rule centerId ({rule.centerId}, type={type(rule.centerId)})")

            # Check if the centerId matches
            if req.centerId == rule.centerId:
                # --- Start Inline Exclusion Check (Replaces check_keywords for CenterRule) ---
                exclude_match_found = False
                if rule.excludeKeywords: # Check if the rule has exclusion keywords
                    desc_check = req.description if rule.caseSensitive else req.description.lower()
                    exclude_kws = rule.excludeKeywords
                    if not rule.caseSensitive:
                        exclude_kws = [k.lower() for k in exclude_kws]

                    # Check if ANY excluded keyword is present
                    if any(k in desc_check for k in exclude_kws):
                        exclude_match_found = True
                        logger.debug(f"[calculate_finishing_days] Center rule '{rule.id}' skipped: Found excluded keyword.")

                # If no excluded keywords were found (or none defined), the rule passes this check
                if not exclude_match_found:
                    finishing_days += rule.addDays
                    logger.debug(f"[calculate_finishing_days] Center rule '{rule.id}' matched request centerId {req.centerId} and passed exclusion check: {rule.description} ({rule.addDays} days)")
                # --- End Inline Exclusion Check ---
            else:
                 logger.debug(f"[calculate_finishing_days] Center rule '{rule.id}' skipped: Rule centerId ({rule.centerId}) != Request centerId ({req.centerId})")

    else:
        logger.debug("[calculate_finishing_days] No centerId provided in request (or value is None), skipping Center Rules evaluation.")


    # Add any additional production days (no change needed here)
    if req.additionalProductionDays is not None and req.additionalProductionDays > 0:
        finishing_days += req.additionalProductionDays
        logger.debug(f"[calculate_finishing_days] Added {req.additionalProductionDays} additional production days (manual)")

    logger.info(f"[calculate_finishing_days] Total Calculated Finishing Days: {finishing_days}")
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

def add_business_days(start_date: datetime.date, days_to_add: int, closed_dates: list[str]) -> Tuple[datetime.date, datetime.date]:
    """
    Adds business days to a start date, skipping weekends and closed dates.
    Also adjusts the start_date forward if it falls on a non-business day.

    Returns:
        Tuple[datetime.date, datetime.date]: (adjusted_start_date, dispatch_date)
    """
    current_date = start_date
    logger.debug(f"[add_business_days] Initial start date: {start_date}, adding {days_to_add} days. Closed: {closed_dates}")

    # Adjust start_date forward if it's not a business day
    while current_date.weekday() >= 5 or str(current_date) in closed_dates:
        logger.debug(f"[add_business_days] Adjusting start date forward from {current_date} (Weekend or Closed)")
        current_date += timedelta(days=1)

    adjusted_start_date = current_date  # This is the actual first day of production
    logger.debug(f"[add_business_days] Adjusted Start Date: {adjusted_start_date}")

    # Now add the required production days
    days_counted = 0
    dispatch_date = adjusted_start_date # Start counting from the adjusted start date

    # If days_to_add is 0, dispatch is the same as adjusted start date (after validation)
    if days_to_add <= 0:
         logger.debug(f"[add_business_days] Zero or negative days to add. Dispatch date is same as adjusted start date: {adjusted_start_date}")
         return adjusted_start_date, adjusted_start_date


    # Loop to add business days for dispatch calculation
    # Start counting from the day *after* adjusted_start_date
    current_check_date = adjusted_start_date
    while days_counted < days_to_add:
        current_check_date += timedelta(days=1)
        if current_check_date.weekday() >= 5:  # Skip Saturday (5) and Sunday (6)
            # logger.debug(f"[add_business_days] Skipping weekend: {current_check_date}")
            continue
        if str(current_check_date) in closed_dates:
            # logger.debug(f"[add_business_days] Skipping closed date: {current_check_date}")
            continue
        days_counted += 1
        # logger.debug(f"[add_business_days] Counted day {days_counted}: {current_check_date}")


    dispatch_date = current_check_date # The final day is the dispatch date
    logger.debug(f"[add_business_days] Final Dispatch Date: {dispatch_date}")

    return adjusted_start_date, dispatch_date


def find_cmyk_hub_id(chosen_hub: str, cmyk_hubs: list[dict]) -> int:
    """
    Looks up 'chosen_hub' (e.g. 'vic', 'wa', 'qld') in cmyk_hubs
    and returns the corresponding CMHKhubID. If not found, returns 0.
    """
    for entry in cmyk_hubs:
        if entry["Hub"].lower() == chosen_hub.lower():
            return entry["CMHKhubID"]
    return 0  # fallback if no match