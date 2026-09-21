import os
import json
import sqlite3
from datetime import datetime

from flask import (
    Flask,
    request,
    jsonify,
    render_template_string,
    redirect,
    url_for,
    session
)
from pywebpush import webpush, WebPushException


app = Flask(__name__)

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "smart-fire-guard-secret-change-this"
)

DATABASE = "smart_fire_guard.db"

VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_EMAIL = os.environ.get(
    "VAPID_EMAIL",
    "mailto:admin@example.com"
)


# ---------------------------------------------------------
# DATABASE
# ---------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS owners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            location TEXT,
            device_id TEXT,
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            endpoint TEXT UNIQUE NOT NULL,
            subscription_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(owner_id) REFERENCES owners(id)
        )
    """)

    conn.commit()
    conn.close()


init_db()


# ---------------------------------------------------------
# FIRE STATUS
# ---------------------------------------------------------

fire_status = {
    "fire": False,
    "flame": "SAFE",
    "temperature": 0,
    "extinguisher": "OFF",
    "notification_sent": False
}


# ---------------------------------------------------------
# PUSH NOTIFICATION
# ---------------------------------------------------------

def send_push_notification(owner_id):
    """
    Send Web Push notification to all subscriptions
    belonging to one registered owner.
    """

    if not VAPID_PRIVATE_KEY:
        print("VAPID_PRIVATE_KEY is missing.")
        return False

    conn = get_db()

    subscriptions = conn.execute(
        """
        SELECT id, endpoint, subscription_json
        FROM push_subscriptions
        WHERE owner_id = ?
        """,
        (owner_id,)
    ).fetchall()

    success = False

    payload = {
        "title": "SMART FIRE GUARD",
        "body": (
            "🔥 FIRE DETECTED! "
            "Please check the location immediately."
        ),
        "icon": "/static/fire-icon.png",
        "badge": "/static/fire-badge.png",
        "data": {
            "type": "fire_alert",
            "temperature": str(fire_status["temperature"]),
            "location": get_owner_location(owner_id),
            "url": "/dashboard"
        }
    }

    for subscription in subscriptions:

        try:
            subscription_info = json.loads(
                subscription["subscription_json"]
            )

            webpush(
                subscription_info=subscription_info,
                data=json.dumps(payload),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={
                    "sub": VAPID_EMAIL
                }
            )

            print(
                "Web Push notification sent:",
                subscription["endpoint"]
            )

            success = True

        except WebPushException as e:

            print("Web Push error:", e)

            # Remove expired/invalid subscriptions
            if getattr(e, "response", None) is not None:

                try:
                    status_code = e.response.status_code

                    if status_code in [404, 410]:
                        conn.execute(
                            """
                            DELETE FROM push_subscriptions
                            WHERE id = ?
                            """,
                            (subscription["id"],)
                        )

                except Exception:
                    pass

        except Exception as e:
            print("Notification error:", e)

    conn.commit()
    conn.close()

    return success


def get_owner_location(owner_id):
    conn = get_db()

    owner = conn.execute(
        "SELECT location FROM owners WHERE id = ?",
        (owner_id,)
    ).fetchone()

    conn.close()

    if owner:
        return owner["location"] or "Registered location"

    return "Registered location"


# ---------------------------------------------------------
# OWNER HELPERS
# ---------------------------------------------------------

def get_current_owner():
    owner_id = session.get("owner_id")

    if not owner_id:
        return None

    conn = get_db()

    owner = conn.execute(
        "SELECT * FROM owners WHERE id = ?",
        (owner_id,)
    ).fetchone()

    conn.close()

    return owner


# ---------------------------------------------------------
# SERVICE WORKER
# ---------------------------------------------------------

SERVICE_WORKER = """
const CACHE_NAME = "smart-fire-guard-v1";

self.addEventListener("install", event => {
    self.skipWaiting();
});

self.addEventListener("activate", event => {
    event.waitUntil(self.clients.claim());
});


