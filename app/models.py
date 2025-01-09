from pydantic import BaseModel
from typing import Optional

class ScheduleRequest(BaseModel):
    # Input data structure
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
    # Output data structure
    productGroup: str
    dispatchDate: str
    setGrainDirection: int
    hubTransferTo: int
    dispatchDateLog: str
    setGrainDirectionString: str
    developmentLogging: str
