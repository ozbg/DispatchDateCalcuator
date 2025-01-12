
import pytest
from datetime import date
from app.schedule_logic import process_order
from app.models import ScheduleRequest
from datetime import datetime, timezone
from app.models import ScheduleRequest, ScheduleResponse


def test_process_order_state_override():
        """
        Test state override logic for SA, TAS, ACT, and NQLD.
        """
        req = ScheduleRequest(
            misDeliversToPostcode="5000",
            misOrderQTY=1000,
            orientation="portrait",
            description="Test product",
            printType=1,
            kinds=1,
            preflightedWidth=210.0,
            preflightedHeight=297.0,
            misCurrentHub="vic",
            misCurrentHubID=1,
            misDeliversToState="sa"
        )
        response = process_order(req)
        assert response is not None
        assert response.hubTransferTo == 1  # Assuming VIC hub ID is 1

def test_process_order_postcode_override():
        """
        Test postcode-based hub override.
        """
        req = ScheduleRequest(
            misDeliversToPostcode="2650",
            misOrderQTY=1000,
            orientation="portrait",
            description="150gsm laser",
            printType=1,
            kinds=1,
            preflightedWidth=210.0,
            preflightedHeight=297.0,
            misCurrentHub="nsw",
            misCurrentHubID=2,
            misDeliversToState="nsw"
        )
        response = process_order(req)
        assert response is not None
        assert response.hubTransferTo == 1  # Assuming VIC hub ID is 1

def test_process_order_product_matching():
        """
        Test product matching logic.
        """
        req = ScheduleRequest(
            misDeliversToPostcode="3000",
            misOrderQTY=1000,
            orientation="portrait",
            description="Unknown product",
            printType=1,
            kinds=1,
            preflightedWidth=210.0,
            preflightedHeight=297.0,
            misCurrentHub="vic",
            misCurrentHubID=1,
            misDeliversToState="vic"
        )
        response = process_order(req)
        assert response is not None
        assert response.productGroup == "No Group Found"

def test_process_order_cutoff_check():
        """
        Test cutoff check logic.
        """
        req = ScheduleRequest(
            misDeliversToPostcode="3000",
            misOrderQTY=1000,
            orientation="portrait",
            description="Test product",
            printType=1,
            kinds=1,
            preflightedWidth=210.0,
            preflightedHeight=297.0,
            misCurrentHub="vic",
            misCurrentHubID=1,
            misDeliversToState="vic"
        )
        response = process_order(req)
        assert response is not None
        current_time = datetime.now(timezone.utc)
        cutoff_hour = 12  # Assuming cutoff hour is 12
        if current_time.hour >= cutoff_hour:
            assert "After Cutoff" in response.dispatchDateLog
        else:
            assert "Before Cutoff" in response.dispatchDateLog

def test_process_order_finishing_days():
        """
        Test finishing days calculation.
        """
        req = ScheduleRequest(
            misDeliversToPostcode="3000",
            misOrderQTY=20000,  # Large quantity to trigger additional finishing day
            orientation="portrait",
            description="Test product with fold",
            printType=1,
            kinds=1,
            preflightedWidth=210.0,
            preflightedHeight=297.0,
            misCurrentHub="vic",
            misCurrentHubID=1,
            misDeliversToState="vic"
        )
        response = process_order(req)
        assert response is not None
        assert "qty>10k" in response.dispatchDateLog
        assert "fold/crease/perf/score" in response.dispatchDateLog

def test_process_order_wa_offset():
        """
        Test WA time offset logic.
        """
        req = ScheduleRequest(
            misDeliversToPostcode="6000",
            misOrderQTY=1000,
            orientation="portrait",
            description="Test product",
            printType=1,
            kinds=1,
            preflightedWidth=210.0,
            preflightedHeight=297.0,
            misCurrentHub="wa",
            misCurrentHubID=3,
            misDeliversToState="wa"
        )
        response = process_order(req)
        assert response is not None
        assert "WA time adjust" in response.dispatchDateLog

def test_process_order_no_product_match():
        """
        Test fallback product logic when no product match is found.
        """
        req = ScheduleRequest(
            misDeliversToPostcode="3000",
            misOrderQTY=50,
            orientation="portrait",
            description="some random text no known keywords",
            printType=2,
            kinds=1,
            preflightedWidth=100,
            preflightedHeight=50,
            misCurrentHub="vic",
            misCurrentHubID=1,
            misDeliversToState="vic"
        )
        response = process_order(req)
        assert response is not None
        assert response.productGroup == "No Group Found"

def test_process_order_grain_direction():
        """
        Test grain direction determination logic.
        """
        req = ScheduleRequest(
            misDeliversToPostcode="3000",
            misOrderQTY=100,
            orientation="portrait",
            description="Some bc text",
            printType=1,
            kinds=1,
            preflightedWidth=100,
            preflightedHeight=150,
            misCurrentHub="vic",
            misCurrentHubID=1,
            misDeliversToState="vic"
        )
        response = process_order(req)
        assert response is not None
        assert response.setGrainDirection == 3  # Vertical

def test_process_order_holiday_closed_date():
        """
        Test holiday closed date logic.
        """
        req = ScheduleRequest(
            misDeliversToPostcode="3000",
            misOrderQTY=100,
            orientation="portrait",
            description="Offset bc near holiday date",
            printType=1,
            kinds=1,
            preflightedWidth=210,
            preflightedHeight=297,
            misCurrentHub="vic",
            misCurrentHubID=1,
            misDeliversToState="vic"
        )
        response = process_order(req)
        assert response is not None
        # In a real scenario, you'd manipulate time or data to ensure it tries to dispatch on a holiday.
        # Then you'd check that it advanced to the next working day.
        assert "Holiday closure" in response.dispatchDateLog
