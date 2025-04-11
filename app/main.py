#main.py
#main.py is the main application file that defines the FastAPI application and the routes.
import logging
import uuid
from fastapi import FastAPI, Request, HTTPException
from datetime import datetime
from collections import deque
import threading
from fastapi import HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import json
from pathlib import Path
from typing import List, Optional
import pytz

# >>> NEW IMPORTS FOR AUTH <<<
from fastapi import Depends
from app.auth import get_current_user

from app.data_manager import get_production_groups_data, save_production_groups_data

from app.data_manager import (
    get_product_info_data, save_product_info_data,
    get_cmyk_hubs_data, save_cmyk_hubs_data,
    get_product_keywords_data, save_product_keywords_data,
    get_hub_data, save_hub_data,
    get_imposing_rules_data, save_imposing_rules_data,
    get_preflight_profiles_data, save_preflight_profiles_data,
    get_preflight_rules_data, save_preflight_rules_data
    
)
from app.models import ScheduleRequest, ScheduleResponse
from app.schedule_logic import process_order


## 1) Set up the basic logging configuration using the root logger.
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()  # Use the root logger so all logs propagate

# 2) Initialize FastAPI with a global dependency for security
# Define metadata for API tags (used in docs)
tags_metadata = [
    {
        "name": "Scheduling",
        "description": "Core endpoint for calculating order schedules.",
    },
    {
        "name": "Configuration",
        "description": "Endpoints for viewing and managing configuration data (Products, Hubs, Rules). Requires authentication.",
    },
    {
        "name": "UI",
        "description": "Endpoints serving HTML pages for the web interface. Authentication required.",
        # Removed externalDocs as '#' is not a valid URL and there's no specific external doc link.
    },
    {
        "name": "Internal",
        "description": "Internal utility endpoints.",
    },
]

app = FastAPI(
    title="CMYKhub Dispatch Calculator API",
    version="1.0.1",
    description="API for calculating production schedules based on product type, finishing, hub rules, and cutoffs.",
    dependencies=[Depends(get_current_user)],  # <--- GLOBAL SECURITY
    openapi_tags=tags_metadata
)

# Basic logging setup
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()  # Use the root logger so all logs propagate

# 3) Create thread-safe containers for debug logs
debug_messages = deque(maxlen=1000)
debug_lock = threading.Lock()

# 4) Define the DebugHandler
class DebugHandler(logging.Handler):
    def emit(self, record):
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S'),
            'level': record.levelname,
            'message': record.getMessage()
        }
        with debug_lock:
            debug_messages.append(log_entry)

# 5) Attach the DebugHandler to the root logger
logger.addHandler(DebugHandler())

@app.get("/debug-logs")
async def get_debug_logs():
    """Return the latest debug messages"""
    with debug_lock:
        return list(debug_messages)

# Mount static folder for CSS, images, etc.
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Set up Jinja2 templates folder
templates = Jinja2Templates(directory="app/templates")

@app.get("/api-test", response_class=HTMLResponse)
async def api_test(request: Request):
    return templates.TemplateResponse("api_test.html", {"request": request})

def get_hub_postcodes(hub_name: str) -> str:
    """Get postcodes for a specific hub from hub_data.json"""
    hub_data = get_hub_data()
    for hub in hub_data:
        if hub["hubName"].lower() == hub_name.lower():
            return hub["postcode"]
    return ""

