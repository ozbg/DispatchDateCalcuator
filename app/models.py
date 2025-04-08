#models.py contains the Pydantic models that are used to define the structure of the JSON data that is sent to and received from the API.
#These models are used to validate the data and ensure that it conforms to the expected structure.
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Union
from datetime import date
import logging # Add logging import

logger = logging.getLogger(__name__) # Get a logger instance
logger.warning(">>>>>>>>>> LOADING models.py containing ScheduleRequest with centerId <<<<<<<<<<") # Use warning level


class RuleConditions(BaseModel):
    """Defines conditions under which a finishing rule applies."""
    quantityLessThan: Optional[int] = Field(None, description="Rule applies if total quantity is less than this value.")
    quantityGreaterThan: Optional[int] = Field(None, description="Rule applies if total quantity is greater than this value.")
    quantityGreaterOrEqual: Optional[int] = Field(None, description="Rule applies if total quantity is greater than or equal to this value.")
    productIdEqual: Optional[int] = Field(None, description="Rule applies if the product ID matches this value.")
    productIdNotEqual: Optional[int] = Field(None, description="Rule applies if the product ID does *not* match this value.")
    productIdIn: Optional[List[int]] = Field(None, description="Rule applies if the product ID is in this list.")
    productGroupNotContains: Optional[str] = Field(None, description="Rule applies if the product group name (case-insensitive) does *not* contain this string.")
    productionHubIs: Optional[List[str]] = Field(None, description="Rule applies if the chosen production hub is in this list (lowercase names).") 
    hubOverrides: Optional[Dict[str, int]] = Field(None, description="Dictionary mapping hub names (lowercase) to specific day adjustments, overriding the rule's default `addDays`.")

class FinishingRule(BaseModel):
    """Represents a rule based on keywords found in the order description to add finishing days."""
    id: str = Field(..., description="Unique identifier for the rule.")
    description: str = Field(..., description="Human-readable description of the rule.")
    keywords: Optional[List[str]] = Field(None, description="List of keywords to search for in the order description.")
    excludeKeywords: Optional[List[str]] = Field(None, description="List of keywords that, if found, prevent the rule from matching.")
    matchType: Optional[str] = Field("any", description="How keywords should match: 'any' (at least one) or 'all'.")
    caseSensitive: bool = Field(False, description="Whether keyword matching should be case-sensitive.")
    addDays: int = Field(..., description="Number of finishing days to add if the rule matches.")
    conditions: Optional[RuleConditions] = Field(None, description="Optional conditions that must also be met for the rule to apply.")
    enabled: bool = Field(True, description="Whether the rule is currently active.")

class CenterRule(BaseModel):
    """Represents a special finishing rule applicable only to a specific dispatch center/hub ID."""
    id: str = Field(..., description="Unique identifier for the rule.")
    description: str = Field(..., description="Human-readable description of the rule.")
    centerId: int = Field(..., description="The specific hub/center ID this rule applies to.")
    excludeKeywords: Optional[List[str]] = Field(None, description="List of keywords that, if found in the order description, prevent the rule from matching.")
    matchType: Optional[str] = Field("any", description="Keyword exclusion type: 'any' (if any excluded keyword is found) or 'all'.") # Note: Original logic implies 'any' for exclusion
    caseSensitive: bool = Field(False, description="Whether keyword matching should be case-sensitive.")
    addDays: int = Field(..., description="Number of finishing days to add if the rule matches (can be negative).")
    enabled: bool = Field(True, description="Whether the rule is currently active.")

class FinishingRules(BaseModel):
    """Container model holding lists of all keyword-based and center-based finishing rules."""
    keywordRules: List[FinishingRule] = Field(..., description="List of general keyword-based finishing rules.")
    centerRules: List[CenterRule] = Field(..., description="List of finishing rules specific to certain center IDs.")

