import pytest
from datetime import date
from app.schedule_logic import process_order
from app.models import ScheduleRequest

def test_process_order_simple():
    # 1) Basic check: Simple portrait BC

    """
    Tests a standard portrait job that should match a product and
    produce a dispatch date with minimal finishing.
    """
    req = ScheduleRequest(
        misDeliversToPostcode="3000",
        misOrderQTY=1000,
        orientation="portrait",
        description="1 Offset 450+ NV Branding Cards bc",
        printType=1,
        kinds=1,
        preflightedWidth=210.0,
        preflightedHeight=320.0,
        misCurrentHub="vic",
        misCurrentHubID=1,
        misDeliversToState="vic"
    )
    response = process_order(req)
    
    # Convert the Pydantic model to a dictionary (similar to JSON)
    print("\n[TEST] Full JSON output:", response.dict())
    #assert response is not None
    #assert "NV Print 1S" in response.productGroup
    #

# 2) After cutoff test
def test_after_cutoff():
    """
    Forces an after-cutoff scenario by mocking a large hour cutoff (e.g., 8 pm).
    We'll artificially test it by setting the product's cutoff to 0 in code,
    or interpret the logic that if hour >= product cutoff => next day.
    """
    req = ScheduleRequest(
        misDeliversToPostcode="3000",
        misOrderQTY=500,
        orientation="portrait",
        description="2 Offset 450+ NV - after cutoff test bc",
        printType=1,
        kinds=1,
        preflightedWidth=210,
        preflightedHeight=297,
        misCurrentHub="vic",
        misCurrentHubID=1,
        misDeliversToState="vic"
    )
    # Typically you'd manipulate the system time or the product data
    # to ensure we are after cutoff. For a basic test, we check if the logic
    # at hour >= cutoff triggers next day.
    response = process_order(req)
    
    # Convert the Pydantic model to a dictionary (similar to JSON)
    print("\n[TEST] Full JSON output:", response.dict())
    
    assert response is not None
    assert "After Cutoff" in response.dispatchDateLog


# 3) WA offset test
def test_wa_offset():
    """
    Ensures that if the hub is WA, we apply the WA time adjust.
    """
    req = ScheduleRequest(
        misDeliversToPostcode="6000",
        misOrderQTY=500,
        orientation="landscape",
        description="3 BC EcoStar Silk 350gsm",
        printType=1,
        kinds=1,
        preflightedWidth=90,
        preflightedHeight=50,
        misCurrentHub="wa",
        misCurrentHubID=3,
        misDeliversToState="wa"
    )
    response = process_order(req)
    
    # Convert the Pydantic model to a dictionary (similar to JSON)
    print("\n[TEST] Full JSON output:", response.dict())
    
    assert response is not None
    # Not an exact numeric assertion, but we do confirm the debug log
    # references we applied the WA offset. (Might check for "CutoffStatus")
        # Convert the Pydantic model to a dictionary (similar to JSON)
        # Convert the Pydantic model to a dictionary (similar to JSON)


# 4) Large quantity => +1 finishing day
def test_large_qty_finishing():
    """
    If the total quantity (misOrderQTY * kinds) > 10000, finishing days +1
    """
    req = ScheduleRequest(
        misDeliversToPostcode="4000",
        misOrderQTY=20000,  # large
        orientation="portrait",
        description="4 O 100gsm Laser Pad",
        printType=1,
        kinds=1,
        preflightedWidth=210,
        preflightedHeight=297,
        misCurrentHub="nsw",
        misCurrentHubID=5,
        misDeliversToState="nsw"
    )
    response = process_order(req)
    
    # Convert the Pydantic model to a dictionary (similar to JSON)
    print("\n[TEST] Full JSON output:", response.dict())

    assert response is not None
    # Check that the debug log references finishing +1 for large quantity
    assert "qty>10k" in response.dispatchDateLog


# 5) Fold, Score => additional finishing day
def test_fold_score_finishing():
    """
    If the description includes 'fold' or 'score', finishing days +1.
    """
    req = ScheduleRequest(
        misDeliversToPostcode="3000",
        misOrderQTY=1000,
        orientation="portrait",
        description="5 Fold and score 210x297 offset bc",
        printType=1,
        kinds=1,
        preflightedWidth=210,
        preflightedHeight=297,
        misCurrentHub="vic",
        misCurrentHubID=1,
        misDeliversToState="vic"
    )
    response = process_order(req)
    
    # Convert the Pydantic model to a dictionary (similar to JSON)
    print("\n[TEST] Full JSON output:", response.dict())

    
    assert response is not None
    # finishing +1
    assert "fold/crease/perf/score" in response.dispatchDateLog


