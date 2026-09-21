import os
import sqlite3
import hashlib
import secrets
from functools import wraps
from datetime import datetime, timezone

from flask import Flask, request, jsonify, session, render_template_string

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))
DB_PATH = os.environ.get("DATABASE_PATH", "smart_fire_guard.db")

# ============================================================
# DATABASE
# ============================================================

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            device_id TEXT NOT NULL UNIQUE,
            address TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS maintenance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS fire_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            device_id TEXT,
            latitude REAL,
            longitude REAL,
            accuracy REAL DEFAULT 0,
            temperature REAL DEFAULT 0,
            source TEXT DEFAULT 'website',
            created_at TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


init_db()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None

    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return user


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not get_current_user():
            return jsonify({"ok": False, "error": "Please login first."}), 401
        return func(*args, **kwargs)
    return wrapper


# Browser IDs currently polling the server.
# No Firebase or third-party notification service is used.
open_browsers = set()


# ============================================================
# MODERN FIRE-THEME SINGLE-PAGE WEBSITE
# ============================================================

PAGE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Smart Fire Guard</title>

<style>
:root{
    --bg:#070a0f;
    --panel:#10151e;
    --panel2:#151c27;
    --border:#2a3443;
    --text:#f7f8fa;
    --muted:#9ba7b8;
    --red:#ff3b30;
    --orange:#ff7a00;
    --yellow:#ffbd2e;
    --green:#25d68a;
    --blue:#4da3ff;
    --shadow:0 18px 45px rgba(0,0,0,.35);
}

*{box-sizing:border-box}

body{
    margin:0;
    min-height:100vh;
    font-family:Inter,Arial,sans-serif;
    background:
      radial-gradient(circle at 75% 0%,rgba(255,74,0,.16),transparent 30%),
      radial-gradient(circle at 10% 100%,rgba(255,59,48,.08),transparent 30%),
      var(--bg);
    color:var(--text);
}

button,input,textarea{font:inherit}

button{cursor:pointer}

.auth-wrap{
    min-height:100vh;
    display:flex;
    align-items:center;
    justify-content:center;
    padding:25px;
}

.auth-card{
    width:min(480px,100%);
    background:rgba(16,21,30,.94);
    border:1px solid var(--border);
    border-radius:24px;
    padding:32px;
    box-shadow:var(--shadow);
}

.fire-logo{
    width:65px;
    height:65px;
    border-radius:19px;
    display:flex;
    align-items:center;
    justify-content:center;
    font-size:32px;
    background:linear-gradient(145deg,var(--red),var(--orange));
    box-shadow:0 10px 30px rgba(255,59,48,.25);
    margin-bottom:18px;
}

h1,h2,h3{margin-top:0}

.subtitle{color:var(--muted)}

input,textarea{
    width:100%;
    padding:13px 14px;
    border-radius:11px;
    border:1px solid var(--border);
    background:#0b1017;
    color:white;
    outline:none;
    margin:6px 0 12px;
}

input:focus,textarea:focus{
    border-color:var(--orange);
    box-shadow:0 0 0 3px rgba(255,122,0,.1);
}

textarea{min-height:110px;resize:vertical}

.btn{
    border:0;
    border-radius:11px;
    padding:12px 17px;
    font-weight:700;
    margin:4px;
}

.btn-fire{
    color:white;
    background:linear-gradient(135deg,var(--red),var(--orange));
}

