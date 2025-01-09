from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.data_manager import (
    get_product_info_data, save_product_info_data,
    get_cmyk_hubs_data, save_cmyk_hubs_data,
    get_product_keywords_data, save_product_keywords_data,
    get_hub_data, save_hub_data
)
from app.models import ScheduleRequest, ScheduleResponse
from app.schedule_logic import process_order

app = FastAPI(title="Scheduler API", version="1.0.0")

# Mount static folder for CSS, images, etc.
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Set up Jinja2 templates folder
templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    """
    Simple homepage that links to the different sections (Products, etc.).
    """
    return templates.TemplateResponse("index.html", {"request": request})


# ---------------------
# Scheduling Endpoint
# ---------------------
@app.post("/schedule", response_model=ScheduleResponse)
def schedule_order(request_data: ScheduleRequest):
    """
    Endpoint for scheduling an order. Accepts JSON of the order details,
    runs the business logic, and returns a ScheduleResponse.
    """
    result = process_order(request_data)
    if not result:
        raise HTTPException(status_code=400, detail="Unable to schedule order.")
    return result


# ---------------------
# Example: Product Info Management (HTML UI)
# ---------------------
@app.get("/products", response_class=HTMLResponse)
def products_html(request: Request):
    """
    Render a page showing the product_info.json data.
    """
    data = get_product_info_data()
    return templates.TemplateResponse("products.html", {"request": request, "product_data": data})


@app.get("/products/edit/{product_id}", response_class=HTMLResponse)
def edit_product_html(request: Request, product_id: str):
    """
    Render a form to edit a specific product by ID.
    """
    data = get_product_info_data()
    if product_id not in data:
        raise HTTPException(status_code=404, detail="Product not found.")
    product = data[product_id]
    return templates.TemplateResponse("edit_product.html", {
        "request": request,
        "product_id": product_id,
        "product": product
    })


@app.post("/products/edit/{product_id}")
def update_product(product_id: str,
                   product_category: str = Form(...),
                   product_group: str = Form(...),
                   cutoff: str = Form(...),
                   days_to_produce: str = Form(...)):
    """
    Handle form submission to update a product.
    """
    data = get_product_info_data()
    if product_id not in data:
        raise HTTPException(status_code=404, detail="Product not found.")

    data[product_id]["Product_Category"] = product_category
    data[product_id]["Product_Group"] = product_group
    data[product_id]["Cutoff"] = cutoff
    data[product_id]["Days_to_produce"] = days_to_produce

    save_product_info_data(data)
    return RedirectResponse(url="/products", status_code=303)


@app.get("/products/add", response_class=HTMLResponse)
def add_product_html(request: Request):
    """
    Render a form to add a new product.
    """
    return templates.TemplateResponse("add_product.html", {"request": request})


@app.post("/products/add")
def create_new_product(product_id: str = Form(...),
                       product_category: str = Form(...),
                       product_group: str = Form(...),
                       cutoff: str = Form(...),
                       days_to_produce: str = Form(...)):
    """
    Handle form submission to add a new product.
    """
    data = get_product_info_data()
    if product_id in data:
        raise HTTPException(status_code=400, detail="Product ID already exists.")

    data[product_id] = {
        "Product_Category": product_category,
        "Product_Group": product_group,
        "Product_ID": int(product_id),
        "Production_Hub": ["vic"],
        "Cutoff": cutoff,
        "SynergyPreflight": 0,
        "SynergyImpose": 0,
        "EnableAutoHubTransfer": 1,
        "OffsetOnly": "",
        "Start_days": ["Monday","Tuesday","Wednesday","Thursday","Friday"],
        "Days_to_produce": days_to_produce,
        "Modified_run_date": []
    }

    save_product_info_data(data)
    return RedirectResponse(url="/products", status_code=303)


@app.get("/products/delete/{product_id}")
def delete_product(product_id: str):
    """
    Deletes a product record from JSON data.
    """
    data = get_product_info_data()
    if product_id in data:
        del data[product_id]
        save_product_info_data(data)
    else:
        raise HTTPException(status_code=404, detail="Product not found.")
    return RedirectResponse(url="/products", status_code=303)