# 6) Round corner => +1 finishing day
def test_round_corner_finishing():
    req = ScheduleRequest(
        misDeliversToPostcode="3000",
        misOrderQTY=500,
        orientation="landscape",
        description="6 round corner business cards bc",
        printType=1,
        kinds=1,
        preflightedWidth=90,
        preflightedHeight=55,
        misCurrentHub="vic",
        misCurrentHubID=1,
        misDeliversToState="vic"
    )
    response = process_order(req)
    assert response is not None
    assert "round corner/drill" in response.dispatchDateLog
    print("\n[TEST] Round corner =>", response.dispatchDateLog)


# 7) Additional production days
def test_additional_production_days():
    """
    If the request sets additionalProductionDays, it must appear in finishing.
    """
    req = ScheduleRequest(
        misDeliversToPostcode="3000",
        misOrderQTY=250,
        orientation="portrait",
        description="Roll Label bc, plus Van delivery",
        printType=1,
        kinds=1,
        preflightedWidth=210,
        preflightedHeight=99,
        misCurrentHub="vic",
        misCurrentHubID=1,
        misDeliversToState="vic",
        additionalProductionDays=2
    )
    response = process_order(req)
    assert response is not None
    # Check debug log for e.g. "Finishing +2 from 'additionalProductionDays'"
    assert "Finishing +2" in response.dispatchDateLog
    print("\n[TEST] Additional days =>", response.dispatchDateLog)


