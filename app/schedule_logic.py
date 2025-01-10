import logging
from datetime import datetime, timedelta
import pytz
from typing import Optional

from app.models import ScheduleRequest, ScheduleResponse
from app.data_manager import (
    get_product_info_data,
    get_product_keywords_data,
    get_cmyk_hubs_data
)
from app.product_matcher import match_product_id, determine_grain_direction
from app.config import TIME_ADJUST, WA_TIME_ADJUST

logger = logging.getLogger("scheduler")
logger.setLevel(logging.DEBUG)

def process_order(req: ScheduleRequest) -> Optional[ScheduleResponse]:
    """
    Main function to schedule an order. Replicates the core logic from your JS code.
    """
    # 1. Identify product
    product_keywords = get_product_keywords_data()
    found_product_id = match_product_id(req.description, product_keywords)
    if found_product_id is None:
        logger.debug("No matching product found. Defaulting product_id=0.")
        found_product_id = 0

    product_info = get_product_info_data()
    product_obj = product_info.get(str(found_product_id), None)

    # 2. Determine grain direction
    grain_str, grain_id = determine_grain_direction(
        orientation=req.orientation,
        width=req.preflightedWidth,
        height=req.preflightedHeight,
        description=req.description
    )

    # 3. Current time with offset
    utc_now = datetime.now(pytz.utc)
    if req.misCurrentHub.lower() == "wa":
        current_time = utc_now + timedelta(hours=WA_TIME_ADJUST)
    else:
        current_time = utc_now + timedelta(hours=TIME_ADJUST)

    # 4. If product not found, create a fallback
    if not product_obj:
        logger.debug(f"Product ID {found_product_id} not in data, using fallback product.")
        product_obj = {
            "Product_Group": "No Group Found",
            "Cutoff": "12",
            "Days_to_produce": "2",
            "Production_Hub": ["vic"]
        }

    product_group = product_obj["Product_Group"]
    cutoff_hour = int(product_obj["Cutoff"])
    base_prod_days = int(product_obj["Days_to_produce"])

    # 5. Check cutoff
    if current_time.hour >= cutoff_hour:
        start_date = (current_time + timedelta(days=1)).date()
        cutoff_status = "After Cutoff"
    else:
        start_date = current_time.date()
        cutoff_status = "Before Cutoff"

    # 6. Finishing days
    finishing_days = calculate_finishing_days(req)
    total_prod_days = base_prod_days + finishing_days

    # 7. Hub state vs. closed dates
    actual_hub_state = req.misDeliversToState.lower() if req.misCurrentHub.lower() != "wa" else "wa"
    closed_dates = get_closed_dates_for_state(actual_hub_state)

    # 8. Calculate dispatch date (business days logic)
    dispatch_date = add_business_days(start_date, total_prod_days, closed_dates)

    # 9. Build debug log
    debug_log = (
        f"CutoffStatus={cutoff_status}, StartDate={start_date}, "
        f"ProdDays={base_prod_days}, FinishingDays={finishing_days}, "
        f"DispatchDate={dispatch_date}"
    )
    logger.debug("SCHEDULE LOG: " + debug_log)

    # 10. Return response
    return ScheduleResponse(
        productGroup=product_group,
        dispatchDate=str(dispatch_date),
        setGrainDirection=grain_id,
        hubTransferTo=1,  # Example
        dispatchDateLog=debug_log,
        setGrainDirectionString=grain_str,
        developmentLogging="Development logs: " + debug_log
    )


def calculate_finishing_days(req: ScheduleRequest) -> int:
    finishing_days = 0
    desc_lower = req.description.lower()
    total_qty = req.misOrderQTY * req.kinds

    if any(k in desc_lower for k in ["fold", "crease", "perf", "score"]):
        finishing_days += 1
        logger.debug("Finishing +1 for fold/crease/perf/score")

    if any(k in desc_lower for k in ["round corner", "dril"]):
        finishing_days += 1
        logger.debug("Finishing +1 for round corner/drill")

    if total_qty > 10000:
        finishing_days += 1
        logger.debug("Finishing +1 for qty>10k")

    finishing_days += req.additionalProductionDays
    if req.additionalProductionDays > 0:
        logger.debug(f"Finishing +{req.additionalProductionDays} from 'additionalProductionDays'")

    return finishing_days

def get_closed_dates_for_state(state: str):
    cmyk_data = get_cmyk_hubs_data()
    for hub_entry in cmyk_data:
        if hub_entry["State"].lower() == state.lower():
            return hub_entry.get("Closed_Dates", [])
    return []

def add_business_days(start_date, days_to_add, closed_dates):
    from datetime import timedelta
    current_date = start_date
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

    return current_date
