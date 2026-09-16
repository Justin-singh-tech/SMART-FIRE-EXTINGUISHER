import os
import json
import uuid
from datetime import datetime, timezone

from flask import Flask, request, jsonify, render_template_string
import firebase_admin
from firebase_admin import credentials, firestore, messaging

app = Flask(__name__)

# ------------------------------------------------------------
# Firebase Admin
# ------------------------------------------------------------
FIREBASE_SERVICE_ACCOUNT = os.getenv("FIREBASE_SERVICE_ACCOUNT", "")
FIREBASE_VAPID_KEY = os.getenv("FIREBASE_VAPID_KEY", "")

firebase_ready = False
db = None

if FIREBASE_SERVICE_ACCOUNT:
    try:
        service_account_info = json.loads(FIREBASE_SERVICE_ACCOUNT)
        cred = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        firebase_ready = True
    except Exception as e:
        print("Firebase Admin initialization error:", e)

# This is the WEB APP config you gave for your Firebase project.
FIREBASE_CONFIG = {
    "apiKey": "AIzaSyD1JM4e0Ztg3FUhCkA4tYh8UzEOYcdn9k",
    "authDomain": "smart-fire-project.firebaseapp.com",
    "projectId": "smart-fire-project",
    "storageBucket": "smart-fire-project.firebasestorage.app",
    "messagingSenderId": "591246962485",
    "appId": "1:591246962485:web:2030ebe6c34a81f5bd667c"
}

# Temporary runtime status. Owner/device data is stored in Firestore.
status = {
    "fire": False,
    "pump": False,
    "last_event": None,
    "device_id": None
}


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def now_iso():
    return datetime.now(timezone.utc).isoformat()


def owner_ref(device_id):
    if not db or not device_id:
        return None
    return db.collection("owners").document(device_id)


def clean_owner(data):
    return {
        "name": str(data.get("name", "")).strip(),
        "phone": str(data.get("phone", "")).strip(),
        "house": str(data.get("house", "")).strip(),
        "device_id": str(data.get("device_id", "")).strip()
    }


# ------------------------------------------------------------
# Main website
# ------------------------------------------------------------
HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Smart Fire Guard</title>

<script src="https://www.gstatic.com/firebasejs/10.13.2/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/10.13.2/firebase-messaging-compat.js"></script>