.btn-green{background:var(--green);color:#06130d}
.btn-blue{background:var(--blue);color:#06101b}
.btn-dark{background:#283344;color:white}
.btn-danger{background:#b91c2c;color:white}

.link-btn{
    background:none;
    border:0;
    color:#ff9b52;
    padding:8px;
}

.hidden{display:none!important}

#dashboardApp{display:none}

.sidebar{
    position:fixed;
    inset:0 auto 0 0;
    width:250px;
    padding:24px 15px;
    background:rgba(12,17,25,.96);
    border-right:1px solid var(--border);
    z-index:20;
}

.brand{
    display:flex;
    align-items:center;
    gap:11px;
    padding:8px 10px 25px;
    font-weight:800;
    font-size:18px;
}

.brand-icon{
    width:38px;height:38px;
    border-radius:11px;
    display:flex;align-items:center;justify-content:center;
    background:linear-gradient(145deg,var(--red),var(--orange));
}

.nav button{
    width:100%;
    border:0;
    background:transparent;
    color:#aeb8c8;
    text-align:left;
    padding:13px 14px;
    border-radius:11px;
    margin:3px 0;
}

.nav button:hover,.nav button.active{
    color:white;
    background:linear-gradient(90deg,rgba(255,59,48,.18),rgba(255,122,0,.08));
    border-left:3px solid var(--orange);
}

.main{
    margin-left:250px;
    padding:30px;
    max-width:1450px;
}

.topbar{
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:15px;
    margin-bottom:24px;
}

.live{
    display:flex;
    align-items:center;
    gap:8px;
    color:#8eeec0;
    font-size:13px;
}

.dot{
    width:9px;height:9px;border-radius:50%;
    background:var(--green);
    box-shadow:0 0 12px var(--green);
}

.card{
    background:linear-gradient(145deg,rgba(20,27,38,.96),rgba(13,18,27,.96));
    border:1px solid var(--border);
    border-radius:18px;
    padding:23px;
    margin-bottom:20px;
    box-shadow:0 10px 30px rgba(0,0,0,.18);
}

.hero{
    position:relative;
    overflow:hidden;
    background:
      radial-gradient(circle at 90% 20%,rgba(255,122,0,.24),transparent 35%),
      linear-gradient(135deg,#221116,#131923 65%);
}

.hero:after{
    content:"🔥";
    position:absolute;
    right:35px;
    top:22px;
    font-size:75px;
    opacity:.12;
}

.grid{
    display:grid;
    grid-template-columns:repeat(auto-fit,minmax(190px,1fr));
    gap:15px;
}

.stat{
    background:#0b1017;
    border:1px solid #202a38;
    border-radius:15px;
    padding:20px;
}

.stat-label{
    color:var(--muted);
    font-size:13px;
}

.stat-value{
    margin-top:9px;
    font-size:25px;
    font-weight:800;
}

.safe{color:var(--green)}
.fire{color:#ff5b52}

.alert{
    border:1px solid rgba(255,59,48,.35);
    border-left:5px solid var(--red);
    background:rgba(105,20,24,.25);
    padding:17px;
    border-radius:12px;
    margin:10px 0;
}

.maintenance{
    border:1px solid rgba(77,163,255,.25);
    border-left:5px solid var(--blue);
    background:rgba(30,75,120,.2);
    padding:17px;
    border-radius:12px;
    margin:10px 0;
}

.muted{color:var(--muted);font-size:13px}

#toast{
    position:fixed;
    right:20px;
    bottom:20px;
    width:min(380px,calc(100% - 40px));
    padding:15px 18px;
    border-radius:13px;
    background:#1c2635;
    border:1px solid #35445a;
    box-shadow:var(--shadow);
    display:none;
    z-index:100;
}

@media(max-width:760px){
    .sidebar{
        width:70px;
        padding:15px 7px;
    }

    .brand span,.nav-label{display:none}

    .brand{justify-content:center}

    .nav button{text-align:center}

    .main{
        margin-left:70px;
        padding:16px;
    }
}
</style>
</head>

<body>

<!-- =========================================================
     LOGIN / REGISTER
========================================================= -->

<div id="authScreen" class="auth-wrap">
    <div class="auth-card">

        <div class="fire-logo">🔥</div>

        <h1>Smart Fire Guard</h1>
        <p class="subtitle">
            Automatic Fire Detection & Alert System
        </p>

        <div id="registerPanel">
            <h2>Create your account</h2>

            <input id="regName" placeholder="Full Name">
            <input id="regPhone" placeholder="Phone Number">
            <input id="regEmail" type="email" placeholder="Email Address">
            <input id="regDevice" placeholder="Device ID">
            <input id="regAddress" placeholder="Location / Address">
            <input id="regPassword" type="password" placeholder="Password">

            <button class="btn btn-fire" onclick="registerUser()">
                Create Account
            </button>

            <button class="link-btn" onclick="showLogin()">
                Already registered? Login
            </button>
        </div>

        <div id="loginPanel" class="hidden">
            <h2>Welcome back</h2>

            <input id="loginEmail" type="email" placeholder="Email Address">
            <input id="loginPassword" type="password" placeholder="Password">

            <button class="btn btn-fire" onclick="loginUser()">
                Login
            </button>

            <button class="link-btn" onclick="showRegister()">
                New user? Create account
            </button>
        </div>

    </div>
</div>


<!-- =========================================================
     DASHBOARD
========================================================= -->

<div id="dashboardApp">

<aside class="sidebar">

    <div class="brand">
        <div class="brand-icon">🔥</div>
        <span>SMART FIRE GUARD</span>
    </div>

    <nav class="nav">
        <button id="navDashboard" onclick="showPage('dashboard')">
            🏠 <span class="nav-label">Dashboard</span>
        </button>

        <button id="navProfile" onclick="showPage('profile')">
            👤 <span class="nav-label">My Profile</span>
        </button>

        <button id="navMaintenance" onclick="showPage('maintenance')">
            🔧 <span class="nav-label">Maintenance</span>
        </button>

        <button id="navAlerts" onclick="showPage('alerts')">
            🚨 <span class="nav-label">Fire Alerts</span>
        </button>

        <button id="navTest" onclick="showPage('test')">
            🧪 <span class="nav-label">System Test</span>
        </button>

        <button onclick="logout()">
            🚪 <span class="nav-label">Logout</span>
        </button>
    </nav>

</aside>

<main class="main">

    <div class="topbar">
        <div>
            <h1 id="pageTitle">Dashboard</h1>
            <div class="muted">Smart Fire Guard Control Center</div>
        </div>

        <div class="live">
            <span class="dot"></span>
            Server connected
        </div>
    </div>


    <!-- DASHBOARD -->
    <section id="pageDashboard" class="page">

        <div class="card hero">
            <h2>Hello, <span id="welcomeName"></span> 👋</h2>
            <p class="subtitle">
                Your fire protection system is being monitored.
            </p>
            <p class="muted">
                Device ID: <span id="welcomeDevice"></span>
            </p>
        </div>

        <div class="grid">

            <div class="stat">
                <div class="stat-label">SYSTEM STATUS</div>
                <div id="systemStatus" class="stat-value safe">SAFE</div>
            </div>

            <div class="stat">
                <div class="stat-label">FIRE SENSOR</div>
                <div id="flameStatus" class="stat-value">SAFE</div>
            </div>

            <div class="stat">
                <div class="stat-label">TEMPERATURE</div>
                <div id="temperatureStatus" class="stat-value">0 °C</div>
            </div>

            <div class="stat">
                <div class="stat-label">PUMP / RELAY</div>
                <div id="pumpStatus" class="stat-value">OFF</div>
            </div>

        </div>

        <div class="card">
            <h2>Live System</h2>
            <p id="liveText" class="subtitle">
                System is operating normally.
            </p>
        </div>

    </section>


    <!-- PROFILE -->
    <section id="pageProfile" class="page hidden">

        <div class="card">
            <h2>👤 My Profile</h2>
            <p class="subtitle">
                Update your registration information.
            </p>

            <input id="profileName" placeholder="Full Name">
            <input id="profilePhone" placeholder="Phone Number">
            <input id="profileEmail" type="email" placeholder="Email">
            <input id="profileDevice" placeholder="Device ID">
            <input id="profileAddress" placeholder="Location / Address">

            <button class="btn btn-green" onclick="saveProfile()">
                Save Changes
            </button>
        </div>

    </section>


    <!-- MAINTENANCE -->
    <section id="pageMaintenance" class="page hidden">

        <div class="card">
            <h2>🔧 Maintenance Notifications</h2>
            <p class="subtitle">
                Maintenance messages sent by the administrator.
            </p>

            <div id="maintenanceList"></div>
        </div>

    </section>


    <!-- ALERTS -->
    <section id="pageAlerts" class="page hidden">

        <div class="card">
            <h2>🚨 Fire Alerts</h2>
            <p class="subtitle">
                Recent fire events and their locations.
            </p>

            <div id="alertsList"></div>
        </div>

    </section>


    <!-- TEST -->
    <section id="pageTest" class="page hidden">

        <div class="card hero">
            <h2>🧪 System Test</h2>

            <p class="subtitle">
                Test Fire will ask for this browser's current location
                and broadcast the alert to all currently open dashboards.
            </p>

            <button class="btn btn-fire" onclick="testFire()">
                🔥 TEST FIRE
            </button>

            <button class="btn btn-green" onclick="resetSystem()">
                Reset System
            </button>
        </div>

    </section>

</main>
</div>

<div id="toast"></div>


<script>
let browserId = localStorage.getItem("smartFireBrowserId");

if (!browserId) {
    browserId = crypto.randomUUID();
    localStorage.setItem("smartFireBrowserId", browserId);
}

let lastEventId = 0;
let maintenanceCursor = 0;


function toast(message) {
    const box = document.getElementById("toast");
    box.textContent = message;
    box.style.display = "block";

    setTimeout(() => {
        box.style.display = "none";
    }, 4500);
}


function showRegister() {
    document.getElementById("loginPanel").classList.add("hidden");
    document.getElementById("registerPanel").classList.remove("hidden");
}


function showLogin() {
    document.getElementById("registerPanel").classList.add("hidden");
    document.getElementById("loginPanel").classList.remove("hidden");
}


async function registerUser() {

    const response = await fetch("/api/register", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            name: regName.value.trim(),
            phone: regPhone.value.trim(),
            email: regEmail.value.trim(),
            device_id: regDevice.value.trim(),
            address: regAddress.value.trim(),
            password: regPassword.value
        })
    });

    const data = await response.json();

    if (!data.ok) {
        toast(data.error);
        return;
    }

    toast("Account created successfully.");
    openDashboard();
}


async function loginUser() {

    const response = await fetch("/api/login", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            email: loginEmail.value.trim(),
            password: loginPassword.value
        })
    });

    const data = await response.json();

    if (!data.ok) {
        toast(data.error);
        return;
    }

    openDashboard();
}