class OrderNote(BaseModel):
    """Represents a note associated with an order, typically from the MIS."""
    noteText: str = Field(..., description="The content of the note.")
    dateCreated: str = Field(..., description="Timestamp when the note was created (ISO format string).")
    userID: int = Field(..., description="ID of the user who created the note.")
    userName: str = Field(..., description="Name of the user who created the note.")
    type: str = Field(..., description="Type or category of the note (e.g., 'Hub', 'Centre').")

class ScheduleRequest(BaseModel):
    """Input model for the /schedule endpoint, containing all necessary order details."""
    orderId: Optional[str] = Field(None, description="Optional unique identifier for the order.")
    misDeliversToPostcode: str = Field(..., description="Delivery postcode for the order.", example="3000")
    misOrderQTY: int = Field(..., description="Quantity of the item ordered.", example=1000)
    orientation: str = Field(..., description="Orientation determined by preflight ('portrait' or 'landscape').", example="portrait")
    description: str = Field(..., description="Full product description, used for keyword matching.", example="Offset 150gsm Gloss Flyer")
    printType: int = Field(..., description="Type of printing process (1: Offset, 2: Digital, 3: Offset+Digital, 4: Wideformat).", example=1)
    kinds: int = Field(..., description="Number of kinds or versions for the order item.", example=1)
    preflightedWidth: float = Field(..., description="Width of the product in mm after preflight.", example=210.0)
    preflightedHeight: float = Field(..., description="Height of the product in mm after preflight.", example=297.0)
    misCurrentHub: str = Field(..., description="The hub where the order currently resides in the MIS (lowercase).", example="vic")
    misCurrentHubID: Optional[int] = Field(None, description="The ID of the hub where the order currently resides.", example=1)
    misDeliversToState: str = Field(..., description="The state the order delivers to (lowercase, used for hub selection).", example="vic")
    orderNotes: Optional[List[OrderNote]] = Field(None, description="Optional list of notes associated with the order.")
    centerId: Optional[int] = Field(None, description="Optional specific Center ID for evaluating Center Rules in finishing_rules.json.")
    additionalProductionDays: Optional[int] = Field(0, description="Manually specified additional days to add to production time.", example=0)
    timeOffsetHours: Optional[int] = Field(0, description="Simulate running the request N hours forward (+) or backward (-) from the actual processing time.", example=0)

class OrderMatchingCriteria(BaseModel):
    """Defines criteria used in HubSelectionRules and ImposingRules to match specific orders."""
    maxQuantity: Optional[int] = Field(None, description="Rule applies if order quantity is less than or equal to this value.")
    minQuantity: Optional[int] = Field(None, description="Rule applies if order quantity is greater than or equal to this value.")
    keywords: Optional[List[str]] = Field(None, description="Rule applies if any of these keywords are found in the order description (case-insensitive).")
    excludeKeywords: Optional[List[str]] = Field(None, description="Rule applies if *none* of these keywords are found in the order description (case-insensitive).")
    productIds: Optional[List[int]] = Field(None, description="Rule applies if the order's product ID is in this list.")
    excludeProductIds: Optional[List[int]] = Field(None, description="Rule *fails* if the order's product ID is in this list.") # <<< ADDED THIS LINE
    productGroups: Optional[List[str]] = Field(None, description="Rule applies if the order's product group is in this list (case-insensitive).")
    excludeProductGroups: Optional[List[str]] = Field(None, description="Rule applies if the order's product group is *not* in this list (case-insensitive).")
    printTypes: Optional[List[int]] = Field(None, description="Rule applies if the order's printType is in this list.")

class ImposingRule(BaseModel):
    """Defines a rule used to determine the SynergyImpose action."""
    id: str = Field(..., description="Unique identifier for the imposing rule.")
    description: str = Field(..., description="Human-readable description of the rule's purpose.")
    priority: int = Field(0, description="Execution priority (higher numbers run first). The first matching rule determines the action.")
    enabled: bool = Field(True, description="Whether this rule is currently active.")
    orderCriteria: Optional[OrderMatchingCriteria] = Field(None, description="If defined, the order must match *all* criteria for the rule to apply.")
    imposingAction: int = Field(..., description="The action to take if the rule matches (0: No Impose, 1: Auto Impose, 2: Manual Impose).")
    startDate: Optional[str] = Field(None, description="Date (YYYY-MM-DD) from which the rule becomes active.")
    endDate: Optional[str] = Field(None, description="Date (YYYY-MM-DD) after which the rule is no longer active.")

