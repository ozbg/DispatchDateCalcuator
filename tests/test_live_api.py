# tests/test_live_api.py
# Open a new terminal, run up the server:  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# Run the test: pytest tests/test_live_api.py




import pytest
import requests

def test_schedule_live():
    payload = {
       "misDeliversToPostcode":"2650",
       "misOrderQTY":50,
       "orientation":"landscape",
       "description":"100gsm Laser dril ",
       "printType":1,
       "kinds":1,
       "preflightedWidth":190,
       "preflightedHeight":255,
       "misCurrentHub":"nsw",
       "misCurrentHubID":2,
       "misDeliversToState":"nsw"
     }
    url = "http://127.0.0.1:8000/schedule"
    response = requests.post(url, json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "productGroup" in data
    print("[TEST] Full live response:", data)
    
    