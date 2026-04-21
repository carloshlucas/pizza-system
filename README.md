# 🍕 CHL Pizzaria

A self-hosted pizza ordering system built with Flask. Customers order from a multilingual menu, the kitchen sees orders in real time, and the admin manages the menu.

## Pages

| Route | Description |
|-------|-------------|
| `/` | Customer menu (PT / EN / NL) — public |
| `/kitchen` | Kitchen display — live orders — 🔒 requires login |
| `/admin` | Admin panel — manage pizzas — 🔒 requires login |
| `/login` | Staff login page |
| `/logout` | Clears session and redirects to login |

## Stack

- **Backend:** Python / Flask + Gunicorn
- **Database:** SQLite (persisted via Docker bind mount)
- **Frontend:** Vanilla HTML + CSS + JS (Jinja2 templates)
- **Deploy:** Docker + Docker Compose

## Running locally

**1. Create a `.env` file** in the project root (never commit this):

```env
SECRET_KEY=<your-secret-key>
ADMIN_PASSWORD=<admin-password>
KITCHEN_PASSWORD=<kitchen-password>
```

**2. Add `env_file` to `docker-compose.yml`:**

```yaml
services:
  pizza:
    build: .
    ports:
      - "80:5000"
    volumes:
      - ./data:/data
    env_file:
      - .env
    restart: unless-stopped
```

**3. Start the app:**

```bash
docker-compose up --build
```

Then open [http://localhost](http://localhost) (port 80).
Staff login at [http://localhost/login](http://localhost/login).

## Running without Docker

```bash
pip install -r requirements.txt
export $(cat .env | xargs) && python app.py
```

Then open [http://localhost:5000](http://localhost:5000).

## Environment variables

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Flask session signing key — use a long random string |
| `ADMIN_PASSWORD` | Password for the admin panel |
| `KITCHEN_PASSWORD` | Password for the kitchen display |

Generate a secure secret key:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

## Configuration

The pizzeria name is configured in `app.py`:

```python
APP_CONFIG = {
    "pizzeria_name":    "CHL",                                    # ← change here only
    "secret_key":       os.environ.get("SECRET_KEY"),
    "admin_password":   os.environ.get("ADMIN_PASSWORD"),
    "kitchen_password": os.environ.get("KITCHEN_PASSWORD"),
}
```

## Features

- 🔒 Session-based authentication for admin and kitchen
- 🌍 Multilingual menu (PT, EN, NL) with ingredient auto-translation
- 🍕 Admin panel to add, edit, disable or delete pizzas
- 👨‍🍳 Kitchen display with real-time pending orders (polling every 5s)
- 💾 Persistent SQLite database via Docker bind mount (`./data`)
- 📱 Mobile-friendly layout

## Project structure

```
pizza-system/
├── app.py               # Flask app, config, DB logic, routes
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env                 # Local secrets — never commit
├── .gitignore
└── templates/
    ├── menu.html        # Customer-facing menu
    ├── kitchen.html     # Kitchen display
    ├── admin.html       # Admin panel
    └── login.html       # Staff login page
```

## First run

The database is seeded automatically with 18 classic Brazilian pizzas on first launch. Prices default to €0.00 — set them via the admin panel.