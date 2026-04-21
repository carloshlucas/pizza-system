from flask import Flask, render_template, request, jsonify, session, redirect
import sqlite3
import time
import hmac
import sys
import os

# ── APP CONFIG ────────────────────────────────────────────────────────────────

def _require_env(key: str, fallback: str = None) -> str:
    """Read an environment variable, exit with a clear error if not set."""
    value = os.environ.get(key, fallback)
    if value is None:
        print(f"ERROR: Environment variable '{key}' is not set.", file=sys.stderr)
        sys.exit(1)
    return value

APP_CONFIG = {
    "pizzeria_name":    "CHL",
    "secret_key":       _require_env("SECRET_KEY"),
    "admin_password":   _require_env("ADMIN_PASSWORD"),
    "kitchen_password": _require_env("KITCHEN_PASSWORD"),
}

DB_PATH = "/data/pizzas.db"

# ── INPUT LIMITS ──────────────────────────────────────────────────────────────

MAX_TABLE_LEN = 20
MAX_NOTES_LEN = 200
MAX_NAME_LEN  = 100
MAX_ING_LEN   = 500

# ── BRUTE FORCE PROTECTION ────────────────────────────────────────────────────

_login_attempts: dict[str, list[float]] = {}
LOGIN_MAX_ATTEMPTS = 10   # max attempts
LOGIN_WINDOW_SECS  = 300  # within 5 minutes

def _is_rate_limited(ip: str) -> bool:
    now      = time.time()
    attempts = [t for t in _login_attempts.get(ip, []) if now - t < LOGIN_WINDOW_SECS]
    _login_attempts[ip] = attempts
    return len(attempts) >= LOGIN_MAX_ATTEMPTS

def _record_attempt(ip: str):
    now = time.time()
    attempts = _login_attempts.get(ip, [])
    attempts.append(now)
    _login_attempts[ip] = attempts