<style>
*{box-sizing:border-box}
body{
    margin:0;
    font-family:Arial,Helvetica,sans-serif;
    background:#f3f6fb;
    color:#172033;
}
header{
    background:linear-gradient(135deg,#d71920,#ff6b35);
    color:white;
    padding:28px 18px;
    text-align:center;
}
header h1{margin:0 0 8px;font-size:32px}
header p{margin:0;opacity:.95}
.container{max-width:900px;margin:25px auto;padding:0 15px}
.card{
    background:white;
    border-radius:18px;
    padding:22px;
    margin-bottom:18px;
    box-shadow:0 5px 20px rgba(0,0,0,.08);
}
.hidden{display:none!important}
h2{margin-top:0}
input{
    width:100%;
    padding:13px;
    margin:7px 0 12px;
    border:1px solid #ccd3df;
    border-radius:10px;
    font-size:16px;
}
button{
    border:0;
    border-radius:10px;
    padding:12px 16px;
    margin:5px;
    font-size:15px;
    font-weight:bold;
    cursor:pointer;
}
.primary{background:#d71920;color:white}
.secondary{background:#e9eef6;color:#172033}
.success{background:#14804a;color:white}
.danger{background:#b42318;color:white}
.status{
    padding:20px;
    border-radius:15px;
    text-align:center;
    font-size:22px;
    font-weight:bold;
    margin:15px 0;
}
.safe{background:#dff7e8;color:#116332}
.fire{background:#ffe1e1;color:#a40e0e;animation:pulse 1s infinite}
@keyframes pulse{50%{opacity:.65}}
.grid{
    display:grid;
    grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
    gap:14px;
}
.stat{
    padding:18px;
    border-radius:14px;
    background:#f1f5fa;
}
.stat b{display:block;font-size:20px;margin-top:7px}
.small{font-size:13px;color:#647084}
.alert{
    padding:12px;
    border-radius:10px;
    background:#fff4d6;
    color:#6d4d00;
    margin-top:10px;
    white-space:pre-wrap;
}
footer{text-align:center;color:#697386;padding:20px}
</style>
</head>

<body>
<header>
    <h1>🔥 Smart Fire Guard</h1>
    <p>Automatic Fire Detection & Protection System</p>
</header>

<div class="container">

<!-- Registration -->
<section id="registerPage" class="card">
    <h2>👤 Register Your Home</h2>
    <p class="small">Register once on this device. When you return later, the website will open your dashboard automatically.</p>

    <form id="registerForm">
        <label>Owner Name</label>
        <input id="name" required maxlength="80" placeholder="Enter owner name">

        <label>Mobile Number</label>
        <input id="phone" required maxlength="20" placeholder="Enter mobile number">

        <label>House / Location Name</label>
        <input id="house" required maxlength="100" placeholder="Example: My Home">

        <button class="primary" type="submit">Register & Continue</button>
    </form>

    <div id="registerMsg" class="alert hidden"></div>
</section>

<!-- Dashboard -->
<section id="dashboardPage" class="hidden">
    <div class="card">
        <h2>🏠 Owner Dashboard</h2>
        <p id="welcome"></p>

        <div id="mainStatus" class="status safe">🟢 SYSTEM SAFE</div>

        <div class="grid">
            <div class="stat">
                🔥 Fire Sensor
                <b id="fireValue">No Fire</b>
            </div>
            <div class="stat">
                💧 Pump
                <b id="pumpValue">OFF</b>
            </div>
            <div class="stat">
                📡 Device
                <b id="deviceValue">Connected</b>
            </div>
            <div class="stat">
                🕒 Last Event
                <b id="lastValue">None</b>
            </div>
        </div>
    </div>

    <div class="card">
        <h2>🔔 Notifications</h2>
        <p>Enable Firebase notifications on this device. The notification token is linked to this registered device.</p>
        <button class="primary" onclick="enableNotifications()">Enable Notifications</button>
        <div id="notificationMsg" class="alert hidden"></div>
    </div>

    <div class="card">
        <h2>👤 Owner Information</h2>
        <input id="editName" placeholder="Owner name">
        <input id="editPhone" placeholder="Mobile number">
        <input id="editHouse" placeholder="House / location">
        <button class="success" onclick="saveOwner()">Save Changes</button>
        <button class="secondary" onclick="logoutDevice()">Register Another Device</button>
        <div id="ownerMsg" class="alert hidden"></div>
    </div>

    <div class="card">
        <h2>🧪 Project Test</h2>
        <p class="small">Use this only to test the website notification flow.</p>
        <button class="danger" onclick="testFire()">Test Fire Alert</button>
        <button class="secondary" onclick="resetFire()">Reset Status</button>
        <div id="testMsg" class="alert hidden"></div>
    </div>
</section>

<footer>Smart Fire Guard • School Project</footer>
</div>

<script>
const firebaseConfig = {{ firebase_config | safe }};
const vapidKey = {{ vapid_key | tojson }};

let messaging = null;

try {
    firebase.initializeApp(firebaseConfig);
    messaging = firebase.messaging();
} catch(e) {
    console.error(e);
}

function getDeviceId(){
    let id = localStorage.getItem("smartFireDeviceId");
    if(!id){
        id = crypto.randomUUID ? crypto.randomUUID() :
             ("device-" + Date.now() + "-" + Math.random().toString(16).slice(2));
        localStorage.setItem("smartFireDeviceId", id);
    }
    return id;
}

function show(id, text){
    const el = document.getElementById(id);
    el.textContent = text;
    el.classList.remove("hidden");
}

function hide(id){
    document.getElementById(id).classList.add("hidden");
}

async function loadOwner(){
    const deviceId = getDeviceId();

    try{
        const r = await fetch("/api/owner?device_id=" + encodeURIComponent(deviceId));
        const data = await r.json();

        if(data.registered){
            showDashboard(data.owner);
        }else{
            document.getElementById("registerPage").classList.remove("hidden");
            document.getElementById("dashboardPage").classList.add("hidden");
        }
    }catch(e){
        show("registerMsg","Could not connect to the server. Please reload the page.");
    }
}

function showDashboard(owner){
    document.getElementById("registerPage").classList.add("hidden");
    document.getElementById("dashboardPage").classList.remove("hidden");

    document.getElementById("welcome").textContent =
        "Welcome, " + owner.name + " • " + owner.house;

    document.getElementById("editName").value = owner.name || "";
    document.getElementById("editPhone").value = owner.phone || "";
    document.getElementById("editHouse").value = owner.house || "";

    loadStatus();
}

document.getElementById("registerForm").addEventListener("submit", async function(e){
    e.preventDefault();

    const owner = {
        name: document.getElementById("name").value.trim(),
        phone: document.getElementById("phone").value.trim(),
        house: document.getElementById("house").value.trim(),
        device_id: getDeviceId()
    };

    try{
        const r = await fetch("/register",{
            method:"POST",
            headers:{"Content-Type":"application/json"},
            body:JSON.stringify(owner)
        });

        const data = await r.json();

        if(data.ok){
            showDashboard(data.owner);
        }else{
            show("registerMsg", data.error || "Registration failed.");
        }
    }catch(e){
        show("registerMsg","Registration failed. Check your internet connection.");
    }
});

async function saveOwner(){
    const owner = {
        name: document.getElementById("editName").value.trim(),
        phone: document.getElementById("editPhone").value.trim(),
        house: document.getElementById("editHouse").value.trim(),
        device_id: getDeviceId()
    };

    try{
        const r = await fetch("/owner/update",{
            method:"POST",
            headers:{"Content-Type":"application/json"},
            body:JSON.stringify(owner)
        });
        const data = await r.json();

        if(data.ok){
            show("ownerMsg","Owner information updated successfully.");
            showDashboard(data.owner);
        }else{
            show("ownerMsg",data.error || "Could not save changes.");
        }
    }catch(e){
        show("ownerMsg","Could not connect to server.");
    }
}

function logoutDevice(){
    if(confirm("This will remove this device's local registration and show registration again. Continue?")){
        localStorage.removeItem("smartFireDeviceId");
        localStorage.removeItem("fcmToken");
        location.reload();
    }
}

async function enableNotifications(){
    if(!messaging){
        show("notificationMsg","Firebase Messaging could not start.");
        return;
    }

    if(!("Notification" in window)){
        show("notificationMsg","This browser does not support notifications.");
        return;
    }

    if(!("serviceWorker" in navigator)){
        show("notificationMsg","This browser does not support service workers.");
        return;
    }

    if(!vapidKey){
        show("notificationMsg","Firebase VAPID public key is missing on the server. Add FIREBASE_VAPID_KEY in Render.");
        return;
    }

    try{
        const permission = await Notification.requestPermission();

        if(permission !== "granted"){
            show("notificationMsg","Notification permission was not granted. Allow notifications for this website and try again.");
            return;
        }

        const registration = await navigator.serviceWorker.register("/firebase-messaging-sw.js");

        const token = await messaging.getToken({
            vapidKey: vapidKey,
            serviceWorkerRegistration: registration
        });

        if(!token){
            show("notificationMsg","Firebase did not return a notification token.");
            return;
        }

        localStorage.setItem("fcmToken", token);

        const r = await fetch("/save-fcm-token",{
            method:"POST",
            headers:{"Content-Type":"application/json"},
            body:JSON.stringify({
                device_id:getDeviceId(),
                token:token
            })
        });

        const data = await r.json();

        if(data.ok){
            show("notificationMsg","🔔 Notifications enabled on this device.");
        }else{
            show("notificationMsg",data.error || "Token could not be saved.");
        }

    }catch(e){
        console.error(e);
        show("notificationMsg",
            "Notification setup failed.\n\n" +
            (e.name || "Error") + ": " +
            (e.message || String(e))
        );
    }
}

async function loadStatus(){
    try{
        const r = await fetch("/status");
        const data = await r.json();

        document.getElementById("fireValue").textContent =
            data.fire ? "🔥 FIRE DETECTED" : "No Fire";

        document.getElementById("pumpValue").textContent =
            data.pump ? "ON" : "OFF";

        document.getElementById("lastValue").textContent =
            data.last_event || "None";

        const box = document.getElementById("mainStatus");

        if(data.fire){
            box.className = "status fire";
            box.textContent = "🔴 FIRE DETECTED";
        }else{
            box.className = "status safe";
            box.textContent = "🟢 SYSTEM SAFE";
        }
    }catch(e){}
}

async function testFire(){
    try{
        const r = await fetch("/api/test-fire",{
            method:"POST",
            headers:{"Content-Type":"application/json"},
            body:JSON.stringify({device_id:getDeviceId()})
        });
        const data = await r.json();
        show("testMsg", data.message || data.error || "Test completed.");
        loadStatus();
    }catch(e){
        show("testMsg","Test failed.");
    }
}

async function resetFire(){
    try{
        await fetch("/api/reset",{method:"POST"});
        loadStatus();
        show("testMsg","System status reset.");
    }catch(e){
        show("testMsg","Reset failed.");
    }
}

loadOwner();
setInterval(loadStatus, 3000);
</script>
</body>
</html>
"""


# ------------------------------------------------------------
# Routes
# ------------------------------------------------------------
@app.route("/")
def home():
    return render_template_string(
        HTML,
        firebase_config=json.dumps(FIREBASE_CONFIG),
        vapid_key=FIREBASE_VAPID_KEY
    )


@app.route("/firebase-messaging-sw.js")
def firebase_messaging_sw():
    # Compat SDK in the service worker is intentionally used because
    # unbundled modular Firebase service workers need extra bundling.
    sw = f"""
importScripts('https://www.gstatic.com/firebasejs/10.13.2/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.13.2/firebase-messaging-compat.js');

firebase.initializeApp({json.dumps(FIREBASE_CONFIG)});
const messaging = firebase.messaging();

messaging.onBackgroundMessage(function(payload) {{
    const notification = payload.notification || {{}};

    self.registration.showNotification(
        notification.title || "🔥 Smart Fire Guard Alert",
        {{
            body: notification.body || "Fire detected at your registered home.",
            icon: notification.icon || undefined
        }}
    );
}});
"""
    return sw, 200, {"Content-Type": "application/javascript; charset=utf-8"}


@app.route("/api/owner")
def api_owner():
    device_id = request.args.get("device_id", "").strip()

    if not device_id:
        return jsonify({"registered": False})

    if not db:
        return jsonify({
            "registered": False,
            "error": "Database is not connected. Configure FIREBASE_SERVICE_ACCOUNT."
        })

    snap = owner_ref(device_id).get()

    if not snap.exists:
        return jsonify({"registered": False})

    owner = snap.to_dict()
    return jsonify({"registered": True, "owner": owner})


@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    owner = clean_owner(data)

    if not all([owner["name"], owner["phone"], owner["house"], owner["device_id"]]):
        return jsonify({"ok": False, "error": "Please fill all registration fields."}), 400

    if not db:
        return jsonify({
            "ok": False,
            "error": "Database is not connected. Configure FIREBASE_SERVICE_ACCOUNT in Render."
        }), 500

    ref = owner_ref(owner["device_id"])
    existing = ref.get()

    if existing.exists:
        return jsonify({
            "ok": False,
            "error": "This device is already registered. Open the dashboard instead."
        }), 409

    owner["created_at"] = now_iso()
    owner["updated_at"] = now_iso()

    ref.set(owner)
    return jsonify({"ok": True, "owner": owner})


@app.route("/owner/update", methods=["POST"])
def update_owner():
    data = request.get_json(silent=True) or {}
    owner = clean_owner(data)

    if not all([owner["name"], owner["phone"], owner["house"], owner["device_id"]]):
        return jsonify({"ok": False, "error": "Please fill all fields."}), 400

    if not db:
        return jsonify({"ok": False, "error": "Database is not connected."}), 500

    ref = owner_ref(owner["device_id"])
    snap = ref.get()

    if not snap.exists:
        return jsonify({"ok": False, "error": "Owner is not registered on this device."}), 404

    owner["updated_at"] = now_iso()
    ref.set(owner, merge=True)

    return jsonify({"ok": True, "owner": ref.get().to_dict()})


@app.route("/save-fcm-token", methods=["POST"])
def save_fcm_token():
    data = request.get_json(silent=True) or {}
    device_id = str(data.get("device_id", "")).strip()
    token = str(data.get("token", "")).strip()

    if not device_id or not token:
        return jsonify({"ok": False, "error": "Device ID and token are required."}), 400

    if not db:
        return jsonify({"ok": False, "error": "Database is not connected."}), 500

    if not owner_ref(device_id).get().exists:
        return jsonify({"ok": False, "error": "Register this device first."}), 404

    # One document per browser/device token.
    token_id = uuid.uuid5(uuid.NAMESPACE_URL, token).hex

    db.collection("fcm_tokens").document(token_id).set({
        "device_id": device_id,
        "token": token,
        "updated_at": now_iso()
    }, merge=True)

    return jsonify({"ok": True})


@app.route("/status")
def get_status():
    return jsonify(status)


@app.route("/api/fire", methods=["POST"])
def fire_detected():
    """
    ESP8266 should POST:
    {
      "device_id": "the registered device id",
      "fire": true
    }

    For the school prototype, the device ID can be put in the ESP8266 code
    after registering the website on the target device.
    """
    data = request.get_json(silent=True) or {}
    device_id = str(data.get("device_id", "")).strip()

    if not device_id:
        return jsonify({"ok": False, "error": "device_id is required"}), 400

    fire = bool(data.get("fire", True))

    status["fire"] = fire
    status["pump"] = fire
    status["last_event"] = now_iso()
    status["device_id"] = device_id

    if not fire:
        return jsonify({"ok": True, "message": "Fire status cleared."})

    # Send only to notification tokens registered to this same device ID.
    sent = 0
    failed = 0

    if db and firebase_ready:
        try:
            docs = (
                db.collection("fcm_tokens")
                .where("device_id", "==", device_id)
                .stream()
            )

            for doc in docs:
                item = doc.to_dict()
                token = item.get("token")

                if not token:
                    continue

                message = messaging.Message(
                    notification=messaging.Notification(
                        title="🔥 FIRE DETECTED",
                        body="Smart Fire Guard detected a fire at your registered home."
                    ),
                    data={
                        "type": "fire",
                        "device_id": device_id
                    },
                    token=token
                )

                try:
                    messaging.send(message)
                    sent += 1
                except Exception as e:
                    failed += 1
                    print("FCM send error:", e)

        except Exception as e:
            print("FCM lookup error:", e)

    return jsonify({
        "ok": True,
        "fire": True,
        "notification_sent": sent,
        "notification_failed": failed
    })


@app.route("/api/test-fire", methods=["POST"])
def test_fire():
    data = request.get_json(silent=True) or {}
    device_id = str(data.get("device_id", "")).strip()

    if not device_id:
        return jsonify({"ok": False, "error": "Device ID is missing."}), 400

    # Reuse the real fire-notification logic.
    with app.test_request_context(
        "/api/fire",
        method="POST",
        json={"device_id": device_id, "fire": True}
    ):
        return fire_detected()


@app.route("/api/reset", methods=["POST"])
def reset():
    status["fire"] = False
    status["pump"] = False
    status["last_event"] = now_iso()
    return jsonify({"ok": True})


@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "firebase_admin": firebase_ready,
        "database": bool(db),
        "vapid_key_configured": bool(FIREBASE_VAPID_KEY)
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
