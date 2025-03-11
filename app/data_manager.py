import json
from pathlib import Path
import logging
from typing import Dict, List, Any, Optional

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Data directory is one level up from 'app/'
DATA_DIR = Path(__file__).parent.parent / "data"

def validate_json_structure(data: Any, required_fields: List[str], context: str) -> None:
    """Validate that all required fields exist in the data structure"""
    if isinstance(data, dict):
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            raise ValueError(f"Missing required fields in {context}: {', '.join(missing_fields)}")
    elif isinstance(data, list) and data:  # If it's a list and not empty, check first item
        if isinstance(data[0], dict):  # If list contains dictionaries
            missing_fields = [field for field in required_fields if field not in data[0]]
            if missing_fields:
                raise ValueError(f"Missing required fields in {context} items: {', '.join(missing_fields)}")

def load_json_file(filepath: Path, context: str) -> Any:
    """Generic JSON file loader with error handling"""
    logger.debug(f"Attempting to load {context} from {filepath}")
    
    if not filepath.exists():
        error_msg = f"{context} file not found at {filepath}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)
        
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.debug(f"Successfully loaded {context} data")
            return data
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON in {context} file: {str(e)}"
        logger.error(error_msg)
        raise json.JSONDecodeError(f"{error_msg}. Line: {e.lineno}, Column: {e.colno}", e.doc, e.pos)
    except Exception as e:
        error_msg = f"Error reading {context} file: {str(e)}"
        logger.error(error_msg)
        raise

def save_json_file(filepath: Path, data: Any, context: str) -> None:
    """Generic JSON file saver with error handling"""
    logger.debug(f"Attempting to save {context} to {filepath}")
    
    try:
        # Ensure the directory exists
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            logger.debug(f"Successfully saved {context} data")
    except Exception as e:
        error_msg = f"Error saving {context} file: {str(e)}"
        logger.error(error_msg)
        raise

# ---------- Product Info ----------
def get_product_info_data() -> Dict:
    required_fields = ["Product_ID", "Product_Group", "Product_Category", "Cutoff",
                      "Days_to_produce", "Production_Hub", "Start_days"]
    
    data = load_json_file(DATA_DIR / "product_info.json", "product info")
    
    try:
        # Validate each product entry
        for product_id, product_data in data.items():
            validate_json_structure(product_data, required_fields, f"product {product_id}")
        return data
    except Exception as e:
        logger.error(f"Invalid product info data structure: {str(e)}")
        raise

def save_product_info_data(data: Dict):
    save_json_file(DATA_DIR / "product_info.json", data, "product info")

# ---------- CMYK Hubs ----------
def get_cmyk_hubs_data() -> List[Dict]:
    required_fields = ["Hub", "CMHKhubID", "State", "Next_Best", "Timezone"]
    
    data = load_json_file(DATA_DIR / "cmyk_hubs.json", "CMYK hubs")
    
    try:
        validate_json_structure(data, required_fields, "CMYK hubs")
        
        # Additional validation for hub-specific fields
        for hub in data:
            if not isinstance(hub["Next_Best"], list):
                raise ValueError(f"'Next_Best' must be a list for hub {hub.get('Hub', 'UNKNOWN')}")
            if not isinstance(hub["Timezone"], str):
                raise ValueError(f"'Timezone' must be a string for hub {hub.get('Hub', 'UNKNOWN')}")
            
        return data
    except Exception as e:
        logger.error(f"Invalid CMYK hubs data structure: {str(e)}")
        raise

def save_cmyk_hubs_data(data: List[Dict]):
    save_json_file(DATA_DIR / "cmyk_hubs.json", data, "CMYK hubs")

# ---------- Product Keywords ----------
def get_product_keywords_data() -> List[Dict]:
    required_fields = ["Product_ID", "Match_All", "Match_Any", "Exclude_All"]
    
    data = load_json_file(DATA_DIR / "product_keywords.json", "product keywords")
    
    try:
        validate_json_structure(data, required_fields, "product keywords")
        
        # Validate that arrays are actually arrays
        for keyword_set in data:
            for field in ["Match_All", "Match_Any", "Exclude_All"]:
                if not isinstance(keyword_set.get(field, []), list):
                    raise ValueError(f"'{field}' must be an array in product keywords for Product_ID {keyword_set.get('Product_ID', 'UNKNOWN')}")
        
        return data
    except Exception as e:
        logger.error(f"Invalid product keywords data structure: {str(e)}")
        raise

def save_product_keywords_data(data: List[Dict]):
    save_json_file(DATA_DIR / "product_keywords.json", data, "product keywords")

# ---------- Hub Data / Postcodes ----------
def get_hub_data() -> List[Dict]:
    required_fields = ["hubName", "hubId", "postcode"]
    
    data = load_json_file(DATA_DIR / "hub_data.json", "hub data")
    
    try:
        validate_json_structure(data, required_fields, "hub data")
        
        # Validate postcode format
        for hub in data:
            if not isinstance(hub["postcode"], str):
                raise ValueError(f"Postcode must be a string for hub {hub.get('hubName', 'UNKNOWN')}")
            
        return data
    except Exception as e:
        logger.error(f"Invalid hub data structure: {str(e)}")
        raise

def save_hub_data(data: List[Dict]):
    save_json_file(DATA_DIR / "hub_data.json", data, "hub data")

# ---------- Production Groups ----------
def get_production_groups_data() -> List[Dict]:
    required_fields = ["id", "name", "Match_All", "Match_Any", "Exclude_All"]
    
    data = load_json_file(DATA_DIR / "production_groups.json", "production groups")
    
    try:
        validate_json_structure(data, required_fields, "production groups")
        
        # Validate arrays and required fields
        for group in data:
            for field in ["Match_All", "Match_Any", "Exclude_All"]:
                if not isinstance(group.get(field, []), list):
                    raise ValueError(f"'{field}' must be an array in production group {group.get('name', 'UNKNOWN')}")
            
        return data
    except Exception as e:
        logger.error(f"Invalid production groups data structure: {str(e)}")
        raise

def save_production_groups_data(data: List[Dict]):
    save_json_file(DATA_DIR / "production_groups.json", data, "production groups")