self.addEventListener("push", event => {

    let data = {
        title: "SMART FIRE GUARD",
        body: "🔥 FIRE DETECTED!",
        icon: "/static/fire-icon.png",
        badge: "/static/fire-badge.png",
        data: {
            url: "/dashboard"
        }
    };

    try {
        if (event.data) {
            data = event.data.json();
        }
    } catch (error) {
        console.log("Push data error:", error);
    }


    const options = {
        body: data.body,

        icon: data.icon || "/static/fire-icon.png",

        badge: data.badge || "/static/fire-badge.png",

        tag: "smart-fire-alert",

        renotify: true,

        requireInteraction: true,

        vibrate: [
            500,
            200,
            500,
            200,
            1000
        ],

        data: data.data || {},

        actions: [
            {
                action: "open",
                title: "OPEN FIRE GUARD"
            }
        ]
    };


    event.waitUntil(
        self.registration.showNotification(
            data.title || "SMART FIRE GUARD",
            options
        )
    );
});


self.addEventListener("notificationclick", event => {

    event.notification.close();

    const url =
        event.notification.data &&
        event.notification.data.url
            ? event.notification.data.url
            : "/dashboard";


    event.waitUntil(

        clients.matchAll({
            type: "window",
            includeUncontrolled: true
        }).then(clientList => {

            for (const client of clientList) {

                if ("focus" in client) {

                    client.navigate(url);

                    return client.focus();
                }
            }

            if (clients.openWindow) {
                return clients.openWindow(url);
            }

        })
    );
});
"""


@app.route("/sw.js")
def service_worker():
    response = app.response_class(
        SERVICE_WORKER,
        mimetype="application/javascript"
    )

    response.headers["Service-Worker-Allowed"] = "/"

    return response


# ---------------------------------------------------------
# HOME
# ---------------------------------------------------------

@app.route("/")
def home():

    if session.get("owner_id"):
        return redirect(url_for("dashboard"))

    return redirect(url_for("register"))


# ---------------------------------------------------------
# REGISTER
# ---------------------------------------------------------

REGISTER_HTML = """
<!DOCTYPE html>
<html>
<head>

<meta name="viewport" content="width=device-width, initial-scale=1">

<title>Smart Fire Guard</title>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    font-family: Arial, sans-serif;

    background:
        radial-gradient(circle at top, #401010, #090909 65%);

    color: white;

    min-height: 100vh;

    display: flex;
    align-items: center;
    justify-content: center;

    padding: 20px;
}

.card {
    width: 100%;
    max-width: 520px;

    background: rgba(25,25,25,.95);

    border: 1px solid #5a1b1b;

    border-radius: 24px;

    padding: 30px;

    box-shadow:
        0 20px 60px rgba(0,0,0,.6);
}

.logo {
    text-align: center;

    font-size: 42px;

    margin-bottom: 5px;
}

h1 {
    text-align: center;

    margin: 0;

    color: #ff4b35;
}

.subtitle {
    text-align: center;

    color: #aaa;

    margin-bottom: 30px;
}

label {
    display: block;

    margin-top: 15px;

    color: #ddd;

    font-size: 14px;
}

input {
    width: 100%;

    padding: 14px;

    margin-top: 7px;

    border-radius: 10px;

    border: 1px solid #444;

    background: #111;

    color: white;

    font-size: 16px;
}

button {
    width: 100%;

    margin-top: 22px;

    padding: 15px;

    border: none;

    border-radius: 12px;

    background: linear-gradient(
        135deg,
        #ff3b20,
        #ff7a18
    );

    color: white;

    font-size: 17px;

    font-weight: bold;

    cursor: pointer;
}

button:hover {
    opacity: .9;
}

.info {
    margin-top: 20px;

    padding: 14px;

    background: #181818;

    border-radius: 10px;

    color: #aaa;

    font-size: 13px;

    line-height: 1.5;
}

</style>

</head>

<body>

<div class="card">

    <div class="logo">🔥</div>

    <h1>SMART FIRE GUARD</h1>

    <div class="subtitle">
        Automatic Fire Detection & Alert System
    </div>

    <form method="POST">

        <label>Owner Name</label>

        <input
            name="name"
            required
            placeholder="Enter owner name"
        >


        <label>Phone Number</label>

        <input
            name="phone"
            placeholder="+91XXXXXXXXXX"
        >


        <label>Email Address</label>

        <input
            name="email"
            type="email"
            placeholder="example@email.com"
        >


        <label>Fire Guard Location</label>

        <input
            name="location"
            placeholder="Home / Office / Shop"
        >


        <label>Device ID</label>

        <input
            name="device_id"
            placeholder="Fire Guard device ID"
        >


        <button type="submit">
            REGISTER FIRE GUARD
        </button>

    </form>


    <div class="info">

        🔔 After registration, enable browser notifications
        from the dashboard.

        <br><br>

        Your registration is saved on this device/server,
        so you can return directly to the dashboard later.

    </div>