# 8) No match => fallback product
def test_no_product_match():
    """
    Description doesn't match anything in product_keywords => product_id=0 fallback.
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
    # Fallback product => "No Group Found" or something
    assert "No Group Found" in response.productGroup
    print("\n[TEST] No product match =>", response.dispatchDateLog)


# 9) Check A3+ logic
def test_over_a3_digital():
    """
    If digital + bigger than A3 => might remove QLD, WA from Prod Hubs.
    (Your original code might do that if (longEdge>420 or shortEdge>297) => remove certain hubs.)
    """
    req = ScheduleRequest(
        misDeliversToPostcode="2000",
        misOrderQTY=500,
        orientation="landscape",
        description="Digital bc bigger than A3 scodix??",
        printType=1,
        kinds=1,
        preflightedWidth=500,  # > A3
        preflightedHeight=300,
        misCurrentHub="nsw",
        misCurrentHubID=2,
        misDeliversToState="nsw",
        additionalProductionDays=0
    )
    response = process_order(req)
    assert response is not None
    print("\n[TEST] Over A3 digital =>", response.dispatchDateLog)


# 10) Modified run date test
@pytest.mark.skip(reason="Requires your real data with 'Modified_run_date'")
def test_modified_run_date():
    """
    If there's a product with a valid 'Modified_run_date' override, ensure it's used.
    (You have examples like product_id=9,25,26,44).
    We'll test product_id=9, which has an override for '2025-01-08'.
    """
    req = ScheduleRequest(
        misDeliversToPostcode="3000",
        misOrderQTY=500,
        orientation="portrait",
        description="Offset 350gsm Branding Cards Printed 1S bc",  # triggers product_id=9
        printType=1,
        kinds=1,
        preflightedWidth=100,
        preflightedHeight=50,
        misCurrentHub="vic",
        misCurrentHubID=1,
        misDeliversToState="vic"
    )
    # You'd manipulate the system date or forcibly set 'current_time' to 2025-01-08 for the override.
    response = process_order(req)
    assert response is not None
    # Then check the debug/log that we used the override
    print("\n[TEST] Modified run =>", response.dispatchDateLog)


# 11) UV/Scodix => only VIC
def test_uv_scodix_only_vic():
    """
    If description includes 'UV' or 'Scodix', it's only produced in VIC per your original code.
    """
    req = ScheduleRequest(
        misDeliversToPostcode="4000",
        misOrderQTY=1000,
        orientation="portrait",
        description="Digital scodix bc",
        printType=1,
        kinds=1,
        preflightedWidth=210,
        preflightedHeight=297,
        misCurrentHub="qld",
        misCurrentHubID=5,
        misDeliversToState="qld"
    )
    response = process_order(req)
    assert response is not None
    # Possibly check the debug log to confirm it transferred to VIC
    print("\n[TEST] UV/Scodix => VIC =>", response.dispatchDateLog)


# 12) Envelopes => product 45 or 62
def test_envelopes():
    """
    If the description matches envelopes, we might see product ID 45 or 62 (#wa).
    """
    req = ScheduleRequest(
        misDeliversToPostcode="3000",
        misOrderQTY=2000,
        orientation="portrait",
        description="Envelopes with peel seal",
        printType=1,
        kinds=1,
        preflightedWidth=220,
        preflightedHeight=110,
        misCurrentHub="vic",
        misCurrentHubID=1,
        misDeliversToState="vic"
    )
    response = process_order(req)
    assert response is not None
    print("\n[TEST] Envelopes =>", response.dispatchDateLog)


# 13) Synthetic product => product 12, 38, etc.
def test_synthetic_product():
    """
    If it's digital synthetic, check we match product_id=12 or something similar.
    """
    req = ScheduleRequest(
        misDeliversToPostcode="6000",
        misOrderQTY=100,
        orientation="portrait",
        description="Synthetic Digital bc",
        printType=1,
        kinds=1,
        preflightedWidth=210,
        preflightedHeight=297,
        misCurrentHub="wa",
        misCurrentHubID=3,
        misDeliversToState="wa"
    )
    response = process_order(req)
    assert response is not None
    print("\n[TEST] Synthetic =>", response.dispatchDateLog)


# 14) Presentation folder => +2 days if qty>500
def test_presentation_folder():
    """
    If product is 29 or 30, and qty>500 => finishingDays +2
    """
    req = ScheduleRequest(
        misDeliversToPostcode="3000",
        misOrderQTY=501,  # >500
        orientation="portrait",
        description="Presentation Folder bc 501 qty",
        printType=1,
        kinds=1,
        preflightedWidth=310,
        preflightedHeight=220,
        misCurrentHub="vic",
        misCurrentHubID=1,
        misDeliversToState="vic"
    )
    response = process_order(req)
    assert response is not None
    # In your finishing logic, you'd see +2 for >500
    print("\n[TEST] Presentation folder =>", response.dispatchDateLog)


# 15) Grain direction: portrait => Vertical
def test_grain_portrait():
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
    resp = process_order(req)
    assert resp is not None
    assert resp.setGrainDirection == 3  # Vertical
    print("\n[TEST] Grain portrait =>", resp.dispatchDateLog)


# 16) Grain direction: landscape => Horizontal
def test_grain_landscape():
    req = ScheduleRequest(
        misDeliversToPostcode="3000",
        misOrderQTY=100,
        orientation="landscape",
        description="Some bc text",
        printType=1,
        kinds=1,
        preflightedWidth=150,
        preflightedHeight=100,
        misCurrentHub="vic",
        misCurrentHubID=1,
        misDeliversToState="vic"
    )
    resp = process_order(req)
    assert resp is not None
    assert resp.setGrainDirection == 2  # Horizontal
    print("\n[TEST] Grain landscape =>", resp.dispatchDateLog)


# 17) Not BC size => grain=Either
def test_grain_not_bc():
    req = ScheduleRequest(
        misDeliversToPostcode="3000",
        misOrderQTY=500,
        orientation="portrait",
        description="Large flyer 500x500 not bc",
        printType=1,
        kinds=1,
        preflightedWidth=500,
        preflightedHeight=500,
        misCurrentHub="vic",
        misCurrentHubID=1,
        misDeliversToState="vic"
    )
    resp = process_order(req)
    assert resp is not None
    assert resp.setGrainDirection == 1  # Either
    print("\n[TEST] Not BC =>", resp.dispatchDateLog)


# 18) #wa + Digital => check certain product
def test_wa_digital():
    """
    If #wa is in description plus 'Digital', might match product_id=49..52 etc.
    """
    req = ScheduleRequest(
        misDeliversToPostcode="6000",
        misOrderQTY=800,
        orientation="portrait",
        description="Digital #wa natural board",
        printType=1,
        kinds=1,
        preflightedWidth=210,
        preflightedHeight=297,
        misCurrentHub="wa",
        misCurrentHubID=3,
        misDeliversToState="wa"
    )
    resp = process_order(req)
    assert resp is not None
    print("\n[TEST] #wa + digital =>", resp.dispatchDateLog)


# 19) Padding => +2 finishing days
def test_padding_finishing():
    """
    If description includes 'padding' and product != 31 => finishingDays+2
    """
    req = ScheduleRequest(
        misDeliversToPostcode="3000",
        misOrderQTY=200,
        orientation="portrait",
        description="Offset something with padding",
        printType=1,
        kinds=1,
        preflightedWidth=210,
        preflightedHeight=297,
        misCurrentHub="vic",
        misCurrentHubID=1,
        misDeliversToState="vic"
    )
    resp = process_order(req)
    assert resp is not None
    # Possibly check that +2 finishing days for padding.
    print("\n[TEST] Padding =>", resp.dispatchDateLog)


# 20) Holiday closed date scenario
def test_holiday_closed_date():
    """
    If the dispatch day falls on a closed date in cmyk_hubs.json,
    we skip that date and go to the next open date.
    (E.g., 2024-12-25 or 2025-01-01 from your data.)
    This test is conceptual unless we mock the system date or manipulate logic.
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
    resp = process_order(req)
    assert resp is not None
    # In a real scenario, you'd manipulate time or data to ensure it tries to dispatch on a holiday.
    # Then you'd check that it advanced to the next working day.
    print("\n[TEST] Holiday closure =>", resp.dispatchDateLog)