from fastapi import FastAPI, Request
from fastapi import FastAPI, Request
from fastapi import HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import json
import json
from pathlib import Path
from typing import List
import json
import pytz
import logging

from app.data_manager import (
    get_product_info_data, save_product_info_data,
    get_cmyk_hubs_data, save_cmyk_hubs_data,
    get_product_keywords_data, save_product_keywords_data,
    get_hub_data, save_hub_data
)
from app.models import ScheduleRequest, ScheduleResponse
from app.schedule_logic import process_order

app = FastAPI(title="Scheduler API", version="1.0.0")

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("scheduler")

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

@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

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