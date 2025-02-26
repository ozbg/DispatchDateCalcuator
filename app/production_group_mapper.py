import logging
from app.product_matcher import match_all, exclude_all, match_any  # reuse your helper functions

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def match_production_groups(description: str, groups: list) -> list:
    """Return a list of production group names that match the order description."""
    assigned_groups = []
    desc_lower = description.lower()
    
    for group in groups:
        group_id = group.get("id")
        group_name = group.get("name")
        # Check required keywords if defined
        if group.get("Match_All"):
            if not match_all(group["Match_All"], desc_lower):
                logger.debug(f"Group '{group_name}' skipped because not all required keywords match.")
                continue
        # Check excluded keywords if defined
        if group.get("Exclude_All"):
            if not exclude_all(group["Exclude_All"], desc_lower):
                logger.debug(f"Group '{group_name}' skipped due to excluded keywords.")
                continue
        # Check match-any groups if defined – if any sub‐group exists then at least one keyword must match
        if group.get("Match_Any"):
            if not match_any(group["Match_Any"], desc_lower):
                logger.debug(f"Group '{group_name}' skipped because none of the optional keyword groups match.")
                continue
        # If we reach here, the group qualifies
        logger.debug(f"Assigned production group '{group_name}' to order based on description.")
        assigned_groups.append(group_name)
    
    return assigned_groups