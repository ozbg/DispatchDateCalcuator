#main.py
#main.py is the main application file that defines the FastAPI application and the routes.
import logging
from fastapi import FastAPI, Request
from datetime import datetime
from collections import deque
import threading
from fastapi import HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import json
from pathlib import Path
from typing import List
import pytz

from app.data_manager import (
    get_product_info_data, save_product_info_data,
    get_cmyk_hubs_data, save_cmyk_hubs_data,
    get_product_keywords_data, save_product_keywords_data,
    get_hub_data, save_hub_data
)
from app.models import ScheduleRequest, ScheduleResponse
from app.schedule_logic import process_order

# 1) Set up the basic logging configuration
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("scheduler")

# 2) Initialize FastAPI
app = FastAPI(title="Scheduler API", version="1.0.0")

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

# 5) Now add the handler to our logger
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

@app.get("/cmyk-hubs", response_class=HTMLResponse)
async def cmyk_hubs(request: Request):
    try:
        hubs_data = get_cmyk_hubs_data()
        return templates.TemplateResponse(
            "cmyk_hubs.html",
            {"request": request, "hubs": hubs_data}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/save-hubs")
async def save_hubs(request: Request):
    try:
        hubs_data = await request.json()
        save_cmyk_hubs_data(hubs_data)
        return JSONResponse({"success": True, "message": "Hubs saved successfully"})
    except Exception as e:
        return JSONResponse(
            {"success": False, "message": f"Error saving hubs: {str(e)}"},
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

@app.post("/finishing-rules/save")
async def save_rule(request: Request):
    try:
        data = await request.json()
        rules_path = Path("data/finishing_rules.json")
        with open(rules_path, "r") as f:
            rules = json.load(f)

        rule_type = data["type"]
        new_rule = data["rule"]

        if rule_type == "keyword":
            # Update or add keyword rule
            existing_rule = next((r for r in rules["keywordRules"] if r["id"] == new_rule["id"]), None)
            if existing_rule:
                rules["keywordRules"].remove(existing_rule)
            rules["keywordRules"].append(new_rule)
        else:
            # Update or add center rule
            existing_rule = next((r for r in rules["centerRules"] if r["id"] == new_rule["id"]), None)
            if existing_rule:
                rules["centerRules"].remove(existing_rule)
            rules["centerRules"].append(new_rule)

        with open(rules_path, "w", encoding='utf-8') as f:
            json.dump(rules, f, indent=2, ensure_ascii=False)

        return JSONResponse({"success": True, "message": "Rule saved successfully"})
    except Exception as e:
        return JSONResponse(
            {"success": False, "message": f"Error saving rule: {str(e)}"},
            status_code=500
        )

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

@app.post("/schedule", response_model=ScheduleResponse)
def schedule_order(request_data: ScheduleRequest):
    logger.debug(f"Received scheduling request: {request_data}")
    result = process_order(request_data)
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

@app.get("/products", response_class=HTMLResponse)
async def products_html(request: Request):
    logger.debug("Fetching product info and CMYK hubs data.")
    data = get_product_info_data()
    cmyk_hubs = get_cmyk_hubs_data()
    return templates.TemplateResponse("products.html", {
        "request": request,
        "product_data": data,
        "cmyk_hubs": cmyk_hubs
    })

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
            "Production_Hub": product_data.get("Production_Hub", [])
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