@app.get("/cmyk-hubs", response_class=HTMLResponse)
async def cmyk_hubs(request: Request):
    try:
        hubs_data = get_cmyk_hubs_data()
        hub_data = get_hub_data()  # Load hub data for postcodes
        return templates.TemplateResponse(
            "cmyk_hubs.html",
            {
                "request": request,
                "hubs": hubs_data,
                "hub_data": hub_data,
                "get_hub_postcodes": get_hub_postcodes
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/save-hubs")
async def save_hubs(request: Request):
    try:
        # Get current data
        data = await request.json()
        hubs_data = data.get('hubs', [])
        postcode_data = data.get('postcodes', {})
        
        # Ensure timezone is preserved for each hub
        for hub in hubs_data:
            # Ensure we use the capitalized Timezone key consistently
            if 'timezone' in hub:
                hub['Timezone'] = hub.pop('timezone')
            # Keep existing Timezone if present, otherwise set default
            if 'Timezone' not in hub:
                # Find existing hub to preserve its timezone if possible
                existing_hub = next((h for h in get_cmyk_hubs_data() if h['Hub'] == hub['Hub']), None)
                hub['Timezone'] = existing_hub['Timezone'] if existing_hub and 'Timezone' in existing_hub else 'Australia/Melbourne'
        
        # Ensure closed dates are synced across same hub entries
        hub_closed_dates = {}
        for hub in hubs_data:
            hub_name = hub.get('Hub')
            if hub_name not in hub_closed_dates:
                hub_closed_dates[hub_name] = hub.get('Closed_Dates', [])
        
        # Apply synced closed dates
        for hub in hubs_data:
            hub_name = hub.get('Hub')
            if hub_name in hub_closed_dates:
                hub['Closed_Dates'] = hub_closed_dates[hub_name]
        
        # Save CMYK hubs data
        save_cmyk_hubs_data(hubs_data)
        
        # Get existing hub data
        current_hub_data = get_hub_data()
        
        # Update hub data with new postcodes
        for hub_name, postcode in postcode_data.items():
            # Find existing hub entry or create new one
            hub_entry = next((h for h in current_hub_data if h["hubName"] == hub_name), None)
            if hub_entry:
                hub_entry["postcode"] = postcode
            else:
                # Get hub ID from hubs_data
                hub_info = next((h for h in hubs_data if h["Hub"] == hub_name), None)
                hub_id = hub_info["CMHKhubID"] if hub_info else None
                current_hub_data.append({
                    "hubName": hub_name,
                    "hubId": hub_id,
                    "postcode": postcode
                })
        
        # Save updated hub data
        save_hub_data(current_hub_data)
        
        return JSONResponse({
            "success": True,
            "message": "Hubs and postcodes saved successfully"
        })
    except Exception as e:
        logger.error(f"Error saving hubs and postcodes: {str(e)}")
        return JSONResponse(
            {"success": False, "message": f"Error saving data: {str(e)}"},
            status_code=500
        )

@app.post("/finishing-rules/save")
async def save_finishing_rule(request: Request):
    try:
        data = await request.json()
        logger.debug(f"Received rule data: {data}")
        
        rules_path = Path("data/finishing_rules.json")
        with open(rules_path, "r") as f:
            rules = json.load(f)
            
        rule_type = data.get("type")
        new_rule = data.get("rule")
        
        if not new_rule or not rule_type:
            raise ValueError("Missing rule data or type")
            
        if rule_type == "keyword":
            # Find and update existing rule or add new one
            rule_index = next((i for i, r in enumerate(rules["keywordRules"])
                             if r["id"] == new_rule["id"]), None)
            if rule_index is not None:
                rules["keywordRules"][rule_index] = new_rule
            else:
                rules["keywordRules"].append(new_rule)
        else:
            # Handle center rules
            rule_index = next((i for i, r in enumerate(rules["centerRules"])
                             if r["id"] == new_rule["id"]), None)
            if rule_index is not None:
                rules["centerRules"][rule_index] = new_rule
            else:
                rules["centerRules"].append(new_rule)
        
        # Save updated rules
        with open(rules_path, "w", encoding='utf-8') as f:
            json.dump(rules, f, indent=2, ensure_ascii=False)
            
        return JSONResponse({
            "success": True,
            "message": "Rule saved successfully",
            "rule": new_rule
        })
    except Exception as e:
        logger.error(f"Error saving rule: {str(e)}")
        return JSONResponse(
            {"success": False, "message": f"Error saving rule: {str(e)}"},
            status_code=500
        )

@app.get("/product-keywords", response_class=HTMLResponse)
async def product_keywords(request: Request):
    try:
        keywords_data = get_product_keywords_data()
        product_info = get_product_info_data()
        return templates.TemplateResponse(
            "product_keywords.html",
            {
                "request": request,
                "keywords": keywords_data,
                "product_info": product_info
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/save-keywords")
async def save_keywords(request: Request):
    try:
        keywords_data = await request.json()
        keywords_path = Path("data/product_keywords.json")
        with open(keywords_path, "w") as f:
            json.dump(keywords_data, f, indent=2)
        return JSONResponse({"success": True, "message": "Keywords saved successfully"})
    except Exception as e:
        return JSONResponse(
            {"success": False, "message": f"Error saving keywords: {str(e)}"},
            status_code=500
        )

@app.get("/hub-rules", response_class=HTMLResponse)
async def hub_rules(request: Request):
    try:
        rules_path = Path("data/hub_rules.json")
        if rules_path.exists():
            with open(rules_path, "r") as f:
                data = json.load(f)
                rules = data.get("rules", [])
                equipment = data.get("equipment", {})
        else:
            rules = []
            equipment = {}
        
        # Load hubs data from cmyk_hubs.json
        hubs = get_cmyk_hubs_data()
        
        logger.debug(f"Loaded {len(rules)} rules and equipment data for {len(hubs)} hubs")
        return templates.TemplateResponse(
            "hub_rules.html",
            {
                "request": request,
                "rules": rules,
                "equipment": equipment,
                "hubs": hubs   # Pass hubs data here
            }
        )
    except Exception as e:
        logger.error(f"Error loading hub rules: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/hub-rules/save")
async def save_hub_rule(request: Request):
    try:
        # Parse and validate incoming data
        try:
            rule_data = await request.json()
            logger.debug(f"Received rule data: {rule_data}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON received: {e}")
            return JSONResponse({
                "success": False,
                "message": "Invalid JSON data received"
            }, status_code=400)

        # Validate required fields
        required_fields = ["id", "description", "hubId"]
        missing_fields = [field for field in required_fields if not rule_data.get(field)]
        if missing_fields:
            error_msg = f"Missing required fields: {', '.join(missing_fields)}"
            logger.error(error_msg)
            return JSONResponse({
                "success": False,
                "message": error_msg
            }, status_code=400)

        rules_path = Path("data/hub_rules.json")
        
        # Load existing data
        data = {"rules": [], "equipment": {}}
        if rules_path.exists():
            try:
                with open(rules_path, "r", encoding='utf-8') as f:
                    data = json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in hub_rules.json: {e}")
                return JSONResponse({
                    "success": False,
                    "message": "Error reading rules file"
                }, status_code=500)

        rules = data.get("rules", [])
        
        # Update or add rule
        rule_index = next((i for i, r in enumerate(rules)
                          if r["id"] == rule_data["id"]), None)
                          
        if rule_index is not None:
            logger.info(f"Updating existing rule at index {rule_index}")
            rules[rule_index] = rule_data
        else:
            logger.info(f"Adding new rule with ID: {rule_data['id']}")
            rules.append(rule_data)
            
        # Sort rules by priority
        rules.sort(key=lambda x: x.get("priority", 0), reverse=True)
        
        # Save rules
        try:
            data["rules"] = rules
            with open(rules_path, "w", encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Successfully saved rule with ID: {rule_data['id']}")
            return JSONResponse({
                "success": True,
                "message": "Rule saved successfully",
                "rule": rule_data
            })
        except Exception as e:
            logger.error(f"Failed to save rules file: {e}")
            return JSONResponse({
                "success": False,
                "message": f"Failed to save rules file: {str(e)}"
            }, status_code=500)
            
    except Exception as e:
        logger.error(f"Unexpected error saving hub rule: {str(e)}")
        return JSONResponse({
            "success": False,
            "message": f"Unexpected error: {str(e)}"
        }, status_code=500)
    except ValueError as ve:
        logger.error(f"Validation error saving hub rule: {str(ve)}")
        return JSONResponse(
            {"success": False, "message": str(ve)},
            status_code=400
        )
    except Exception as e:
        logger.error(f"Error saving hub rule: {str(e)}")
        return JSONResponse(
            {"success": False, "message": f"Error saving rule: {str(e)}"},
            status_code=500
        )

@app.post("/hub-rules/delete/{rule_id}")
async def delete_hub_rule(rule_id: str):
    try:
        rules_path = Path("data/hub_rules.json")
        if not rules_path.exists():
            return JSONResponse({
                "success": False,
                "message": "Rules file not found"
            }, status_code=404)
            
        try:
            with open(rules_path, "r", encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in hub_rules.json: {e}")
            return JSONResponse({
                "success": False,
                "message": "Error reading rules file"
            }, status_code=500)
            
        # Check if rule exists
        original_length = len(data.get("rules", []))
        data["rules"] = [r for r in data["rules"] if r["id"] != rule_id]
        
        if len(data["rules"]) == original_length:
            return JSONResponse({
                "success": False,
                "message": f"Rule with ID {rule_id} not found"
            }, status_code=404)
            
        try:
            with open(rules_path, "w", encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Successfully deleted rule with ID: {rule_id}")
            return JSONResponse({
                "success": True,
                "message": "Rule deleted successfully"
            })
        except Exception as e:
            logger.error(f"Failed to save rules file after deletion: {e}")
            return JSONResponse({
                "success": False,
                "message": f"Failed to save rules file: {str(e)}"
            }, status_code=500)
            
    except Exception as e:
        logger.error(f"Error deleting hub rule: {str(e)}")
        return JSONResponse({
            "success": False,
            "message": f"Unexpected error: {str(e)}"
        }, status_code=500)

@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/finishing-rules", response_class=HTMLResponse)
async def finishing_rules(request: Request):
    try:
        rules_path = Path("data/finishing_rules.json")
        with open(rules_path, "r") as f:
            rules = json.load(f)
        return templates.TemplateResponse(
            "finishing_rules.html",
            {"request": request, "rules": rules}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/finishing-rules/delete/{rule_id}")
async def delete_rule(rule_id: str):
    try:
        rules_path = Path("data/finishing_rules.json")
        with open(rules_path, "r") as f:
            rules = json.load(f)

        # Try to remove from keyword rules
        rules["keywordRules"] = [r for r in rules["keywordRules"] if r["id"] != rule_id]
        # Try to remove from center rules
        rules["centerRules"] = [r for r in rules["centerRules"] if r["id"] != rule_id]

        with open(rules_path, "w") as f:
            json.dump(rules, f, indent=2)

        return JSONResponse({"success": True, "message": "Rule deleted successfully"})
    except Exception as e:
        return JSONResponse(
            {"success": False, "message": f"Error deleting rule: {str(e)}"},
            status_code=500
        )

# --- NEW: Imposing Rules ---
@app.get("/imposing-rules", response_class=HTMLResponse, tags=["UI"])
async def imposing_rules_page(request: Request):
    """Serves the HTML page for managing imposing rules."""
    try:
        rules = get_imposing_rules_data() # Get list of rules
        logger.debug(f"Loaded {len(rules)} imposing rules for UI.")
        return templates.TemplateResponse(
            "imposing_rules.html",
            {
                "request": request,
                "rules": rules,
            }
        )
    except Exception as e:
        logger.error(f"Error loading imposing rules page: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error loading page: {e}")

@app.post("/imposing-rules/save", tags=["Configuration"])
async def save_imposing_rules_endpoint(request: Request):
    """Saves the entire list of imposing rules."""
    try:
        # The frontend sends the entire list of potentially modified rules
        rules_list = await request.json()
        if not isinstance(rules_list, list):
             raise ValueError("Invalid data format: Expected a list of rules.")

        # Optional: Add validation for each rule in the list here if needed
        # e.g., using Pydantic models: [ImposingRule(**r) for r in rules_list]

        save_imposing_rules_data(rules_list) # Save the list
        logger.info(f"Saved {len(rules_list)} imposing rules.")
        return JSONResponse({"success": True, "message": "Imposing rules saved successfully"})
    except ValueError as ve:
         logger.error(f"Validation error saving imposing rules: {ve}")
         return JSONResponse({"success": False, "message": str(ve)}, status_code=400)
    except Exception as e:
        logger.error(f"Error saving imposing rules: {str(e)}", exc_info=True)
        return JSONResponse({"success": False, "message": f"Error saving rules: {str(e)}"}, status_code=500)

@app.post("/imposing-rules/delete/{rule_id}", tags=["Configuration"])
async def delete_imposing_rule_endpoint(rule_id: str):
    """Deletes a specific imposing rule by its ID."""
    try:
        current_rules = get_imposing_rules_data() # Get list of rules
        original_length = len(current_rules)

        # Filter out the rule to delete
        updated_rules = [r for r in current_rules if r.get("id") != rule_id]

        if len(updated_rules) == original_length:
            logger.warning(f"Imposing rule ID {rule_id} not found for deletion.")
            raise HTTPException(status_code=404, detail=f"Rule with ID {rule_id} not found.")

        save_imposing_rules_data(updated_rules) # Save the updated list

        logger.info(f"Successfully deleted imposing rule with ID: {rule_id}")
        return JSONResponse({"success": True, "message": "Rule deleted successfully"})
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error deleting imposing rule {rule_id}: {e}", exc_info=True)
        return JSONResponse({"success": False, "message": f"Error deleting rule: {str(e)}"}, status_code=500)

# --- NEW: Preflight Profiles ---
@app.get("/preflight-profiles", response_class=HTMLResponse, tags=["UI", "Configuration"])
async def preflight_profiles_page(request: Request):
    """Serves the HTML page for managing preflight profiles."""
    try:
        profiles = get_preflight_profiles_data()
        logger.debug(f"Loaded {len(profiles)} preflight profiles for UI.")
        return templates.TemplateResponse(
            "preflight_profiles.html",
            {
                "request": request,
                "profiles": profiles,
            }
        )
    except FileNotFoundError as e:
        logger.error(f"Preflight profiles file not found: {e}")
        raise HTTPException(status_code=500, detail="Preflight profiles configuration file not found.")
    except Exception as e:
        logger.exception("Error loading preflight profiles page")
        raise HTTPException(status_code=500, detail=f"Error loading page: {e}")

@app.post("/preflight-profiles/save", tags=["Configuration"])
async def save_preflight_profiles_endpoint(request: Request):
    """Saves the entire list of preflight profiles."""
    try:
        profiles_list = await request.json()
        if not isinstance(profiles_list, list):
             raise ValueError("Invalid data format: Expected a list of profiles.")

        # Basic validation for each profile
        seen_ids = set()
        seen_names = set()
        for profile in profiles_list:
             # Check structure and required fields
             required_keys = ["id", "description", "preflightProfileName"]
             if not isinstance(profile, dict) or not all(key in profile for key in required_keys):
                 raise ValueError(f"Each profile must be a dictionary with 'id', 'description', and 'preflightProfileName'. Invalid profile: {profile}")

             # Validate ID
             if not isinstance(profile["id"], int) or profile["id"] < 0:
                 raise ValueError(f"Profile ID must be a non-negative integer: {profile}")
             if profile["id"] in seen_ids:
                 raise ValueError(f"Duplicate Profile ID found: {profile['id']}")
             seen_ids.add(profile["id"])

             # Validate Description
             if not isinstance(profile["description"], str) or not profile["description"].strip():
                  raise ValueError(f"Profile description cannot be empty: {profile}")

             # Validate Preflight Profile Name
             if not isinstance(profile["preflightProfileName"], str) or not profile["preflightProfileName"].strip():
                  raise ValueError(f"Preflight Profile Name cannot be empty: {profile}")
             # Optional: Add regex check for valid characters if needed (e.g., no spaces)
             # if not re.match(r"^[a-zA-Z0-9_]+$", profile["preflightProfileName"]):
             #     raise ValueError(f"Preflight Profile Name contains invalid characters: {profile}")
             if profile["preflightProfileName"].lower() in seen_names: # Check for case-insensitive uniqueness
                 raise ValueError(f"Duplicate Preflight Profile Name found (case-insensitive): {profile['preflightProfileName']}")
             seen_names.add(profile["preflightProfileName"].lower())


             # Handle reserved ID 0
             if profile["id"] == 0:
                 if profile["description"] != "Do Not Preflight":
                     logger.warning("Forcing description for reserved Profile ID 0 to 'Do Not Preflight'.")
                     profile['description'] = "Do Not Preflight"
                 if profile["preflightProfileName"] != "NoPreflight":
                     logger.warning("Forcing preflightProfileName for reserved Profile ID 0 to 'NoPreflight'.")
                     profile['preflightProfileName'] = "NoPreflight"


        save_preflight_profiles_data(profiles_list)
        logger.info(f"Saved {len(profiles_list)} preflight profiles.")
        # Return the saved list so JS can update if needed (e.g., sorting)
        return JSONResponse({"success": True, "message": "Preflight profiles saved successfully", "profiles": profiles_list})
    except ValueError as ve:
         logger.error(f"Validation error saving preflight profiles: {ve}")
         return JSONResponse({"success": False, "message": str(ve)}, status_code=400)
    except Exception as e:
        logger.exception("Error saving preflight profiles")
        return JSONResponse({"success": False, "message": f"Error saving profiles: {str(e)}"}, status_code=500)

# --- NEW: Preflight Rules ---
@app.get("/preflight-rules", response_class=HTMLResponse, tags=["UI", "Configuration"])
async def preflight_rules_page(request: Request):
    """Serves the HTML page for managing preflight rules."""
    try:
        rules = get_preflight_rules_data() # Get list of rules
        profiles = get_preflight_profiles_data() # Get profiles for dropdown
        logger.debug(f"Loaded {len(rules)} preflight rules and {len(profiles)} profiles for UI.")
        return templates.TemplateResponse(
            "preflight_rules.html",
            {
                "request": request,
                "rules": rules,
                "preflight_profiles": profiles # Pass profiles to template
            }
        )
    except FileNotFoundError as e:
        logger.error(f"Data file not found for /preflight-rules: {e}")
        raise HTTPException(status_code=500, detail=f"Configuration file not found: {e.filename}")
    except Exception as e:
        logger.exception("Error loading preflight rules page")
        raise HTTPException(status_code=500, detail=f"Error loading page: {e}")

@app.post("/preflight-rules/save", tags=["Configuration"])
async def save_preflight_rules_endpoint(request: Request):
    """Saves the entire list of preflight rules."""
    try:
        rules_list = await request.json()
        if not isinstance(rules_list, list):
             raise ValueError("Invalid data format: Expected a list of rules.")

        # Optional: Validate using Pydantic model [PreflightRule(**r) for r in rules_list]
        # Ensure all required fields exist, profile IDs are valid ints etc.

        save_preflight_rules_data(rules_list) # Save the list
        logger.info(f"Saved {len(rules_list)} preflight rules.")
        return JSONResponse({"success": True, "message": "Preflight rules saved successfully"})
    except ValueError as ve:
         logger.error(f"Validation error saving preflight rules: {ve}")
         return JSONResponse({"success": False, "message": str(ve)}, status_code=400)
    except Exception as e:
        logger.exception("Error saving preflight rules")
        return JSONResponse({"success": False, "message": f"Error saving rules: {str(e)}"}, status_code=500)

@app.post("/preflight-rules/delete/{rule_id}", tags=["Configuration"])
async def delete_preflight_rule_endpoint(rule_id: str):
    """Deletes a specific preflight rule by its ID."""
    try:
        current_rules = get_preflight_rules_data() # Get list of rules
        original_length = len(current_rules)

        updated_rules = [r for r in current_rules if r.get("id") != rule_id]

        if len(updated_rules) == original_length:
            logger.warning(f"Preflight rule ID {rule_id} not found for deletion.")
            raise HTTPException(status_code=404, detail=f"Rule with ID {rule_id} not found.")

        save_preflight_rules_data(updated_rules) # Save the updated list

        logger.info(f"Successfully deleted preflight rule with ID: {rule_id}")
        return JSONResponse({"success": True, "message": "Rule deleted successfully"})
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.exception(f"Error deleting preflight rule {rule_id}")
        return JSONResponse({"success": False, "message": f"Error deleting rule: {str(e)}"}, status_code=500)

@app.post("/schedule", response_model=ScheduleResponse)
def schedule_order(request_data: ScheduleRequest, request: Request):
    """Process a scheduling request"""
    try:
        
        # --- TRY ACCESSING HERE ---
        logger.debug(f"Attempting to access centerId directly on request_data object...")
        cid = getattr(request_data, 'centerId', 'ATTRIBUTE_NOT_FOUND') # Use getattr for safety
        logger.info(f"Value of request_data.centerId via getattr: {cid} (Type: {type(cid)})")
        # You could even try a direct access here and let it raise the error if it occurs
        # logger.info(f"Direct access request_data.centerId: {request_data.centerId}")
        # --- END TRY ACCESSING HERE ---
        
        result = process_order(request_data)
        if not result:
            logger.error("Unable to schedule order.")
            raise HTTPException(status_code=400, detail="Unable to schedule order.")
        return result
    except Exception as e:
        logger.error(f"Error processing order: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    if not result:
        logger.error("Unable to schedule order.")
        raise HTTPException(status_code=400, detail="Unable to schedule order.")
    logger.debug(f"Scheduling result: {result}")
    return result

@app.get("/schedule-overrides", response_class=HTMLResponse)
async def schedule_overrides(request: Request):
    try:
        product_info = get_product_info_data()
        return templates.TemplateResponse(
            "schedule_overrides.html",
            {"request": request}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/save-overrides")
async def save_overrides(request: Request):
    try:
        data = await request.json()
        save_product_info_data(data)
        return JSONResponse({"success": True, "message": "Overrides saved successfully"})
    except Exception as e:
        return JSONResponse(
            {"success": False, "message": f"Error saving overrides: {str(e)}"},
            status_code=500
        )

@app.get("/get-products")
async def get_products():
    try:
        return JSONResponse(get_product_info_data())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Product Schedule ---
@app.get("/products", response_class=HTMLResponse, tags=["UI"])
async def products_html(request: Request):
    logger.debug("Fetching product info and CMYK hubs data for /products page.")
    try:
        product_data = get_product_info_data()
        cmyk_hubs = get_cmyk_hubs_data()

        # --- Create Mappings ---
        hub_id_to_name = {hub["CMHKhubID"]: hub["Hub"] for hub in cmyk_hubs}
        # Define print type mapping directly here or load from a config if it changes
        print_type_id_to_name = {
            1: "Offset",
            2: "Digital",
            3: "Offset+Digital",
            4: "Wideformat"
        }
        # ----------------------

        return templates.TemplateResponse("products.html", {
            "request": request,
            "product_data": product_data,
            "cmyk_hubs": cmyk_hubs, # Keep sending this if needed elsewhere in template
            "hub_id_to_name": hub_id_to_name,         # Pass the mapping
            "print_type_id_to_name": print_type_id_to_name # Pass the mapping
        })
    except FileNotFoundError as e:
        logger.error(f"Data file not found for /products: {e}")
        raise HTTPException(status_code=500, detail=f"Configuration file not found: {e.filename}")
    except Exception as e:
        logger.exception("Error loading /products page")
        raise HTTPException(status_code=500, detail="Internal server error loading product data.")

@app.post("/products/edit/{product_id}")
async def update_product(request: Request, product_id: str):
    try:
        # Get JSON data from request
        product_data = await request.json()
        logger.debug(f"Updating product with ID: {product_id} with data: {product_data}")
        
        data = get_product_info_data()
        if product_id not in data:
            logger.error(f"Product with ID {product_id} not found.")
            raise HTTPException(status_code=404, detail="Product not found.")

        # Update the product data
        data[product_id].update({
            "Product_Category": product_data.get("Product_Category"),
            "Product_Group": product_data.get("Product_Group"),
            "Cutoff": product_data.get("Cutoff"),
            "Days_to_produce": product_data.get("Days_to_produce"),
            "Production_Hub": product_data.get("Production_Hub", []),
            "printTypes": product_data.get("printTypes", []),
            "scheduleAppliesTo": product_data.get("scheduleAppliesTo", [])    
        })

        save_product_info_data(data)
        logger.debug(f"Product with ID {product_id} updated successfully.")
        return JSONResponse({
            "success": True,
            "message": "Product updated successfully",
            "data": data[product_id]
        })
    except Exception as e:
        logger.error(f"Error updating product: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/products/add", response_class=HTMLResponse)
async def add_product_html(request: Request):
    logger.debug("Rendering add product form.")
    return templates.TemplateResponse("add_product.html", {"request": request})

@app.post("/products/add")
async def create_new_product(request: Request):
    form_data = await request.form()
    product_id = form_data.get("product_id")
    logger.debug(f"Creating new product with ID: {product_id}")
    
    data = get_product_info_data()
    if product_id in data:
        logger.error(f"Product ID {product_id} already exists.")
        raise HTTPException(status_code=400, detail="Product ID already exists.")

    data[product_id] = {
        "Product_Category": form_data.get("product_category"),
        "Product_Group": form_data.get("product_group"),
        "Product_ID": int(product_id),
        "Production_Hub": ["vic"],
        "Cutoff": form_data.get("cutoff"),
        "SynergyPreflight": 0,
        "SynergyImpose": 0,
        "EnableAutoHubTransfer": 1,
        "OffsetOnly": "",
        "Start_days": ["Monday","Tuesday","Wednesday","Thursday","Friday"],
        "Days_to_produce": form_data.get("days_to_produce"),
        "Modified_run_date": []
    }

    save_product_info_data(data)
    logger.debug(f"New product with ID {product_id} created successfully.")
    return JSONResponse({"success": True, "message": "Product created successfully"})

@app.get("/products/delete/{product_id}")
async def delete_product(product_id: str):
    logger.debug(f"Deleting product with ID: {product_id}")
    data = get_product_info_data()
    if product_id in data:
        del data[product_id]
        save_product_info_data(data)
        logger.debug(f"Product with ID {product_id} deleted successfully.")
        return JSONResponse({"success": True, "message": "Product deleted successfully"})
    else:
        logger.error(f"Product with ID {product_id} not found.")
        raise HTTPException(status_code=404, detail="Product not found.")
    
@app.get("/production-groups", response_class=HTMLResponse)
async def production_groups(request: Request):
    try:
        groups = get_production_groups_data()
        return templates.TemplateResponse(
            "production_groups.html",
            {"request": request, "groups": groups}
        )
    except Exception as e:
        logger.error(f"Error loading production groups: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/save-production-groups")
async def save_production_groups_endpoint(request: Request):
    try:
        groups = await request.json()
        save_production_groups_data(groups)
        logger.debug("Production groups saved successfully.")
        return JSONResponse({"success": True, "message": "Production groups saved successfully"})
    except Exception as e:
        logger.error(f"Error saving production groups: {e}")
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)