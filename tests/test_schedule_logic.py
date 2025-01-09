import pytest
from app.schedule_logic import process_order
from app.models import ScheduleRequest

def test_process_order_simple():
    req = ScheduleRequest(
        misDeliversToPostcode="3000",
        misOrderQTY=1000,
        orientation="portrait",
        description="Offset 450+ NV Branding Cards bc",
        printType=1,
        kinds=1,
        preflightedWidth=210.0,
        preflightedHeight=320.0,
        misCurrentHub="vic",
        misCurrentHubID=1,
        misDeliversToState="vic"
    )

    response = process_order(req)
    assert response is not None
    assert response.productGroup is not None
    print("Dispatch Date:", response.dispatchDate)
    print("Debug Log:", response.dispatchDateLog)
