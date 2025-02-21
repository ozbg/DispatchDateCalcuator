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
    """
    Check if description matches keyword rules.
    For required keywords: ALL keywords must be present (AND logic)
    For excluded keywords: ANY keyword match excludes (OR logic)
    
    Args:
        description: The order description to check
        keywords: List of required keywords (ALL must match)
        exclude_keywords: List of excluded keywords (ANY matches exclude)
    
    Returns:
        bool: True if description matches keyword rules, False otherwise
    """
    if not description:
        return not keywords  # Empty description only valid if no required keywords
        
    description = description.lower()
    
    # Check excluded keywords first (OR logic - any match excludes)
    if exclude_keywords:
        for kw in exclude_keywords:
            if not kw:  # Skip empty keywords
                continue
            if kw.lower() in description:
                logger.debug(f"Description excluded due to keyword: '{kw}'")
                return False
                
    # Check required keywords (AND logic - all must match)
    if keywords:
        for kw in keywords:
            if not kw:  # Skip empty keywords
                continue
            if kw.lower() not in description:
                logger.debug(f"Description missing required keyword: '{kw}'")
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

def load_hub_rules() -> List[HubSelectionRule]:
    """Load hub selection rules from JSON file"""
    rules_path = Path("data/hub_rules.json")
    if not rules_path.exists():
        return []
    with open(rules_path, "r") as f:
        rules_data = json.load(f)
        return [HubSelectionRule(**rule) for rule in rules_data["rules"]]

def validate_hub_rules(
    initial_hub: str,
    available_hubs: List[str],
    delivers_to_state: str,
    current_hub: str,
    description: str,
    width: float,
    height: float,
    quantity: int,
    product_id: int,
    product_group: str,
    cmyk_hubs: List[dict]
) -> str:
    """
    Validates a chosen hub against hub rules and returns either:
    - The same hub if it passes rules
    - Or the next best hub if the initial one fails rules
    """
    logger.debug(f"Validating hub rules for initial hub: {initial_hub}")
    
    rules = load_hub_rules()
    rules.sort(key=lambda x: x.priority, reverse=True)
    
    # Check if any rules invalidate the initial hub
    for rule in rules:
        if not rule.enabled:
            continue
            
        if rule.hubId.lower() != initial_hub.lower():
            continue
            
        logger.debug(f"Checking rule: {rule.id} - {rule.description}")
        
        # Check size constraints
        if rule.sizeConstraints:
            # Check width constraint if specified
            if (rule.sizeConstraints.maxWidth is not None and
                width > rule.sizeConstraints.maxWidth):
                logger.debug(f"Hub {initial_hub} failed width constraint: {width} > {rule.sizeConstraints.maxWidth}")
                return find_next_best_hub(initial_hub, available_hubs, delivers_to_state, cmyk_hubs)
                
            # Check height constraint if specified
            if (rule.sizeConstraints.maxHeight is not None and
                height > rule.sizeConstraints.maxHeight):
                logger.debug(f"Hub {initial_hub} failed height constraint: {height} > {rule.sizeConstraints.maxHeight}")
                return find_next_best_hub(initial_hub, available_hubs, delivers_to_state, cmyk_hubs)
                
            # Check quantity constraint if specified
            if (rule.sizeConstraints.maxQuantity is not None and
                quantity > rule.sizeConstraints.maxQuantity):
                logger.debug(f"Hub {initial_hub} failed quantity constraint: {quantity} > {rule.sizeConstraints.maxQuantity}")
                return find_next_best_hub(initial_hub, available_hubs, delivers_to_state, cmyk_hubs)
                
        # Check state restrictions
        if rule.allowedStates and delivers_to_state not in [s.lower() for s in rule.allowedStates]:
            logger.debug(f"Hub {initial_hub} state not in allowed states")
            return find_next_best_hub(initial_hub, available_hubs, delivers_to_state, cmyk_hubs)
            
        if rule.excludedStates and delivers_to_state in [s.lower() for s in rule.excludedStates]:
            logger.debug(f"Hub {initial_hub} state in excluded states")
            return find_next_best_hub(initial_hub, available_hubs, delivers_to_state, cmyk_hubs)
            
        # Check product restrictions
        if rule.productIds and product_id not in rule.productIds:
            logger.debug(f"Hub {initial_hub} product ID not allowed")
            return find_next_best_hub(initial_hub, available_hubs, delivers_to_state, cmyk_hubs)
            
        if rule.excludeProductIds and product_id in rule.excludeProductIds:
            logger.debug(f"Hub {initial_hub} product ID explicitly excluded")
            return find_next_best_hub(initial_hub, available_hubs, delivers_to_state, cmyk_hubs)
            
        # Check product groups
        if rule.productGroups and not any(pg.lower() in product_group.lower() for pg in rule.productGroups):
            logger.debug(f"Hub {initial_hub} product group not allowed")
            return find_next_best_hub(initial_hub, available_hubs, delivers_to_state, cmyk_hubs)
            
        if rule.excludeProductGroups and any(pg.lower() in product_group.lower() for pg in rule.excludeProductGroups):
            logger.debug(f"Hub {initial_hub} product group explicitly excluded")
            return find_next_best_hub(initial_hub, available_hubs, delivers_to_state, cmyk_hubs)
            
        # Check keywords
        if rule.keywords and not any(kw.lower() in description.lower() for kw in rule.keywords):
            logger.debug(f"Hub {initial_hub} required keywords not found")
            return find_next_best_hub(initial_hub, available_hubs, delivers_to_state, cmyk_hubs)
            
        if rule.excludeKeywords and any(kw.lower() in description.lower() for kw in rule.excludeKeywords):
            logger.debug(f"Hub {initial_hub} excluded keywords found")
            return find_next_best_hub(initial_hub, available_hubs, delivers_to_state, cmyk_hubs)
            
    # If we get here, the hub passed all rules
    logger.debug(f"Hub {initial_hub} passed all rules")
    return initial_hub

def find_next_best_hub(current_hub: str, available_hubs: List[str], delivers_to_state: str, cmyk_hubs: List[dict]) -> str:
    """Find the next best hub when current hub fails rules"""
    # Find the hub entry for current state
    for hub in cmyk_hubs:
        if hub["State"].lower() == delivers_to_state:
            # Check each next best option
            for next_hub in hub["Next_Best"]:
                if next_hub.lower() in [h.lower() for h in available_hubs]:
                    logger.debug(f"Found next best hub: {next_hub}")
                    return next_hub.lower()
                    
    # Fallback to first available hub if no next best found
    logger.debug(f"No valid next best hub found, using first available: {available_hubs[0]}")
    return available_hubs[0].lower()

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