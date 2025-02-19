from pydantic import BaseModel
from typing import Optional, List

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