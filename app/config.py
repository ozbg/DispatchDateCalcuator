import os

# API key used for securing all API (JSON) endpoints:
API_KEY = os.getenv("SCHEDULER_API_KEY", "0cddf104f06e58149e1858612bc6cb34")

# Hardcoded multiple users with roles. For best practice, store hashed_password
# (shown here as plain text for simplicity).
USER_CREDENTIALS = {
    "user1":   {"password": "pass1",  "role": "user"},
    "manager": {"password": "pass2",  "role": "manager"},
    "admin":   {"password": "pass33",  "role": "admin"},
}

# Any future config constants can be added here