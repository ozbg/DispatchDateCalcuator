#data_manager.py is responsible for reading and writing data to and from JSON files.
#This module is used by the main application to read and write data to and from JSON files.
#The data is stored in the 'data/' directory, which is one level up from the 'app/' directory.
import json
from pathlib import Path

# Data directory is one level up from 'app/'
DATA_DIR = Path(__file__).parent.parent / "data"

# ---------- Product Info ----------
def get_product_info_data() -> dict:
    filepath = DATA_DIR / "product_info.json"
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def save_product_info_data(data: dict):
    filepath = DATA_DIR / "product_info.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ---------- cmyk Hubs ----------
def get_cmyk_hubs_data() -> list:
    filepath = DATA_DIR / "cmyk_hubs.json"
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def save_cmyk_hubs_data(data: list):
    filepath = DATA_DIR / "cmyk_hubs.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ---------- Product Keywords ----------
def get_product_keywords_data() -> list:
    filepath = DATA_DIR / "product_keywords.json"
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def save_product_keywords_data(data: list):
    filepath = DATA_DIR / "product_keywords.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ---------- Hub Data / Postcodes ----------
def get_hub_data() -> list:
    filepath = DATA_DIR / "hub_data.json"
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def save_hub_data(data: list):
    filepath = DATA_DIR / "hub_data.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# ---------- Production Groups ----------
def get_production_groups_data() -> list:
    filepath = DATA_DIR / "production_groups.json"
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def save_production_groups_data(data: list):
    filepath = DATA_DIR / "production_groups.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)