class PreflightProfile(BaseModel):
    """Represents a preflight profile definition."""
    id: int = Field(..., description="Unique numeric identifier for the profile.")
    description: str = Field(..., description="Human-readable description of the profile.")

# --- PREFLIGHT RULE ---
class PreflightRule(BaseModel):
    """Defines a rule used to determine the SynergyPreflight profile ID."""
    id: str = Field(..., description="Unique identifier for the preflight rule.")
    description: str = Field(..., description="Human-readable description of the rule's purpose.")
    priority: int = Field(0, description="Execution priority (higher numbers run first). The first matching rule determines the action.")
    enabled: bool = Field(True, description="Whether this rule is currently active.")
    orderCriteria: Optional[OrderMatchingCriteria] = Field(None, description="If defined, the order must match *all* criteria for the rule to apply.")
    preflightProfileId: int = Field(..., description="The ID of the Preflight Profile to apply if the rule matches.")
    startDate: Optional[str] = Field(None, description="Date (YYYY-MM-DD) from which the rule becomes active.")
    endDate: Optional[str] = Field(None, description="Date (YYYY-MM-DD) after which the rule is no longer active.")

class HubSizeConstraint(BaseModel):
    """Defines maximum dimensions (width/height) constraints for a hub selection rule."""
    maxWidth: Optional[float] = Field(None, description="Maximum allowable width (mm) for the product (considers orientation).")
    maxHeight: Optional[float] = Field(None, description="Maximum allowable height (mm) for the product (considers orientation).")

class HubEquipmentRule(BaseModel):
    """Placeholder for future rules based on required equipment or processes at a hub."""
    # Example: required_equipment: Optional[List[str]] = None
    # Example: required_processes: Optional[List[str]] = None
    pass

class HubSelectionRule(BaseModel):
    """Defines a rule used to potentially override the default production hub choice."""
    id: str = Field(..., description="Unique identifier for the hub selection rule.")
    description: str = Field(..., description="Human-readable description of the rule's purpose.")
    hubId: str = Field(..., description="The hub (lowercase name) that this rule applies *to*. If criteria match, this hub might be excluded.", example="nqld")
    priority: int = Field(0, description="Execution priority (higher numbers run first). Rules can redirect hub choice.")
    enabled: bool = Field(True, description="Whether this rule is currently active.")
    timezone: str = Field("Australia/Melbourne", description="Timezone associated with the hub (used for cutoff calculations - *currently not used directly in rule logic*).") # Note: Timezone is primarily from cmyk_hubs.json
    sizeConstraints: Optional[HubSizeConstraint] = Field(None, description="If specified, the rule applies if the product size *exceeds* these constraints, potentially excluding the hub.")
    orderCriteria: Optional[OrderMatchingCriteria] = Field(None, description="If specified, the rule applies if the order matches *all* defined criteria, potentially excluding the hub.")
    startDate: Optional[str] = Field(None, description="Date (YYYY-MM-DD) from which the rule becomes active.")
    endDate: Optional[str] = Field(None, description="Date (YYYY-MM-DD) after which the rule is no longer active.")

    # Redundant fields also present in OrderMatchingCriteria - kept for potential direct use if needed, but prefer nested structure.
    keywords: Optional[List[str]] = Field(None, description="[Legacy/Redundant] Use orderCriteria.keywords instead.")
    excludeKeywords: Optional[List[str]] = Field(None, description="[Legacy/Redundant] Use orderCriteria.excludeKeywords instead.")
    productIds: Optional[List[int]] = Field(None, description="[Legacy/Redundant] Use orderCriteria.productIds instead.")
    maxQuantity: Optional[int] = Field(None, description="[Legacy/Redundant] Use orderCriteria.maxQuantity instead.")

    # State/region restrictions - Not currently implemented in logic but defined in model
    allowedStates: Optional[List[str]] = Field(None, description="[Not Implemented] If specified, rule only applies if delivery state is in this list.")
    excludedStates: Optional[List[str]] = Field(None, description="[Not Implemented] If specified, rule only applies if delivery state is *not* in this list.")