async function checkLogin() {

    const response = await fetch("/api/me");

    if (response.ok) {
        openDashboard();
    }
}


async function openDashboard() {

    document.getElementById("authScreen").style.display = "none";
    document.getElementById("dashboardApp").style.display = "block";

    await loadProfile();
    await loadStatus();
    await loadMaintenance();
    await loadAlerts();

    showPage("dashboard");

    registerBrowser();
}


function showPage(name) {

    document.querySelectorAll(".page").forEach(
        page => page.classList.add("hidden")
    );

    const target = document.getElementById("page" + name.charAt(0).toUpperCase() + name.slice(1));

    if (target) target.classList.remove("hidden");

    document.querySelectorAll(".nav button").forEach(
        button => button.classList.remove("active")
    );

    const nav = document.getElementById(
        "nav" + name.charAt(0).toUpperCase() + name.slice(1)
    );

    if (nav) nav.classList.add("active");

    const titles = {
        dashboard: "Dashboard",
        profile: "My Profile",
        maintenance: "Maintenance",
        alerts: "Fire Alerts",
        test: "System Test"
    };

    document.getElementById("pageTitle").textContent = titles[name];
}


async function loadProfile() {

    const response = await fetch("/api/me");

    if (!response.ok) return;

    const user = await response.json();

    welcomeName.textContent = user.name;
    welcomeDevice.textContent = user.device_id;

    profileName.value = user.name;
    profilePhone.value = user.phone;
    profileEmail.value = user.email;
    profileDevice.value = user.device_id;
    profileAddress.value = user.address;
}


