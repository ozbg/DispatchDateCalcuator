from typing import List, Dict, Optional
from datetime import datetime
from .models import HubSelectionRule, HubSizeConstraint
import json
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def load_hub_rules() -> List[HubSelectionRule]:
    """Load hub selection rules from JSON file"""
    rules_path = Path("data/hub_rules.json")
    if not rules_path.exists():
        return []
    with open(rules_path, "r") as f:
        rules_data = json.load(f)
        return [HubSelectionRule(**rule) for rule in rules_data["rules"]]

def check_size_constraints(width: float, height: float, quantity: int,
                         constraints: HubSizeConstraint) -> bool:
    """Check if dimensions and quantity are within hub constraints"""
    if width > constraints.maxWidth or height > constraints.maxHeight:
        return False
    if constraints.maxQuantity and quantity > constraints.maxQuantity:
        return False
    return True

def check_keywords(description: str, keywords: List[str],
                  exclude_keywords: List[str]) -> bool:
    """Check if description matches keyword rules"""
    description = description.lower()
    
    # Check excluded keywords first
    if exclude_keywords:
        if any(kw.lower() in description for kw in exclude_keywords):
            return False
            
    # Check required keywords
    if keywords:
        if not any(kw.lower() in description for kw in keywords):
            return False
            
    return True

def check_dates(rule: HubSelectionRule) -> bool:
    """Check if rule is valid for current date"""
    if not rule.startDate and not rule.endDate:
        return True
        
    current_date = datetime.now().date()
    
    if rule.startDate:
        start = datetime.strptime(rule.startDate, "%Y-%m-%d").date()
        if current_date < start:
            return False
            
    if rule.endDate:
        end = datetime.strptime(rule.endDate, "%Y-%m-%d").date()
        if current_date > end:
            return False
            
    return True

def get_equipment_data() -> Dict:
    """Load equipment and process data for hubs"""
    rules_path = Path("data/hub_rules.json")
    if not rules_path.exists():
        return {}
    with open(rules_path, "r") as f:
        data = json.load(f)
        return data.get("equipment", {})

def check_equipment_requirements(hub_id: str, required_equipment: List[str],
                              required_processes: List[str]) -> bool:
    """Check if hub has required equipment and processes"""
    equipment_data = get_equipment_data()
    hub_equipment = equipment_data.get(hub_id, {})
    
    if required_equipment:
        available_equipment = hub_equipment.get("equipment", [])
        if not all(eq in available_equipment for eq in required_equipment):
            return False
            
    if required_processes:
        available_processes = hub_equipment.get("processes", [])
        if not all(proc in available_processes for proc in required_processes):
            return False
            
    return True

def choose_production_hub(
    available_hubs: List[str],
    delivers_to_state: str,
    current_hub: str,
    description: str,
    width: float,
    height: float,
    quantity: int,
    product_id: int,
    product_group: str
) -> str:
    """
    Choose the most appropriate production hub based on rules and constraints.
    Starts with available hubs and removes those that don't meet criteria.
    Falls back to current hub or next best if still valid.
    """
    logger.debug(f"Starting hub selection with available hubs: {available_hubs}")
    
    # Create set of valid hubs from available hubs
    valid_hubs = set(available_hubs)
    
    # Load and sort rules by priority (highest first)
    rules = load_hub_rules()
    rules.sort(key=lambda x: x.priority, reverse=True)
    
    # Apply each rule to potentially remove hubs
    for rule in rules:
        if not rule.enabled or not check_dates(rule):
            continue
            
        # Skip rules for hubs not in our valid set
        if rule.hubId not in valid_hubs:
            continue
            
        should_remove = False
        
        # Check size constraints
        if rule.sizeConstraints:
            if not check_size_constraints(width, height, quantity, rule.sizeConstraints):
                should_remove = True
                
        # Check state restrictions
        state_lower = delivers_to_state.lower()
        allowed = [st.lower() for st in rule.allowedStates] if rule.allowedStates else []
        excluded = [st.lower() for st in rule.excludedStates] if rule.excludedStates else []

        if allowed and state_lower not in allowed:
            should_remove = True
        if excluded and state_lower in excluded:
            should_remove = True
            
        if rule.excludedStates and delivers_to_state in rule.excludedStates:
            should_remove = True
            
        # Check product restrictions
        if rule.productIds and product_id not in rule.productIds:
            should_remove = True
            
        if rule.excludeProductIds and product_id in rule.excludeProductIds:
            should_remove = True
            
        if rule.productGroups and not any(pg in product_group for pg in rule.productGroups):
            should_remove = True
            
        if rule.excludeProductGroups and any(pg in product_group for pg in rule.excludeProductGroups):
            should_remove = True
            
        # Check keywords
        if (rule.keywords or rule.excludeKeywords) and not check_keywords(
            description,
            rule.keywords or [],
            rule.excludeKeywords or []
        ):
            should_remove = True
            
        # Check equipment requirements
        if (rule.requiredEquipment or rule.requiredProcesses) and not check_equipment_requirements(
            rule.hubId,
            rule.requiredEquipment or [],
            rule.requiredProcesses or []
        ):
            should_remove = True
            
        # Remove hub if any checks failed
        if should_remove:
            valid_hubs.discard(rule.hubId)
            logger.debug(f"Removed hub {rule.hubId} due to rule: {rule.description}")
    
    logger.debug(f"Remaining valid hubs after applying rules: {valid_hubs}")
    
    # If current hub is still valid, use it
    if current_hub in valid_hubs:
        logger.debug(f"Current hub {current_hub} is valid, keeping it")
        return current_hub
        
    # If we have any valid hubs left, return the first one
    if valid_hubs:
        chosen_hub = list(valid_hubs)[0]
        logger.debug(f"Chose first valid hub: {chosen_hub}")
        return chosen_hub
        
    # If no valid hubs remain, log error and return current hub as fallback
    logger.error(
        f"No valid production hubs found for order: product_id={product_id}, "
        f"state={delivers_to_state}, size={width}x{height}, qty={quantity}"
    )
    return current_hub