from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Union

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