async function saveProfile() {

    const response = await fetch("/api/profile", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            name: profileName.value.trim(),
            phone: profilePhone.value.trim(),
            email: profileEmail.value.trim(),
            device_id: profileDevice.value.trim(),
            address: profileAddress.value.trim()
        })
    });

    const data = await response.json();

    if (!data.ok) {
        toast(data.error);
        return;
    }

    toast("Profile updated successfully.");
    loadProfile();
}


async function loadStatus() {

    const response = await fetch("/api/status");

    if (!response.ok) return;

    const status = await response.json();

    systemStatus.textContent = status.fire ? "FIRE DETECTED" : "SAFE";
    systemStatus.className =
        "stat-value " + (status.fire ? "fire" : "safe");

    flameStatus.textContent = status.flame;
    temperatureStatus.textContent = status.temperature + " °C";
    pumpStatus.textContent = status.extinguisher;

    liveText.textContent = status.fire
        ? "🔥 Fire detected. Please check the alert location."
        : "System is operating normally.";
}


function getLocation() {

    return new Promise((resolve, reject) => {

        if (!navigator.geolocation) {
            reject(new Error("This browser does not support location."));
            return;
        }

        navigator.geolocation.getCurrentPosition(
            position => resolve({
                latitude: position.coords.latitude,
                longitude: position.coords.longitude,
                accuracy: position.coords.accuracy
            }),
            () => reject(
                new Error("Please allow location access to test the fire alert.")
            ),
            {
                enableHighAccuracy: true,
                timeout: 12000,
                maximumAge: 0
            }
        );
    });
}


