# My Scheduler

This is a fully functional Python + FastAPI project that replicates the business logic from your JavaScript scheduling code. 

## Quick Start

1. Install dependencies:
   \`\`\`
   pip install -r requirements.txt
   \`\`\`

2. Run the server:
   \`\`\`
   uvicorn app.main:app --reload
   \`\`\`

3. Open in your browser: [http://127.0.0.1:8000](http://127.0.0.1:8000)

## Features

- **/schedule** endpoint for scheduling (POST JSON).
- **HTML UI** for managing products (add/edit/delete).
- **Tests** in \`tests/\`.

## Deployment

You can use Docker (\`Dockerfile\`) or deploy via Render/Heroku with:
\`\`\`
uvicorn app.main:app --host 0.0.0.0 --port 8000
\`\`\`