def _safe_eq(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks."""
    return hmac.compare_digest(a.encode(), b.encode())

# ── TRANSLATION CONFIG ────────────────────────────────────────────────────────
# Central dictionary used by the frontend to translate ingredients and pizza
# names from Portuguese (storage language) to EN and NL.

PIZZAS_CONFIG = {
    "ingredients": {
        'Alho frito':      {'en': 'Fried garlic',         'nl': 'Gebakken knoflook'},
        'Atum':            {'en': 'Tuna',                  'nl': 'Tonijn'},
        'Azeitonas':       {'en': 'Olives',                'nl': 'Olijven'},
        'Bacon':           {'en': 'Bacon',                 'nl': 'Spek'},
        'Calabresa':       {'en': 'Calabrese sausage',     'nl': 'Calabrese worst'},
        'Catupiry':        {'en': 'Brazilian cream cheese','nl': 'Braziliaanse roomkaas'},
        'Cebola':          {'en': 'Onion',                 'nl': 'Ui'},
        'com':             {'en': 'with',                  'nl': 'met'},
        'de':              {'en': 'of',                    'nl': 'van'},
        'e':               {'en': 'and',                   'nl': 'en'},
        'Ervilha':         {'en': 'Peas',                  'nl': 'Erwten'},
        'Escarola':        {'en': 'Escarole',              'nl': 'Andijvie'},
        'Frango desfiado': {'en': 'Shredded chicken',      'nl': 'Gepluisde kip'},
        'Lombo defumado':  {'en': 'Smoked pork loin',      'nl': 'Gerookte varkenshaas'},
        'Manjericão':      {'en': 'Basil',                 'nl': 'Basilicum'},
        'Milho':           {'en': 'Corn',                  'nl': 'Maïs'},
        'Molho de tomate': {'en': 'Tomato sauce',          'nl': 'Tomatensaus'},
        'Mussarela':       {'en': 'Mozzarella',            'nl': 'Mozzarella'},
        'Orégano':         {'en': 'Oregano',               'nl': 'Oregano'},
        'Ovo cozido':      {'en': 'Boiled egg',            'nl': 'Gekookt ei'},
        'Palmito':         {'en': 'Hearts of palm',        'nl': 'Palmharten'},
        'Parmesão':        {'en': 'Parmesan',              'nl': 'Parmezaan'},
        'Pepperoni':       {'en': 'Pepperoni',             'nl': 'Pepperoni'},
        'Presunto':        {'en': 'Ham',                   'nl': 'Ham'},
        'Provolone':       {'en': 'Provolone',             'nl': 'Provolone'},
        'Tomate':          {'en': 'Tomato',                'nl': 'Tomaat'},
    },
    "pizzas": {
        'Alho e Óleo':         {'en': 'Garlic and Oil',       'nl': 'Knoflook en Olie'},
        'Atum com Catupiry':   {'en': 'Tuna with Catupiry',   'nl': 'Tonijn met Catupiry'},
        'Atum com Mussarela':  {'en': 'Tuna with Mozzarella', 'nl': 'Tonijn met Mozzarella'},
        'Bacon':               {'en': 'Bacon',                 'nl': 'Spek'},
        'Caipira':             {'en': 'Caipira',               'nl': 'Caipira'},
        'Calabresa':           {'en': 'Sausage',               'nl': 'Worst'},
        'Carijó':              {'en': 'Carijó',                'nl': 'Carijó'},
        'Escarola':            {'en': 'Escarole',              'nl': 'Andijvie'},
        'Frango com Catupiry': {'en': 'Chicken with Catupiry', 'nl': 'Kip met Catupiry'},
        'Lombo com Catupiry':  {'en': 'Loin with Catupiry',   'nl': 'Varkenshaas met Catupiry'},
        'Marguerita':          {'en': 'Margherita',            'nl': 'Margherita'},
        'Mussarela':           {'en': 'Mozzarella',            'nl': 'Mozzarella'},
        'Napolitana':          {'en': 'Neapolitan',            'nl': 'Napolitaanse'},
        'Palmito':             {'en': 'Hearts of Palm',        'nl': 'Palmharten'},
        'Pepperoni':           {'en': 'Pepperoni',             'nl': 'Pepperoni'},
        'Portuguesa':          {'en': 'Portuguese',            'nl': 'Portugese'},
        'Quatro Queijos':      {'en': 'Four Cheese',           'nl': 'Vier Kazen'},
        'Toscana':             {'en': 'Tuscan',                'nl': 'Toscaanse'},
    }
}

# ── SEED DATA ─────────────────────────────────────────────────────────────────
# Inserted once on first run if the pizzas table is empty.
# Prices default to 0.00 — set them via the admin panel.

SEED_PIZZAS = [
    # Classic
    ("Calabresa",          "Molho de tomate, calabresa, cebola, azeitonas e orégano",                                0.00),
    ("Marguerita",         "Molho de tomate, mussarela, tomate, manjericão, azeitonas e orégano",                    0.00),
    ("Mussarela",          "Molho de tomate, mussarela, azeitonas e orégano",                                        0.00),
    ("Napolitana",         "Molho de tomate, mussarela, tomate, parmesão, azeitonas e orégano",                      0.00),
    # Tuna
    ("Atum com Catupiry",  "Molho de tomate, atum, catupiry, cebola, azeitonas e orégano",                           0.00),
    ("Atum com Mussarela", "Molho de tomate, atum, mussarela, cebola, azeitonas e orégano",                          0.00),
    # Meat & Cured
    ("Bacon",              "Molho de tomate, mussarela, bacon, azeitonas e orégano",                                 0.00),
    ("Lombo com Catupiry", "Molho de tomate, lombo defumado, catupiry, azeitonas e orégano",                         0.00),
    ("Pepperoni",          "Molho de tomate, mussarela, pepperoni, azeitonas e orégano",                             0.00),
    ("Portuguesa",         "Molho de tomate, presunto, mussarela, ovo cozido, cebola, ervilha, azeitonas e orégano", 0.00),
    ("Toscana",            "Molho de tomate, mussarela, calabresa, cebola, azeitonas e orégano",                     0.00),
    # Chicken
    ("Caipira",            "Molho de tomate, frango desfiado, milho, catupiry, azeitonas e orégano",                 0.00),
    ("Carijó",             "Molho de tomate, frango desfiado, milho, bacon, catupiry, azeitonas e orégano",          0.00),
    ("Frango com Catupiry","Molho de tomate, frango desfiado, catupiry, azeitonas e orégano",                        0.00),
    # Cheese & Vegetarian
    ("Alho e Óleo",        "Molho de tomate, mussarela, alho frito, azeitonas e orégano",                           0.00),
    ("Escarola",           "Molho de tomate, escarola, mussarela, bacon, azeitonas e orégano",                      0.00),
    ("Palmito",            "Molho de tomate, mussarela, palmito, azeitonas e orégano",                              0.00),
    ("Quatro Queijos",     "Molho de tomate, mussarela, catupiry, gorgonzola, parmesão, azeitonas e orégano",       0.00),
]


# ── DATABASE ──────────────────────────────────────────────────────────────────

class Database:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self):
        """Create tables and seed initial data if the database is empty."""
        with self.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS pizzas (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT    NOT NULL,
                    ingredients TEXT    NOT NULL,
                    price       REAL    NOT NULL,
                    available   INTEGER DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS orders (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    pizza_id     INTEGER NOT NULL,
                    pizza_name   TEXT    NOT NULL,
                    table_number TEXT,
                    notes        TEXT,
                    status       TEXT DEFAULT 'pending',
                    created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(pizza_id) REFERENCES pizzas(id)
                );
            """)
            if conn.execute("SELECT COUNT(*) FROM pizzas").fetchone()[0] == 0:
                conn.executemany(
                    "INSERT INTO pizzas (name, ingredients, price) VALUES (?,?,?)",
                    SEED_PIZZAS,
                )