async function testFire() {

    try {

        const location = await getLocation();

        const response = await fetch("/api/test-fire", {
            method: "POST",
            headers: {"Content-Type":"application/json"},
            body: JSON.stringify(location)
        });

        const data = await response.json();

        if (!data.ok) {
            toast(data.error);
            return;
        }

        toast("🔥 Fire alert sent to all open dashboards.");

        await loadStatus();
        await loadAlerts();

    } catch (error) {
        toast(error.message);
    }
}


async function resetSystem() {

    const response = await fetch("/api/reset", {
        method: "POST"
    });

    const data = await response.json();

    toast(data.message || data.error);
    loadStatus();
}


async function loadMaintenance() {

    const response = await fetch("/api/maintenance");

    if (!response.ok) return;

    const items = await response.json();

    maintenanceList.innerHTML = "";

    if (!items.length) {
        maintenanceList.innerHTML =
            '<p class="muted">No maintenance notifications yet.</p>';
        return;
    }

    items.forEach(item => {

        maintenanceList.innerHTML += `
            <div class="maintenance">
                <h3>${safe(item.title)}</h3>
                <p>${safe(item.message)}</p>
                <div class="muted">${safe(item.created_at)}</div>
            </div>
        `;
    });
}


async function loadAlerts() {

    const response = await fetch("/api/alerts");

    if (!response.ok) return;

    const items = await response.json();

    alertsList.innerHTML = "";

    if (!items.length) {
        alertsList.innerHTML =
            '<p class="muted">No fire alerts yet.</p>';
        return;
    }

    items.forEach(item => {

        const map =
            "https://www.google.com/maps?q=" +
            item.latitude + "," + item.longitude;

        alertsList.innerHTML += `
            <div class="alert">
                <h3>🔥 Fire Detected</h3>
                <p>Device: ${safe(item.device_id)}</p>
                <p>Time: ${safe(item.created_at)}</p>
                <p>
                    Location:
                    ${item.latitude}, ${item.longitude}
                </p>
                <a href="${map}" target="_blank"
                   style="color:#ff9b52;font-weight:bold">
                    Open Fire Location →
                </a>
            </div>
        `;
    });
}


async function registerBrowser() {

    await fetch("/api/open", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({browser_id: browserId})
    });
}