class ScheduleResponse(BaseModel):
    """Output model for the /schedule endpoint, detailing the calculated schedule."""
    # Core Product Info
    orderId: Optional[str] = Field(None, description="Unique identifier for the order, passed from the request.")
    orderDescription: Optional[str] = Field(None, description="The full description of the order item used for matching.")
    currentHub: str = Field(..., description="The resolved hub where the order originated (lowercase name).")
    currentHubId: int = Field(..., description="The resolved ID of the hub where the order originated.")
    productId: int = Field(..., description="The matched product ID based on the description.")
    productGroup: str = Field(..., description="The group associated with the matched product ID.")
    productCategory: str = Field(..., description="The category associated with the matched product ID.")
    productionHubs: List[str] = Field(..., description="List of potential production hubs defined for the matched product.")
    productionGroups: Optional[List[str]] = Field(None, description="List of production group names matched based on the order description.")
    preflightedWidth: Optional[float] = Field(None, description="Width of the product in mm (passed from request).")
    preflightedHeight: Optional[float] = Field(None, description="Height of the product in mm (passed from request).")

    # Production Details
    cutoffStatus: str = Field(..., description="Indicates if the order was received 'Before Cutoff' or 'After Cutoff' based on the hub's time.")
    productStartDays: List[str] = Field(..., description="List of weekdays the matched product can start production.")
    productCutoff: str = Field(..., description="Cutoff hour (as a string) for the matched product.")
    daysToProduceBase: int = Field(..., description="Base number of production days for the matched product.")
    finishingDays: int = Field(..., description="Calculated number of additional days required for finishing processes based on rules.")
    totalProductionDays: int = Field(..., description="Total production days (base + finishing).")

    # Location Info
    orderPostcode: str = Field(..., description="Delivery postcode for the order.")
    chosenProductionHub: str = Field(..., description="The final selected production hub (lowercase name) after applying overrides and rules.")
    hubTransferTo: int = Field(..., description="The CMYK Hub ID of the `chosenProductionHub`.")

    # Dates
    startDate: str = Field(..., description="The initial calculated start date (YYYY-MM-DD) based on cutoff time (may be a weekend/holiday).")
    adjustedStartDate: str = Field(..., description="The actual start date (YYYY-MM-DD) after adjusting for weekends and closed dates.")
    dispatchDate: str = Field(..., description="The calculated final dispatch date (YYYY-MM-DD) from the `adjustedStartDate` plus `totalProductionDays`, skipping weekends/closed dates.")

    # Processing Info
    grainDirection: str = Field(..., description="Calculated grain direction ('Vertical', 'Horizontal', or 'Either').")
    orderQuantity: int = Field(..., description="Quantity per kind (passed from request).")
    orderKinds: int = Field(..., description="Number of kinds (passed from request).")
    totalQuantity: int = Field(..., description="Total quantity (orderQuantity * orderKinds).")

    # Configuration - Reflecting product settings
    synergyPreflight: Optional[int] = Field(None, description="Synergy preflight setting from the matched product.")
    synergyImpose: Optional[int] = Field(None, description="Synergy impose setting from the matched product.")
    enableAutoHubTransfer: Optional[int] = Field(None, description="Indicates if automatic hub transfer should be enabled (1 if chosen hub differs from current hub, 0 otherwise).")
   
    # Time Info <<< ADDED BLOCK
    actualProcessingTime: str = Field(..., description="Actual server time (incl. timezone) when the request was processed.")
    simulatedProcessingTime: Optional[str] = Field(None, description="Simulated time (incl. timezone) used for calculation if timeOffsetHours was non-zero.")