# ── REPOSITORIES ──────────────────────────────────────────────────────────────

class PizzaRepository:
    def __init__(self, db: Database):
        self.db = db

    def get_all(self) -> list[dict]:
        with self.db.connect() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM pizzas ORDER BY id")]

    def get_available(self) -> list[dict]:
        with self.db.connect() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM pizzas WHERE available=1")]

    def get_by_id(self, pid: int) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM pizzas WHERE id=?", (pid,)).fetchone()
            return dict(row) if row else None

    def add(self, name: str, ingredients: str, price: float):
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO pizzas (name, ingredients, price) VALUES (?,?,?)",
                (name.strip(), ingredients.strip(), price),
            )

    def update(self, pid: int, name: str, ingredients: str, price: float):
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE pizzas SET name=?, ingredients=?, price=? WHERE id=?",
                (name, ingredients, price, pid),
            )

    def delete(self, pid: int):
        with self.db.connect() as conn:
            conn.execute("DELETE FROM pizzas WHERE id=?", (pid,))

    def toggle_availability(self, pid: int):
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE pizzas SET available = 1 - available WHERE id=?", (pid,)
            )


class OrderRepository:
    def __init__(self, db: Database):
        self.db = db

    def get_pending(self) -> list[dict]:
        with self.db.connect() as conn:
            return [dict(r) for r in conn.execute("""
                SELECT o.id, o.pizza_name, o.table_number, o.notes, o.created_at, p.ingredients
                FROM orders o
                JOIN pizzas p ON o.pizza_id = p.id
                WHERE o.status = 'pending'
                ORDER BY o.created_at ASC
            """)]

    def create(self, pizza_id: int, pizza_name: str, table: str, notes: str):
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO orders (pizza_id, pizza_name, table_number, notes) VALUES (?,?,?,?)",
                (pizza_id, pizza_name, table, notes),
            )

    def mark_done(self, order_id: int):
        with self.db.connect() as conn:
            conn.execute("UPDATE orders SET status='done' WHERE id=?", (order_id,))