async function pollEvents() {

    const response = await fetch(
        "/api/events?browser_id=" +
        encodeURIComponent(browserId) +
        "&after=" + lastEventId +
        "&maintenance_after=" + maintenanceCursor
    );

    if (!response.ok) return;

    const data = await response.json();

    data.alerts.forEach(alert => {

        lastEventId = Math.max(lastEventId, alert.id);

        toast(
            "🔥 FIRE ALERT — " +
            alert.latitude + ", " +
            alert.longitude
        );

        loadStatus();
        loadAlerts();

        if (
            "Notification" in window &&
            Notification.permission === "granted"
        ) {
            new Notification("🔥 SMART FIRE GUARD", {
                body:
                    "Fire detected at " +
                    alert.latitude + ", " +
                    alert.longitude
            });
        }
    });

    data.maintenance.forEach(item => {

        maintenanceCursor = Math.max(
            maintenanceCursor,
            item.id
        );

        toast("🔧 Maintenance: " + item.title);

        if (
            "Notification" in window &&
            Notification.permission === "granted"
        ) {
            new Notification("🔧 Maintenance Notice", {
                body: item.title + ": " + item.message
            });
        }
    });
}


function requestBrowserNotifications() {

    if ("Notification" in window &&
        Notification.permission === "default") {

        Notification.requestPermission();
    }
}


async function logout() {

    await fetch("/api/logout", {
        method: "POST"
    });

    location.reload();
}


function safe(value) {

    return String(value)
        .replaceAll("&","&amp;")
        .replaceAll("<","&lt;")
        .replaceAll(">","&gt;")
        .replaceAll('"',"&quot;")
        .replaceAll("'","&#039;");
}


setInterval(pollEvents, 2000);
setInterval(loadStatus, 3000);

checkLogin();
</script>

</body>
</html>
"""


# ============================================================
# BASIC ROUTES
# ============================================================

@app.route("/")
def home():
    return render_template_string(PAGE)


# ============================================================
# AUTHENTICATION
# ============================================================

@app.route("/api/register", methods=["POST"])
def register():

    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    phone = str(data.get("phone", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    device_id = str(data.get("device_id", "")).strip()
    address = str(data.get("address", "")).strip()
    password = str(data.get("password", ""))

    if not all([name, phone, email, device_id, password]):
        return jsonify({
            "ok": False,
            "error": "Please fill all required fields."
        }), 400

    conn = get_db()

    try:
        cursor = conn.execute("""
            INSERT INTO users
            (name, phone, email, password_hash, device_id, address, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            name,
            phone,
            email,
            hash_password(password),
            device_id,
            address,
            utc_now()
        ))

        conn.commit()
        user_id = cursor.lastrowid

    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({
            "ok": False,
            "error": "Email or Device ID is already registered."
        }), 409

    conn.close()

    session["user_id"] = user_id

    return jsonify({"ok": True})


@app.route("/api/login", methods=["POST"])
def login():

    data = request.get_json(silent=True) or {}

    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    conn = get_db()

    user = conn.execute("""
        SELECT id FROM users
        WHERE email = ? AND password_hash = ?
    """, (
        email,
        hash_password(password)
    )).fetchone()

    conn.close()

    if not user:
        return jsonify({
            "ok": False,
            "error": "Invalid email or password."
        }), 401

    session["user_id"] = user["id"]

    return jsonify({"ok": True})


@app.route("/api/logout", methods=["POST"])
def logout():

    session.clear()

    return jsonify({"ok": True})


@app.route("/api/me")
def me():

    user = get_current_user()

    if not user:
        return jsonify({"ok": False}), 401

    return jsonify({
        "id": user["id"],
        "name": user["name"],
        "phone": user["phone"],
        "email": user["email"],
        "device_id": user["device_id"],
        "address": user["address"]
    })


# ============================================================
# PROFILE
# ============================================================

