import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
import pytz


from app.models import ScheduleRequest, ScheduleResponse
from app.data_manager import (
    get_product_info_data,
    get_product_keywords_data,
    get_cmyk_hubs_data,
    get_hub_data
)
from app.product_matcher import match_product_id, determine_grain_direction
from app.config import TIME_ADJUST, WA_TIME_ADJUST

logger = logging.getLogger("scheduler")
logger.setLevel(logging.DEBUG)

def process_order(req: ScheduleRequest) -> Optional[ScheduleResponse]:
    """
    Main function to schedule an order, including:
      1) State overrides for SA/TAS => VIC, ACT => NSW, and NQLD override.
      2) Postcode -> Hub override (if any).
      3) Product matching, finishing days, final production hub selection.
    """

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
        # fallback product
        product_obj = {
            "Product_Group": "No Group Found",
            "Cutoff": "12",
            "Days_to_produce": "2",
            "Production_Hub": ["vic"]
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

    # 6) Calculate finishing days
    finishing_days = calculate_finishing_days(req)
    base_prod_days = int(product_obj["Days_to_produce"])
    total_prod_days = base_prod_days + finishing_days

    # 7) Choose final production hub (like your JS snippet)
    product_hubs = product_obj.get("Production_Hub", [])
    cmyk_hubs = get_cmyk_hubs_data()

    chosen_hub = choose_production_hub(
        product_hubs,
        req.misDeliversToState.lower(),
        req.misCurrentHub.lower(),
        found_product_id,
        cmyk_hubs
    )

    # Find the actual cmykHubID for that chosen hub
    chosen_hub_id = find_cmyk_hub_id(chosen_hub, cmyk_hubs)
    
     # 8) add business days for final dispatch
    closed_dates = get_closed_dates_for_state(chosen_hub, cmyk_hubs)
    adjusted_start_date, dispatch_date = add_business_days(start_date, total_prod_days, closed_dates)

    # Build a debug log
    debug_log = (
        f"CutoffStatus={cutoff_status}, StartDate={start_date}, "
        f"AdjustedStartDate={adjusted_start_date}, "  # Include the adjusted start date in the log
        f"ProdDays={base_prod_days}, FinishingDays={finishing_days}, "
        f"ChosenHub={chosen_hub}, DispatchDate={dispatch_date}"
    )
    logger.debug("SCHEDULE LOG: " + debug_log)

    # Return final
    return ScheduleResponse(
        productGroup=product_obj["Product_Group"],
        dispatchDate=str(dispatch_date),
        setGrainDirection=grain_id,
        hubTransferTo=chosen_hub_id,  # <-- now using the real ID, not hardcoded
        dispatchDateLog=debug_log,
        setGrainDirectionString=grain_str,
        developmentLogging="Development logs: " + debug_log
    )

# --------------------------------------------------------------------
# Postcode-based override (Step 1)
# --------------------------------------------------------------------
def lookup_hub_by_postcode(postcode: str, hub_data: list[dict]) -> Optional[dict]:
    """
    Mirrors your JS logic to check if 'postcode' is in the comma-separated or dash range
    in hub_data. If found, return e.g. {"hubName": "vic", "hubId": 1}, else None.
    """
    for entry in hub_data:
        if is_postcode_in_range(postcode, entry["postcode"]):
            return {"hubName": entry["hubName"], "hubId": entry["hubId"]}
    return None

def is_postcode_in_range(postcode: str, range_string: str) -> bool:
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
def calculate_finishing_days(req: ScheduleRequest) -> int:
    finishing_days = 0
    desc_lower = req.description.lower()
    total_qty = req.misOrderQTY * req.kinds

    # Example: fold, crease, perf => +1
    if any(k in desc_lower for k in ["fold", "crease", "perf", "score"]):
        finishing_days += 1
        logger.debug("Finishing +1 for fold/crease/perf/score")

    # Example: round corner, drill => +1
    if any(k in desc_lower for k in ["round corner", "dril"]):
        finishing_days += 1
        logger.debug("Finishing +1 for round corner/drill")

    # QTY > 10k => +1
    if total_qty > 10000:
        finishing_days += 1
        logger.debug("Finishing +1 for qty>10k")

    # Additional days
    finishing_days += req.additionalProductionDays
    if req.additionalProductionDays > 0:
        logger.debug("Finishing +%d from additionalProductionDays", req.additionalProductionDays)

    return finishing_days

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