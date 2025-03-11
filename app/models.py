#models.py contains the Pydantic models that are used to define the structure of the JSON data that is sent to and received from the API.
#These models are used to validate the data and ensure that it conforms to the expected structure.
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Union
from datetime import date

class RuleConditions(BaseModel):
    """Conditions that can be applied to finishing rules"""
    quantityLessThan: Optional[int] = None
    quantityGreaterThan: Optional[int] = None
    quantityGreaterOrEqual: Optional[int] = None
    productIdEqual: Optional[int] = None
    productIdNotEqual: Optional[int] = None
    productIdIn: Optional[List[int]] = None
    productGroupNotContains: Optional[str] = None
    hubOverrides: Optional[Dict[str, int]] = None

class FinishingRule(BaseModel):
    """Individual finishing rule definition"""
    id: str
    description: str
    keywords: Optional[List[str]] = None
    excludeKeywords: Optional[List[str]] = None
    matchType: Optional[str] = "any"  # "any" or "all"
    caseSensitive: bool = False
    addDays: int
    conditions: Optional[RuleConditions] = None
    enabled: bool = True

class CenterRule(BaseModel):
    """Special rules for specific centers"""
    id: str
    description: str
    centerId: int
    excludeKeywords: Optional[List[str]] = None
    matchType: Optional[str] = "any"
    caseSensitive: bool = False
    addDays: int
    enabled: bool = True

class FinishingRules(BaseModel):
    """Container for all finishing rules"""
    keywordRules: List[FinishingRule]
    centerRules: List[CenterRule]

class ScheduleRequest(BaseModel):
    orderId: Optional[str] = None
    misDeliversToPostcode: str = Field(..., description="Delivery postcode", min_length=4, max_length=4)
    misOrderQTY: int = Field(..., description="Order quantity", gt=0)
    orientation: str = Field(..., description="Product orientation")
    description: str = Field(..., description="Product description", min_length=1)
    printType: int = Field(..., description="Print type")
    kinds: int = Field(..., description="Number of kinds", gt=0)
    preflightedWidth: float = Field(..., description="Product width", gt=0)
    preflightedHeight: float = Field(..., description="Product height", gt=0)
    misCurrentHub: str = Field(..., description="Current hub")
    misCurrentHubID: int = Field(..., description="Current hub ID")
    misDeliversToState: str = Field(..., description="Delivery state")
    orderNotes: Optional[str] = Field(None, description="Order notes")
    additionalProductionDays: Optional[int] = Field(0, description="Additional production days", ge=0)
    
    @validator('misDeliversToState')
    def validate_state(cls, v):
        valid_states = ['vic', 'nsw', 'qld', 'wa', 'sa', 'tas', 'act', 'nt', 'nqld']
        if v.lower() not in valid_states:
            raise ValueError(f'Invalid state {v}. Must be one of: {", ".join(valid_states)}')
        return v.lower()
        
    @validator('orientation')
    def validate_orientation(cls, v):
        valid_orientations = ['portrait', 'landscape']
        if v.lower() not in valid_orientations:
            raise ValueError(f'Invalid orientation {v}. Must be one of: {", ".join(valid_orientations)}')
        return v.lower()
        
    @validator('misDeliversToPostcode')
    def validate_postcode(cls, v):
        if not v.isdigit():
            raise ValueError('Postcode must contain only digits')
        return v

class RuleConditions(BaseModel):
    quantityLessThan: Optional[int] = None
    quantityGreaterThan: Optional[int] = None
    quantityGreaterOrEqual: Optional[int] = None
    productIdEqual: Optional[int] = None
    productIdNotEqual: Optional[int] = None
    productIdIn: Optional[List[int]] = None
    productGroupNotContains: Optional[str] = None
    hubOverrides: Optional[Dict[str, int]] = None

class FinishingRule(BaseModel):
    id: str
    description: str
    keywords: Optional[List[str]] = None
    excludeKeywords: Optional[List[str]] = None
    matchType: Optional[str] = "any"  # "any" or "all"
    caseSensitive: bool = False
    addDays: int
    conditions: Optional[RuleConditions] = None
    enabled: bool = True

class CenterRule(BaseModel):
    id: str
    description: str
    centerId: int
    excludeKeywords: Optional[List[str]] = None
    matchType: Optional[str] = "any"
    caseSensitive: bool = False
    addDays: int
    enabled: bool = True

class FinishingRules(BaseModel):
    keywordRules: List[FinishingRule]
    centerRules: List[CenterRule]

class OrderMatchingCriteria(BaseModel):
    """Criteria for matching orders based on quantity, keywords, and product details"""
    maxQuantity: Optional[int] = None
    minQuantity: Optional[int] = None
    keywords: Optional[List[str]] = None
    excludeKeywords: Optional[List[str]] = None
    productIds: Optional[List[int]] = None
    excludeProductIds: Optional[List[int]] = None
    productGroups: Optional[List[str]] = None
    excludeProductGroups: Optional[List[str]] = None

class HubSizeConstraint(BaseModel):
    """Size constraints for hub production capabilities"""
    maxWidth: Optional[float] = None
    maxHeight: Optional[float] = None

class HubEquipmentRule(BaseModel):
    """Equipment/process availability at a hub"""


class HubSelectionRule(BaseModel):
    """Rules for selecting production hubs"""
    id: str
    description: str
    hubId: str
    priority: int = 0
    enabled: bool = True
    timezone: str = "Australia/Melbourne"  # Default timezone if not specified
    sizeConstraints: Optional[HubSizeConstraint] = None
    orderCriteria: Optional[OrderMatchingCriteria] = None
    startDate: Optional[str] = None
    endDate: Optional[str] = None
    
    # Conditions
    keywords: Optional[List[str]] = None
    excludeKeywords: Optional[List[str]] = None
    productIds: Optional[List[int]] = None
    maxQuantity: Optional[int] = None    
    # Size constraints
    sizeConstraints: Optional[HubSizeConstraint] = None
    
    # State/region restrictions
    allowedStates: Optional[List[str]] = None
    excludedStates: Optional[List[str]] = None
    
    # Temporary exclusions
    startDate: Optional[str] = None
    endDate: Optional[str] = None

class ScheduleResponse(BaseModel):
    # Core Product Info
    orderId: Optional[str] = None
    orderDescription: Optional[str] = None
    currentHub: str
    currentHubId: int
    productId: int
    productGroup: str
    productCategory: str
    productionHubs: List[str]
    productionGroups: Optional[List[str]] = None
    preflightedWidth: Optional[float] = None
    preflightedHeight: Optional[float] = None
        
    # Production Details
    cutoffStatus: str
    productStartDays: List[str]
    productCutoff: str
    daysToProduceBase: int
    finishingDays: int
    totalProductionDays: int
    
    # Location Info
    orderPostcode: str
    chosenProductionHub: str
    hubTransferTo: int
    
    # Dates
    startDate: str
    adjustedStartDate: str
    dispatchDate: str
    
    # Processing Info
    grainDirection: str
    orderQuantity: int
    orderKinds: int
    totalQuantity: int
    
    # Configuration
    synergyPreflight: Optional[int] = None
    synergyImpose: Optional[int] = None
    enableAutoHubTransfer: Optional[int] = None
    
    