@app.route("/api/profile", methods=["POST"])
@login_required
def update_profile():

    user = get_current_user()
    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    phone = str(data.get("phone", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    device_id = str(data.get("device_id", "")).strip()
    address = str(data.get("address", "")).strip()

    if not all([name, phone, email, device_id]):
        return jsonify({
            "ok": False,
            "error": "Name, phone, email and device ID are required."
        }), 400

    conn = get_db()

    try:
        conn.execute("""
            UPDATE users
            SET name = ?, phone = ?, email = ?, device_id = ?, address = ?
            WHERE id = ?
        """, (
            name,
            phone,
            email,
            device_id,
            address,
            user["id"]
        ))

        conn.commit()

    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({
            "ok": False,
            "error": "Email or Device ID is already used."
        }), 409

    conn.close()

    return jsonify({"ok": True})


# ============================================================
# OPEN BROWSER REGISTRY
# ============================================================

@app.route("/api/open", methods=["POST"])
@login_required
def open_browser():

    data = request.get_json(silent=True) or {}
    browser_id = str(data.get("browser_id", "")).strip()

    if browser_id:
        open_browsers.add(browser_id)

    return jsonify({"ok": True})


# ============================================================
# FIRE STATUS
# ============================================================

fire_status = {
    "fire": False,
    "flame": "SAFE",
    "temperature": 0,
    "extinguisher": "OFF"
}


@app.route("/api/status")
def status():

    return jsonify(fire_status)


@app.route("/api/reset", methods=["POST"])
@login_required
def reset():

    fire_status.update({
        "fire": False,
        "flame": "SAFE",
        "temperature": 0,
        "extinguisher": "OFF"
    })

    return jsonify({
        "ok": True,
        "message": "System reset successfully."
    })


# ============================================================
# TEST FIRE
# ============================================================

@app.route("/api/test-fire", methods=["POST"])
@login_required
def test_fire():

    user = get_current_user()
    data = request.get_json(silent=True) or {}

    latitude = data.get("latitude")
    longitude = data.get("longitude")
    accuracy = data.get("accuracy", 0)

    if latitude is None or longitude is None:
        return jsonify({
            "ok": False,
            "error": "Current location is required."
        }), 400

    conn = get_db()

    cursor = conn.execute("""
        INSERT INTO fire_alerts
        (user_id, device_id, latitude, longitude, accuracy,
         temperature, source, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user["id"],
        user["device_id"],
        float(latitude),
        float(longitude),
        float(accuracy or 0),
        50,
        "website",
        utc_now()
    ))

    conn.commit()
    conn.close()

    fire_status.update({
        "fire": True,
        "flame": "FIRE DETECTED",
        "temperature": 50,
        "extinguisher": "ON"
    })

    return jsonify({
        "ok": True,
        "alert_id": cursor.lastrowid
    })


# ============================================================
# ESP8266 FIRE ENDPOINT
# ============================================================

@app.route("/api/fire", methods=["POST"])
def esp_fire():

    data = request.get_json(silent=True) or {}

    device_id = str(data.get("device_id", "")).strip()
    detected = bool(data.get("fire", False))
    temperature = float(data.get("temperature", 0))

    if not device_id:
        return jsonify({
            "ok": False,
            "error": "device_id is required."
        }), 400

    conn = get_db()

    user = conn.execute(
        "SELECT * FROM users WHERE device_id = ?",
        (device_id,)
    ).fetchone()

    if not user:
        conn.close()
        return jsonify({
            "ok": False,
            "error": "Device is not registered."
        }), 404

    if detected:

        # ESP8266 itself may not have a browser location.
        # If coordinates are supplied by the hardware/client,
        # store them. Otherwise latitude/longitude remain NULL.
        latitude = data.get("latitude")
        longitude = data.get("longitude")

        conn.execute("""
            INSERT INTO fire_alerts
            (user_id, device_id, latitude, longitude, accuracy,
             temperature, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user["id"],
            device_id,
            latitude,
            longitude,
            data.get("accuracy", 0),
            temperature,
            "esp8266",
            utc_now()
        ))

        conn.commit()

        fire_status.update({
            "fire": True,
            "flame": "FIRE DETECTED",
            "temperature": temperature,
            "extinguisher": "ON"
        })

    else:
        fire_status.update({
            "fire": False,
            "flame": "SAFE",
            "temperature": temperature,
            "extinguisher": "OFF"
        })

    conn.close()

    return jsonify({"ok": True})


# ============================================================
# ALERT HISTORY
# ============================================================

@app.route("/api/alerts")
@login_required
def alerts():

    conn = get_db()

    rows = conn.execute("""
        SELECT id, device_id, latitude, longitude,
               temperature, source, created_at
        FROM fire_alerts
        ORDER BY id DESC
        LIMIT 50
    """).fetchall()

    conn.close()

    return jsonify([dict(row) for row in rows])


# ============================================================
# MAINTENANCE
#
# ADMIN DEMO:
# Set ADMIN_EMAIL and ADMIN_PASSWORD in Render.
# Then visit:
# POST /api/admin/maintenance
# with JSON:
# {"title":"Maintenance","message":"System maintenance tonight."}
#
# A small admin page is also provided below.
# ============================================================

@app.route("/api/maintenance")
@login_required
def maintenance():

    conn = get_db()

    rows = conn.execute("""
        SELECT id, title, message, created_at
        FROM maintenance
        ORDER BY id DESC
        LIMIT 50
    """).fetchall()

    conn.close()

    return jsonify([dict(row) for row in rows])


def is_admin():
    user = get_current_user()
    admin_email = os.environ.get("ADMIN_EMAIL", "").strip().lower()

    return bool(
        user and
        admin_email and
        user["email"].lower() == admin_email
    )


@app.route("/admin")
def admin_page():

    if not is_admin():
        return """
        <h2>Admin Login Required</h2>
        <p>Login to the main website using the configured ADMIN_EMAIL.</p>
        """

    return """
    <h1>🔥 Smart Fire Guard Admin</h1>

    <form method="post" action="/api/admin/maintenance">
        <input name="title" placeholder="Maintenance title" required>
        <br><br>
        <textarea name="message"
                  placeholder="Maintenance message"
                  required></textarea>
        <br><br>
        <button type="submit">Send Maintenance Notice</button>
    </form>
    """


@app.route("/api/admin/maintenance", methods=["POST"])
def create_maintenance():

    if not is_admin():
        return jsonify({
            "ok": False,
            "error": "Admin access required."
        }), 403

    data = request.get_json(silent=True)

    if data:
        title = str(data.get("title", "")).strip()
        message = str(data.get("message", "")).strip()
    else:
        title = str(request.form.get("title", "")).strip()
        message = str(request.form.get("message", "")).strip()

    if not title or not message:
        return jsonify({
            "ok": False,
            "error": "Title and message are required."
        }), 400

    conn = get_db()

    cursor = conn.execute("""
        INSERT INTO maintenance
        (title, message, created_at)
        VALUES (?, ?, ?)
    """, (
        title,
        message,
        utc_now()
    ))

    conn.commit()
    conn.close()

    return jsonify({
        "ok": True,
        "id": cursor.lastrowid
    })


# ============================================================
# LIVE EVENT POLLING
#
# No Firebase.
# Every open dashboard asks this endpoint for new events.
# ============================================================

@app.route("/api/events")
@login_required
def events():

    try:
        after = int(request.args.get("after", 0))
    except ValueError:
        after = 0

    try:
        maintenance_after = int(
            request.args.get("maintenance_after", 0)
        )
    except ValueError:
        maintenance_after = 0

    conn = get_db()

    alerts_rows = conn.execute("""
        SELECT id, device_id, latitude, longitude,
               temperature, source, created_at
        FROM fire_alerts
        WHERE id > ?
        ORDER BY id ASC
        LIMIT 30
    """, (after,)).fetchall()

    maintenance_rows = conn.execute("""
        SELECT id, title, message, created_at
        FROM maintenance
        WHERE id > ?
        ORDER BY id ASC
        LIMIT 30
    """, (maintenance_after,)).fetchall()

    conn.close()

    return jsonify({
        "alerts": [dict(row) for row in alerts_rows],
        "maintenance": [dict(row) for row in maintenance_rows]
    })


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    return jsonify({
        "ok": True,
        "firebase": False,
        "database": "SQLite",
        "notifications": "Browser live polling"
    })


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