</div>

</body>
</html>
"""


@app.route("/register", methods=["GET", "POST"])
def register():

    if session.get("owner_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        location = request.form.get("location", "").strip()
        device_id = request.form.get("device_id", "").strip()

        if not name:
            return "Owner name is required.", 400

        conn = get_db()

        cursor = conn.execute(
            """
            INSERT INTO owners
            (name, phone, email, location, device_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                phone,
                email,
                location,
                device_id,
                datetime.utcnow().isoformat()
            )
        )

        owner_id = cursor.lastrowid

        conn.commit()
        conn.close()

        session["owner_id"] = owner_id

        return redirect(url_for("dashboard"))

    return render_template_string(REGISTER_HTML)


# ---------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------

DASHBOARD_HTML = """
<!DOCTYPE html>

<html>

<head>

<meta name="viewport" content="width=device-width, initial-scale=1">

<title>Smart Fire Guard Dashboard</title>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;

    font-family: Arial, sans-serif;

    background: #080808;

    color: white;
}

.sidebar {
    position: fixed;

    left: 0;
    top: 0;
    bottom: 0;

    width: 250px;

    background:
        linear-gradient(
            180deg,
            #241010,
            #0e0e0e
        );

    border-right: 1px solid #3d2020;

    padding: 25px;
}

.brand {
    font-size: 22px;

    font-weight: bold;

    color: #ff543b;

    margin-bottom: 40px;
}

.menu {
    display: block;

    padding: 14px;

    margin-bottom: 8px;

    border-radius: 10px;

    color: #ccc;

    text-decoration: none;
}

.menu:hover,
.menu.active {
    background: #321515;

    color: white;
}

.main {
    margin-left: 250px;

    padding: 30px;
}

.header {
    display: flex;

    justify-content: space-between;

    align-items: center;

    margin-bottom: 25px;
}

.header h1 {
    margin: 0;
}

.status {
    padding: 10px 15px;

    border-radius: 20px;

    background: #12351d;

    color: #67e58b;
}

.cards {
    display: grid;

    grid-template-columns:
        repeat(auto-fit, minmax(190px, 1fr));

    gap: 18px;
}

.card {
    background: #151515;

    border: 1px solid #2e2e2e;

    border-radius: 18px;

    padding: 22px;
}

.card h3 {
    color: #aaa;

    margin-top: 0;
}

.value {
    font-size: 30px;

    font-weight: bold;
}

.safe {
    color: #54e27c;
}

.danger {
    color: #ff4d36;
}

.notification {
    margin-top: 25px;

    padding: 25px;

    background:
        linear-gradient(
            135deg,
            #241313,
            #151515
        );

    border: 1px solid #522323;

    border-radius: 18px;
}

button {
    border: none;

    border-radius: 10px;

    padding: 13px 18px;

    margin: 6px;

    cursor: pointer;

    font-weight: bold;

    color: white;

    background: #e63d27;
}

button.secondary {
    background: #333;
}

button.green {
    background: #18733a;
}

.profile {
    margin-top: 25px;
}

.profile p {
    color: #bbb;
}

.alert {
    display: none;

    margin-top: 20px;

    padding: 20px;

    background: #461515;

    border: 1px solid #ff3d2e;

    border-radius: 14px;

    color: #ff897c;
}

@media(max-width: 800px) {

    .sidebar {
        position: static;

        width: 100%;

        height: auto;
    }

    .main {
        margin-left: 0;

        padding: 18px;
    }

    .header {
        flex-direction: column;

        align-items: flex-start;

        gap: 12px;
    }

}

</style>

</head>


<body>


<div class="sidebar">

    <div class="brand">
        🔥 SMART FIRE GUARD
    </div>

    <a class="menu active" href="/dashboard">
        🏠 Dashboard
    </a>

    <a class="menu" href="/profile">
        👤 Owner Details
    </a>

    <a class="menu" href="/logout">
        🚪 Logout
    </a>

</div>


<div class="main">

    <div class="header">

        <h1>Fire Guard Dashboard</h1>

        <div class="status" id="systemStatus">
            ● SYSTEM SAFE
        </div>

    </div>


    <div class="cards">

        <div class="card">

            <h3>🔥 Flame</h3>

            <div
                class="value safe"
                id="flame"
            >
                SAFE
            </div>

        </div>


        <div class="card">

            <h3>🌡 Temperature</h3>

            <div
                class="value"
                id="temperature"
            >
                0°C
            </div>

        </div>


        <div class="card">

            <h3>🧯 Extinguisher</h3>

            <div
                class="value"
                id="extinguisher"
            >
                OFF
            </div>

        </div>


        <div class="card">

            <h3>🔔 Notification</h3>

            <div
                class="value"
                id="notification"
            >
                READY
            </div>

        </div>

    </div>


    <div class="notification">

        <h2>🔔 Web Push Notifications</h2>

        <p id="notificationStatus">
            Notifications are not enabled.
        </p>

        <button
            class="green"
            onclick="enableNotifications()"
        >
            ENABLE NOTIFICATIONS
        </button>

    </div>


    <div class="notification">

        <h2>🔥 Fire Detection Test</h2>

        <p>
            Use this button to simulate a fire detection event.
        </p>

        <button onclick="testFire()">
            TEST FIRE
        </button>

        <button
            class="secondary"
            onclick="resetSystem()"
        >
            RESET SYSTEM
        </button>

    </div>


    <div
        class="alert"
        id="fireAlert"
    >
        🔥 FIRE DETECTED! Check the protected location immediately.
    </div>


    <div class="profile">

        <div class="card">

            <h2>Owner Information</h2>

            <p>
                <b>Name:</b>
                {{ owner["name"] }}
            </p>

            <p>
                <b>Phone:</b>
                {{ owner["phone"] or "Not provided" }}
            </p>

            <p>
                <b>Email:</b>
                {{ owner["email"] or "Not provided" }}
            </p>

            <p>
                <b>Location:</b>
                {{ owner["location"] or "Not provided" }}
            </p>

            <p>
                <b>Device ID:</b>
                {{ owner["device_id"] or "Not provided" }}
            </p>

        </div>

    </div>

</div>


<script>

let vapidPublicKey = "{{ vapid_public_key }}";


function urlBase64ToUint8Array(base64String) {

    const padding = "=".repeat(
        (4 - base64String.length % 4) % 4
    );

    const base64 = (
        base64String +
        padding
    )
    .replace(/-/g, "+")
    .replace(/_/g, "/");

    const rawData = window.atob(base64);

    return Uint8Array.from(
        [...rawData].map(char => char.charCodeAt(0))
    );
}


async function enableNotifications() {

    try {

        if (!("serviceWorker" in navigator)) {

            alert(
                "This browser does not support Service Workers."
            );

            return;
        }


        if (!("PushManager" in window)) {

            alert(
                "This browser does not support Web Push."
            );

            return;
        }


        const permission =
            await Notification.requestPermission();


        if (permission !== "granted") {

            document.getElementById(
                "notificationStatus"
            ).innerText =
                "Notification permission was denied.";

            return;
        }


        const registration =
            await navigator.serviceWorker.register(
                "/sw.js"
            );


        const subscription =
            await registration.pushManager.subscribe({

                userVisibleOnly: true,

                applicationServerKey:
                    urlBase64ToUint8Array(
                        vapidPublicKey
                    )

            });


        const response = await fetch(
            "/api/save-push-subscription",
            {
                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body: JSON.stringify(
                    subscription
                )
            }
        );


        const result =
            await response.json();


        if (result.success) {

            document.getElementById(
                "notificationStatus"
            ).innerText =
                "✅ Web Push notifications are enabled.";

        } else {

            document.getElementById(
                "notificationStatus"
            ).innerText =
                "Could not save notification subscription.";

        }


    } catch (error) {

        console.error(error);

        document.getElementById(
            "notificationStatus"
        ).innerText =
            "Notification setup failed.";

    }

}


async function testFire() {

    const response =
        await fetch("/api/test-fire", {
            method: "POST"
        });

    const result =
        await response.json();

    updateScreen(result);
}


async function resetSystem() {

    const response =
        await fetch("/api/reset", {
            method: "POST"
        });

    const result =
        await response.json();

    updateScreen(result);
}


async function updateStatus() {

    try {

        const response =
            await fetch("/status");

        const data =
            await response.json();

        updateScreen(data);

    } catch (error) {

        console.log(error);

    }

}


function updateScreen(data) {

    document.getElementById(
        "flame"
    ).innerText = data.flame;


    document.getElementById(
        "temperature"
    ).innerText =
        data.temperature + "°C";


    document.getElementById(
        "extinguisher"
    ).innerText =
        data.extinguisher;


    document.getElementById(
        "notification"
    ).innerText =
        data.notification_sent
            ? "SENT"
            : "READY";


    const status =
        document.getElementById(
            "systemStatus"
        );


    const alert =
        document.getElementById(
            "fireAlert"
        );


    if (data.fire) {

        status.innerText =
            "🔥 FIRE DETECTED";

        status.style.background =
            "#461515";

        status.style.color =
            "#ff6b5a";

        document.getElementById(
            "flame"
        ).className =
            "value danger";

        alert.style.display =
            "block";

    } else {

        status.innerText =
            "● SYSTEM SAFE";

        status.style.background =
            "#12351d";

        status.style.color =
            "#67e58b";

        document.getElementById(
            "flame"
        ).className =
            "value safe";

        alert.style.display =
            "none";
    }

}


updateStatus();

setInterval(
    updateStatus,
    3000
);

</script>


</body>

</html>
"""