# ── APPLICATION ───────────────────────────────────────────────────────────────

class PizzeriaApp:
    def __init__(self):
        self.app = Flask(__name__)
        self.app.secret_key = APP_CONFIG["secret_key"]  # required for session-based auth
        self.db = Database(DB_PATH)
        self.pizzas = PizzaRepository(self.db)
        self.orders = OrderRepository(self.db)

        @self.app.context_processor
        def inject_config():
            return {"pizzeria_name": APP_CONFIG["pizzeria_name"]}

        self._register_routes()

    def _register_routes(self):
        # Pages — public
        self.app.add_url_rule("/",       view_func=self.page_menu)
        self.app.add_url_rule("/login",  view_func=self.page_login,  methods=["GET", "POST"])
        self.app.add_url_rule("/logout", view_func=self.page_logout)

        # Pages — protected
        self.app.add_url_rule("/kitchen", view_func=self.page_kitchen)
        self.app.add_url_rule("/admin",   view_func=self.page_admin)

        # Public API
        self.app.add_url_rule("/api/pizzas",  view_func=self.api_get_pizzas)
        self.app.add_url_rule("/api/order",   view_func=self.api_place_order, methods=["POST"])
        self.app.add_url_rule("/api/config",  view_func=self.api_get_config)

        # Kitchen API — protected
        self.app.add_url_rule("/api/orders/pending",             view_func=self.api_pending_orders)
        self.app.add_url_rule("/api/orders/<int:order_id>/done", view_func=self.api_complete_order, methods=["POST"])

        # Admin API — protected
        self.app.add_url_rule("/api/admin/pizzas",                  view_func=self.api_admin_list_pizzas, methods=["GET"])
        self.app.add_url_rule("/api/admin/pizzas",                  view_func=self.api_admin_add_pizza,   methods=["POST"])
        self.app.add_url_rule("/api/admin/pizzas/<int:pid>",        view_func=self.api_admin_update_pizza,methods=["PUT"])
        self.app.add_url_rule("/api/admin/pizzas/<int:pid>",        view_func=self.api_admin_delete_pizza,methods=["DELETE"])
        self.app.add_url_rule("/api/admin/pizzas/<int:pid>/toggle", view_func=self.api_admin_toggle_pizza,methods=["POST"])

    # ── Auth helpers ───────────────────────────────────────────────────────

    def _require_role(self, role: str) -> bool:
        """Returns True if the session has the required role."""
        return session.get("role") == role

    def _require_admin(self):
        """Returns a 401 response if not admin, None otherwise."""
        if not self._require_role("admin"):
            return jsonify({"error": "Unauthorized"}), 401
        return None

    def _require_kitchen(self):
        """Returns a 401 response if not kitchen or admin, None otherwise."""
        if not self._require_role("kitchen") and not self._require_role("admin"):
            return jsonify({"error": "Unauthorized"}), 401
        return None

    # ── Pages ──────────────────────────────────────────────────────────────

    def page_menu(self):
        return render_template("menu.html")

    def page_login(self):
        ip = request.remote_addr

        if request.method == "POST":
            # Rate limiting — block after too many failed attempts
            if _is_rate_limited(ip):
                return render_template("login.html", error="Too many attempts. Try again in 5 minutes.")

            pwd  = request.form.get("password", "")
            role = request.form.get("role", "")

            # Constant-time comparison to prevent timing attacks
            if role == "admin" and _safe_eq(pwd, APP_CONFIG["admin_password"]):
                session["role"] = "admin"
                return redirect("/admin")

            if role == "kitchen" and _safe_eq(pwd, APP_CONFIG["kitchen_password"]):
                session["role"] = "kitchen"
                return redirect("/kitchen")

            _record_attempt(ip)
            return render_template("login.html", error="Wrong password, try again.")

        return render_template("login.html", error=None)

    def page_logout(self):
        session.clear()
        return redirect("/login")

    def page_kitchen(self):
        if not self._require_role("kitchen") and not self._require_role("admin"):
            return redirect("/login")
        return render_template("kitchen.html")

    def page_admin(self):
        if not self._require_role("admin"):
            return redirect("/login")
        return render_template("admin.html")

    # ── Public API ─────────────────────────────────────────────────────────

    def api_get_config(self):
        return jsonify(PIZZAS_CONFIG)

    def api_get_pizzas(self):
        return jsonify(self.pizzas.get_available())

    def api_place_order(self):
        data = request.json
        if not data:
            return jsonify({"error": "Invalid request"}), 400

        # Input validation and length limits
        table = str(data.get("table", "")).strip()[:MAX_TABLE_LEN]
        notes = str(data.get("notes", "")).strip()[:MAX_NOTES_LEN]

        pizza = self.pizzas.get_by_id(data.get("pizza_id"))
        if not pizza or not pizza["available"]:
            return jsonify({"error": "Pizza unavailable"}), 400

        self.orders.create(
            pizza_id=pizza["id"],
            pizza_name=pizza["name"],
            table=table,
            notes=notes,
        )
        return jsonify({"ok": True})

    # ── Kitchen API ────────────────────────────────────────────────────────

    def api_pending_orders(self):
        err = self._require_kitchen()
        if err: return err
        return jsonify(self.orders.get_pending())

    def api_complete_order(self, order_id: int):
        err = self._require_kitchen()
        if err: return err
        self.orders.mark_done(order_id)
        return jsonify({"ok": True})

    # ── Admin API ──────────────────────────────────────────────────────────

    def api_admin_list_pizzas(self):
        err = self._require_admin()
        if err: return err
        return jsonify(self.pizzas.get_all())

    def api_admin_add_pizza(self):
        err = self._require_admin()
        if err: return err
        data = request.json
        if not data:
            return jsonify({"error": "Invalid request"}), 400

        name        = str(data.get("name", "")).strip()[:MAX_NAME_LEN]
        ingredients = str(data.get("ingredients", "")).strip()[:MAX_ING_LEN]
        if not name or not ingredients:
            return jsonify({"error": "Name and ingredients are required"}), 400

        try:
            price = float(data.get("price", 0))
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid price"}), 400

        self.pizzas.add(name, ingredients, price)
        return jsonify({"ok": True})

    def api_admin_update_pizza(self, pid: int):
        err = self._require_admin()
        if err: return err
        data  = request.json
        pizza = self.pizzas.get_by_id(pid)
        if not pizza:
            return jsonify({"error": "Not found"}), 404

        name        = str(data.get("name", pizza["name"])).strip()[:MAX_NAME_LEN]
        ingredients = str(data.get("ingredients", pizza["ingredients"])).strip()[:MAX_ING_LEN]

        try:
            price = float(data.get("price", pizza["price"]))
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid price"}), 400

        self.pizzas.update(pid, name, ingredients, price)
        return jsonify({"ok": True})

    def api_admin_delete_pizza(self, pid: int):
        err = self._require_admin()
        if err: return err
        self.pizzas.delete(pid)
        return jsonify({"ok": True})

    def api_admin_toggle_pizza(self, pid: int):
        err = self._require_admin()
        if err: return err
        self.pizzas.toggle_availability(pid)
        return jsonify({"ok": True})

    def run(self, **kwargs):
        self.db.init()
        self.app.run(**kwargs)

# ── ENTRY POINT ───────────────────────────────────────────────────────────────

pizzeria = PizzeriaApp()
app = pizzeria.app

if __name__ == "__main__":
    # Dev only — production uses gunicorn (see Dockerfile)
    pizzeria.run(host="0.0.0.0", port=5000, debug=False)
    