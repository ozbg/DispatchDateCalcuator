import os
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Require that the API key is set in the environment
try:
    API_KEY = os.environ["SCHEDULER_API_KEY"]
except KeyError:
    raise EnvironmentError("SCHEDULER_API_KEY environment variable must be set.")

# Require that the user credentials are set in the environment as a valid JSON string.
try:
    USER_CREDENTIALS = json.loads(os.environ["USER_CREDENTIALS"])
except KeyError:
    raise EnvironmentError("USER_CREDENTIALS environment variable must be set as a JSON string.")
except json.JSONDecodeError as e:
    raise EnvironmentError(f"USER_CREDENTIALS environment variable is not valid JSON: {e}")

# Any future config constants can be added here.