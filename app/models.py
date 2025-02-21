#models.py contains the Pydantic models that are used to define the structure of the JSON data that is sent to and received from the API.
#These models are used to validate the data and ensure that it conforms to the expected structure.
from pydantic import BaseModel, Field
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
    misDeliversToPostcode: str
    misOrderQTY: int
    orientation: str
    description: str
    printType: int
    kinds: int
    preflightedWidth: float
    preflightedHeight: float
    misCurrentHub: str
    misCurrentHubID: int
    misDeliversToState: str
    orderNotes: Optional[str] = None
    additionalProductionDays: Optional[int] = 0

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

class HubSizeConstraint(BaseModel):
    """Size constraints for hub production capabilities"""
    maxWidth: Optional[float] = None
    maxHeight: Optional[float] = None
    maxQuantity: Optional[int] = None

class HubEquipmentRule(BaseModel):
    """Equipment/process availability at a hub"""
    hubId: str
    equipment: List[str]
    processes: List[str]
    enabled: bool = True

class HubSelectionRule(BaseModel):
    """Rules for selecting production hubs"""
    id: str
    description: str
    hubId: str
    priority: int = 0
    enabled: bool = True
    
    # Conditions
    keywords: Optional[List[str]] = None
    excludeKeywords: Optional[List[str]] = None
    productIds: Optional[List[int]] = None
    excludeProductIds: Optional[List[int]] = None
    productGroups: Optional[List[str]] = None
    excludeProductGroups: Optional[List[str]] = None
    
    # Size constraints
    sizeConstraints: Optional[HubSizeConstraint] = None
    
    # State/region restrictions
    allowedStates: Optional[List[str]] = None
    excludedStates: Optional[List[str]] = None
    
    # Temporary exclusions
    startDate: Optional[str] = None
    endDate: Optional[str] = None
    
    # Equipment requirements
    requiredEquipment: Optional[List[str]] = None
    requiredProcesses: Optional[List[str]] = None

class ScheduleResponse(BaseModel):
    # Core Product Info
    productId: int
    productGroup: str
    productCategory: str
    productionHubs: List[str]
    
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