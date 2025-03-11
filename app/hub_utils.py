import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

def resolve_hub_details(current_hub: Optional[str] = None, current_hub_id: Optional[int] = None, cmyk_hubs: list = None) -> Tuple[str, int]:
    """
    Resolves hub name and ID based on provided inputs.
    Priority:
    1. If both present, validate and use ID's values
    2. If only hub name, lookup ID
    3. If only ID, lookup name
    4. If neither, default to VIC
    
    Returns tuple of (hub_name, hub_id)
    """
    DEFAULT_HUB = "vic"
    DEFAULT_HUB_ID = 1
    
    if not cmyk_hubs:
        logger.warning("No CMYK hubs data provided for resolution")
        return DEFAULT_HUB, DEFAULT_HUB_ID
        
    # Case 1: Both provided - validate and use ID's values
    if current_hub_id is not None and current_hub is not None:
        found_hub = next((h for h in cmyk_hubs if h["CMHKhubID"] == current_hub_id), None)
        if found_hub:
            if found_hub["Hub"].lower() != current_hub.lower():
                logger.warning(f"Hub name mismatch: Provided '{current_hub}' doesn't match ID {current_hub_id} ('{found_hub['Hub']}'). Using ID's value.")
            return found_hub["Hub"].lower(), current_hub_id
            
    # Case 2: Only hub name provided
    if current_hub is not None and current_hub_id is None:
        found_hub = next((h for h in cmyk_hubs if h["Hub"].lower() == current_hub.lower()), None)
        if found_hub:
            return found_hub["Hub"].lower(), found_hub["CMHKhubID"]
            
    # Case 3: Only ID provided
    if current_hub_id is not None and current_hub is None:
        found_hub = next((h for h in cmyk_hubs if h["CMHKhubID"] == current_hub_id), None)
        if found_hub:
            return found_hub["Hub"].lower(), current_hub_id
            
    # Case 4: Neither provided or no matches found
    logger.warning(f"Unable to resolve hub details (hub='{current_hub}', id={current_hub_id}). Using defaults.")
    return DEFAULT_HUB, DEFAULT_HUB_ID

def get_hub_name(hub_id: int, cmyk_hubs: list) -> str:
    """Get hub name from ID. Returns lowercase hub name or 'vic' if not found."""
    found_hub = next((h for h in cmyk_hubs if h["CMHKhubID"] == hub_id), None)
    return found_hub["Hub"].lower() if found_hub else "vic"

def get_hub_id(hub_name: str, cmyk_hubs: list) -> int:
    """Get hub ID from name. Returns ID or 1 (VIC) if not found."""
    found_hub = next((h for h in cmyk_hubs if h["Hub"].lower() == hub_name.lower()), None)
    return found_hub["CMHKhubID"] if found_hub else 1