@app.route("/dashboard")
def dashboard():

    owner = get_current_owner()

    if not owner:
        return redirect(url_for("register"))

    return render_template_string(
        DASHBOARD_HTML,
        owner=owner,
        vapid_public_key=VAPID_PUBLIC_KEY
    )


# ---------------------------------------------------------
# SAVE PUSH SUBSCRIPTION
# ---------------------------------------------------------

@app.route(
    "/api/save-push-subscription",
    methods=["POST"]
)
def save_push_subscription():

    owner = get_current_owner()

    if not owner:
        return jsonify({
            "success": False,
            "error": "Not registered"
        }), 401


    subscription = request.get_json()

    if not subscription:
        return jsonify({
            "success": False,
            "error": "Invalid subscription"
        }), 400


    endpoint = subscription.get("endpoint")

    if not endpoint:
        return jsonify({
            "success": False,
            "error": "Missing endpoint"
        }), 400


    conn = get_db()


    existing = conn.execute(
        """
        SELECT id
        FROM push_subscriptions
        WHERE endpoint = ?
        """,
        (endpoint,)
    ).fetchone()


    if existing:

        conn.execute(
            """
            UPDATE push_subscriptions

            SET owner_id = ?,
                subscription_json = ?

            WHERE endpoint = ?
            """,
            (
                owner["id"],
                json.dumps(subscription),
                endpoint
            )
        )

    else:

        conn.execute(
            """
            INSERT INTO push_subscriptions
            (
                owner_id,
                endpoint,
                subscription_json,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                owner["id"],
                endpoint,
                json.dumps(subscription),
                datetime.utcnow().isoformat()
            )
        )


    conn.commit()
    conn.close()


    return jsonify({
        "success": True,
        "message": "Push subscription saved"
    })


# ---------------------------------------------------------
# FIRE DETECTION
# ---------------------------------------------------------

@app.route(
    "/api/test-fire",
    methods=["POST"]
)
def test_fire():

    owner = get_current_owner()

    if not owner:
        return jsonify({
            "error": "Not registered"
        }), 401


    fire_status["fire"] = True
    fire_status["flame"] = "FIRE"
    fire_status["temperature"] = 85
    fire_status["extinguisher"] = "ON"
    fire_status["notification_sent"] = False


    sent = send_push_notification(
        owner["id"]
    )


    fire_status["notification_sent"] = sent


    return jsonify(fire_status)


# ---------------------------------------------------------
# RESET
# ---------------------------------------------------------

@app.route(
    "/api/reset",
    methods=["POST"]
)
def reset_system():

    fire_status["fire"] = False
    fire_status["flame"] = "SAFE"
    fire_status["temperature"] = 0
    fire_status["extinguisher"] = "OFF"
    fire_status["notification_sent"] = False


    return jsonify(fire_status)


# ---------------------------------------------------------
# REAL SENSOR API
# ---------------------------------------------------------

@app.route(
    "/api/fire",
    methods=["POST"]
)
def real_fire_detection():

    owner = get_current_owner()

    if not owner:
        return jsonify({
            "error": "Not registered"
        }), 401


    data = request.get_json() or {}


    fire_status["fire"] = bool(
        data.get("fire", True)
    )

    fire_status["flame"] = (
        data.get("flame", "FIRE")
    )

    fire_status["temperature"] = (
        data.get("temperature", 85)
    )

    fire_status["extinguisher"] = (
        data.get("extinguisher", "ON")
    )


    if fire_status["fire"]:

        sent = send_push_notification(
            owner["id"]
        )

        fire_status["notification_sent"] = sent

    else:

        fire_status["notification_sent"] = False


    return jsonify({
        "success": True,
        "status": fire_status
    })


# ---------------------------------------------------------
# STATUS
# ---------------------------------------------------------

@app.route("/status")
def status():

    return jsonify(fire_status)


# ---------------------------------------------------------
# PROFILE
# ---------------------------------------------------------

PROFILE_HTML = """
<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
      content="width=device-width, initial-scale=1">

<title>Owner Details</title>

<style>

body {
    margin: 0;

    padding: 30px;

    font-family: Arial;

    background: #090909;

    color: white;
}

.card {
    max-width: 600px;

    margin: auto;

    background: #151515;

    padding: 30px;

    border-radius: 20px;
}

input {
    width: 100%;

    padding: 13px;

    margin:
        8px
        0
        15px;

    box-sizing: border-box;

    background: #0b0b0b;

    border: 1px solid #444;

    border-radius: 9px;

    color: white;
}

button {
    width: 100%;

    padding: 14px;

    border: 0;

    border-radius: 10px;

    background: #e64228;

    color: white;

    font-weight: bold;
}

a {
    display: block;

    margin-top: 15px;

    color: #ff654e;

    text-decoration: none;
}

</style>

</head>

<body>

<div class="card">

<h1>👤 Owner Details</h1>

<form method="POST">

<input
    name="name"
    value="{{ owner['name'] }}"
    placeholder="Name"
    required
>

<input
    name="phone"
    value="{{ owner['phone'] or '' }}"
    placeholder="Phone"
>

<input
    name="email"
    value="{{ owner['email'] or '' }}"
    placeholder="Email"
>

<input
    name="location"
    value="{{ owner['location'] or '' }}"
    placeholder="Location"
>

<input
    name="device_id"
    value="{{ owner['device_id'] or '' }}"
    placeholder="Device ID"
>

<button>
    SAVE CHANGES
</button>

</form>

<a href="/dashboard">
    ← Back to Dashboard
</a>

</div>

</body>

</html>
"""


@app.route(
    "/profile",
    methods=["GET", "POST"]
)
def profile():

    owner = get_current_owner()

    if not owner:
        return redirect(url_for("register"))


    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip()

        location = request.form.get(
            "location",
            ""
        ).strip()

        device_id = request.form.get(
            "device_id",
            ""
        ).strip()


        conn = get_db()

        conn.execute(
            """
            UPDATE owners

            SET name = ?,
                phone = ?,
                email = ?,
                location = ?,
                device_id = ?

            WHERE id = ?
            """,
            (
                name,
                phone,
                email,
                location,
                device_id,
                owner["id"]
            )
        )

        conn.commit()
        conn.close()


        return redirect(
            url_for("profile")
        )


    return render_template_string(
        PROFILE_HTML,
        owner=owner
    )


# ---------------------------------------------------------
# LOGOUT
# ---------------------------------------------------------

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("register")
    )


# ---------------------------------------------------------
# RUN
# ---------------------------------------------------------

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
