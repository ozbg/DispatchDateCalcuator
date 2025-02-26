"""
Configuration for the CMYKhub Dispatch Calculator

Timezone handling:
- Each hub should specify its timezone in cmyk_hubs.json
- Valid timezone examples:
  - 'Australia/Melbourne' (VIC)
  - 'Australia/Sydney' (NSW)
  - 'Australia/Brisbane' (QLD)
  - 'Australia/Perth' (WA)
  
The system uses pytz for timezone handling, which automatically manages:
- Different timezone offsets
- Daylight savings transitions
- Historical timezone changes
"""

# Any future config constants can be added here