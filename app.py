from flask import Flask, request, jsonify, render_template_string, session
import os, json, secrets, hashlib
import firebase_admin
from firebase_admin import credentials, messaging

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this-secret-key")

# Firebase is used ONLY for push notifications.
FIREBASE_CONFIG = {
    "apiKey": "AIzaSyAi0Ugg_3UOtxaoCzET4BCJZ0gFfkl4_6Q",
    "authDomain": "smart-fire-extinguisher-23625.firebaseapp.com",
    "projectId": "smart-fire-extinguisher-23625",
    "storageBucket": "smart-fire-extinguisher-23625.firebasestorage.app",
    "messagingSenderId": "985046588485",
    "appId": "1:985046588485:web:3fd7e8a3f4aa8f2f61572c"
}

VAPID_KEY = (
    "BEZbXaX4nW0phum1G9oJKEhQCUlV7CAK4aWMvHN1EzqkfBv4jeS3S6epCgJjhU9lKizq4SQScX1AGUSZt8z6qSE"
    "JXAxrlb0ygUSquZBWYBLm4I"
)

firebase_ready = False
try:
    service_account = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    if service_account:
        if not firebase_admin._apps:
            firebase_admin.initialize_app(
                credentials.Certificate(json.loads(service_account))
            )
        firebase_ready = True
        print("Firebase notification service ready.")
    else:
        print("WARNING: FIREBASE_SERVICE_ACCOUNT is missing.")
except Exception as e:
    print("Firebase initialization error:", e)

# Simple in-memory storage. No Firestore and no Firebase Authentication.
# WARNING: Render may erase this data after a restart/redeploy.
users = {}
fire_status = {
    "fire": False,
    "flame": "SAFE",
    "temperature": 0,
    "extinguisher": "OFF",
    "notification_sent": False
}

def password_hash(password):
    return hashlib.sha256(password.encode()).hexdigest()

def current_user():
    uid = session.get("user_id")
    if uid and uid in users:
        return uid, users[uid]
    return None, None

def find_user(email):
    for uid, user in users.items():
        if user["email"].lower() == email.lower():
            return uid, user
    return None, None

def find_device(device_id):
    for uid, user in users.items():
        if user.get("device_id") == device_id:
            return uid, user
    return None, None

def send_fire_notification(user, temperature):
    if not firebase_ready:
        print("Firebase is not ready.")
        return False

    tokens = list(user.get("fcm_tokens", []))
    if not tokens:
        print("No notification phone registered for this user.")
        return False

    sent = False
    for token in tokens:
        try:
            message = messaging.Message(
                notification=messaging.Notification(
                    title="SMART FIRE GUARD",
                    body="FIRE DETECTED! Please check immediately."
                ),
                data={
                    "type": "fire_alert",
                    "temperature": str(temperature),
                    "location": user.get("location", "")
                },
                token=token
            )
            messaging.send(message)
            sent = True
            print("Notification sent to", user["email"])
        except Exception as e:
            print("FCM error:", e)
    return sent

@app.route("/firebase-messaging-sw.js")
def service_worker():
    js = f"""
importScripts("https://www.gstatic.com/firebasejs/12.19.0/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/12.19.0/firebase-messaging-compat.js");
firebase.initializeApp({json.dumps(FIREBASE_CONFIG)});
const messaging = firebase.messaging();

messaging.onBackgroundMessage(function(payload) {{
    const title = payload.notification?.title || "SMART FIRE GUARD";
    const options = {{
        body: payload.notification?.body || "FIRE DETECTED! Please check immediately.",
        data: payload.data || {{}}
    }};
    self.registration.showNotification(title, options);
}});
"""
    return js, 200, {"Content-Type": "application/javascript"}

AUTH_HTML = """
<!doctype html><html><head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Smart Fire Guard</title>
<style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:flex;
justify-content:center;align-items:center;background:#101827;color:white;font-family:Arial}
.card{width:min(92%,430px);background:#1b2638;padding:24px;border-radius:18px}
h1{text-align:center}input,button{width:100%;padding:13px;margin:6px 0;
border:0;border-radius:9px;font-size:15px}button{background:#e63946;color:white;
font-weight:bold}.gray{background:#40506a}.hidden{display:none}#message{min-height:24px}
</style></head><body><div class="card">
<h1>🔥 Smart Fire Guard</h1>
<div id="registerBox"><h2>Create Account</h2>
<input id="name" placeholder="Full Name">
<input id="phone" placeholder="Phone Number">
<input id="email" type="email" placeholder="Email">
<input id="location" placeholder="Location">
<input id="device" placeholder="Device ID e.g. FIRE1">
<input id="password" type="password" placeholder="Password">
<button onclick="registerUser()">Register</button>
<button class="gray" onclick="showLogin()">Already registered? Login</button>
</div>
<div id="loginBox" class="hidden"><h2>Login</h2>
<input id="loginEmail" type="email" placeholder="Email">
<input id="loginPassword" type="password" placeholder="Password">
<button onclick="loginUser()">Login</button>
<button class="gray" onclick="showRegister()">Create Account</button>
</div>
<p id="message"></p></div>
<script>
function showLogin(){registerBox.classList.add("hidden");loginBox.classList.remove("hidden");message.textContent=""}
function showRegister(){loginBox.classList.add("hidden");registerBox.classList.remove("hidden");message.textContent=""}
async function registerUser(){
 const data={
  name:document.getElementById("name").value.trim(),
  phone:document.getElementById("phone").value.trim(),
  email:document.getElementById("email").value.trim(),
  location:document.getElementById("location").value.trim(),
  device_id:document.getElementById("device").value.trim(),
  password:document.getElementById("password").value
 };
 const r=await fetch("/register",{
  method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify(data)
 });
 const d=await r.json();
 document.getElementById("message").textContent=d.message;
 if(d.success) window.location.href="/dashboard";
}
async function loginUser(){
 const data={
  email:document.getElementById("loginEmail").value.trim(),
  password:document.getElementById("loginPassword").value
 };
 const r=await fetch("/login",{
  method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify(data)
 });
 const d=await r.json();
 document.getElementById("message").textContent=d.message;
 if(d.success) window.location.href="/dashboard";
}
</script></body></html>
"""

DASHBOARD_HTML = """
<!doctype html><html><head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Smart Fire Guard Dashboard</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#101827;color:white;font-family:Arial}
header{background:#1b2638;padding:15px;display:flex;justify-content:space-between;align-items:center}
main{width:min(95%,900px);margin:20px auto}.card{background:#1b2638;padding:18px;
border-radius:16px;margin-bottom:15px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:15px}
.value{font-size:26px;font-weight:bold;margin-top:8px}.safe{color:#58d68d}.danger{color:#ff6262}
button,input{padding:12px;border:0;border-radius:8px;margin:5px 0}
button{background:#e63946;color:white;font-weight:bold;cursor:pointer}.gray{background:#40506a}
input{width:100%}.hidden{display:none}
</style></head><body>
<header><strong>🔥 Smart Fire Guard</strong><button class="gray" onclick="logout()">Logout</button></header>
<main>
<div class="card"><h2>Welcome, <span id="userName">User</span></h2>
<p>Phone: <span id="userPhone">-</span></p><p>Device: <span id="userDevice">-</span></p>
<button class="gray" onclick="toggleProfile()">My Profile</button>
<button onclick="enableNotifications()">Enable Notifications</button></div>
<div id="profile" class="card hidden"><h2>My Profile</h2>
<input id="pName" placeholder="Name"><input id="pPhone" placeholder="Phone">
<input id="pEmail" placeholder="Email"><input id="pLocation" placeholder="Location">
<input id="pDevice" placeholder="Device ID"><button onclick="saveProfile()">Save Profile</button>
<p id="profileMessage"></p></div>
<div class="grid">
<div class="card">System<div id="system" class="value safe">SAFE</div></div>
<div class="card">IR Sensor<div id="flame" class="value">SAFE</div></div>
<div class="card">Temperature<div id="temperature" class="value">0 °C</div></div>
<div class="card">Relay / Pump<div id="relay" class="value">OFF</div></div>
<div class="card">Notification<div id="notification" class="value">OFF</div></div>
</div>
<div class="card"><h2>System Test</h2>
<button onclick="testFire()">TEST FIRE</button><button class="gray" onclick="resetSystem()">RESET</button>
<p id="result"></p></div>
</main>
<script type="module">
import {initializeApp} from "https://www.gstatic.com/firebasejs/12.19.0/firebase-app.js";
import {getMessaging,getToken,onMessage} from "https://www.gstatic.com/firebasejs/12.19.0/firebase-messaging.js";
const app=initializeApp(__FIREBASE_CONFIG__);
const messaging=getMessaging(app);

async function loadProfile(){
 const r=await fetch("/profile");const d=await r.json();
 if(!d.success){location.href="/";return}
 const u=d.user;
 document.getElementById("userName").textContent=u.name||"User";
 document.getElementById("userPhone").textContent=u.phone||"-";
 document.getElementById("userDevice").textContent=u.device_id||"-";
 document.getElementById("pName").value=u.name||"";
 document.getElementById("pPhone").value=u.phone||"";
 document.getElementById("pEmail").value=u.email||"";
 document.getElementById("pLocation").value=u.location||"";
 document.getElementById("pDevice").value=u.device_id||"";
 updateStatus();
}
window.toggleProfile=()=>{
 document.getElementById("profile").classList.toggle("hidden");
};
window.saveProfile=async()=>{
 const data={
  name:document.getElementById("pName").value.trim(),
  phone:document.getElementById("pPhone").value.trim(),
  email:document.getElementById("pEmail").value.trim(),
  location:document.getElementById("pLocation").value.trim(),
  device_id:document.getElementById("pDevice").value.trim()
 };
 const r=await fetch("/profile",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
 const d=await r.json();
 document.getElementById("profileMessage").textContent=d.message;
 loadProfile();
};
window.enableNotifications=async()=>{
 try{
  if(!("Notification" in window)){alert("Notifications are not supported.");return}
  const permission=await Notification.requestPermission();
  if(permission!=="granted"){alert("Notification permission was not granted.");return}
  const registration=await navigator.serviceWorker.register("/firebase-messaging-sw.js");
  const token=await getToken(messaging,{vapidKey:"__VAPID_KEY__",serviceWorkerRegistration:registration});
  if(!token)throw new Error("FCM token was not created.");
  const r=await fetch("/save-token",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({token})});
  const d=await r.json();alert(d.message);updateStatus();
 }catch(e){alert("Notification error: "+e.message)}
};
onMessage(messaging,payload=>{
 if(Notification.permission==="granted")
  new Notification(payload.notification?.title||"SMART FIRE GUARD",
  {body:payload.notification?.body||"FIRE DETECTED!"});
});
async function updateStatus(){
 const r=await fetch("/status");const d=await r.json();if(!d.success)return;
 document.getElementById("system").textContent=d.fire?"FIRE DETECTED":"SAFE";
 document.getElementById("system").className=d.fire?"value danger":"value safe";
 document.getElementById("flame").textContent=d.flame;
 document.getElementById("temperature").textContent=d.temperature+" °C";
 document.getElementById("relay").textContent=d.extinguisher;
 document.getElementById("notification").textContent=d.notification?"ENABLED":"OFF";
}
window.testFire=async()=>{const r=await fetch("/api/test-fire",{method:"POST"});const d=await r.json();result.textContent=d.message;updateStatus()};
window.resetSystem=async()=>{const r=await fetch("/api/reset",{method:"POST"});const d=await r.json();result.textContent=d.message;updateStatus()};
window.logout=async()=>{await fetch("/logout");location.href="/"};
loadProfile();setInterval(updateStatus,3000);
</script></body></html>
""".replace("__FIREBASE_CONFIG__", json.dumps(FIREBASE_CONFIG)).replace("__VAPID_KEY__", VAPID_KEY)

@app.route("/")
def home():
    uid,user=current_user()
    return dashboard() if user else render_template_string(AUTH_HTML)

@app.route("/dashboard")
def dashboard():
    uid,user=current_user()
    return render_template_string(DASHBOARD_HTML) if user else render_template_string(AUTH_HTML)

@app.route("/register", methods=["POST"])
def register():
    data=request.get_json(silent=True) or {}
    name=data.get("name","").strip();phone=data.get("phone","").strip()
    email=data.get("email","").strip();location=data.get("location","").strip()
    device=data.get("device_id","").strip();password=data.get("password","")

    if not name or not phone or not email or not password:
        return jsonify(success=False,message="Name, phone, email and password are required."),400
    if find_user(email)[1]:
        return jsonify(success=False,message="Email already registered. Please login."),400
    if device and find_device(device)[1]:
        return jsonify(success=False,message="This Device ID is already registered."),400

    uid=secrets.token_hex(16)
    users[uid]={
        "name":name,"phone":phone,"email":email,"location":location,
        "device_id":device,"password":password_hash(password),"fcm_tokens":[]
    }
    session["user_id"]=uid
    return jsonify(success=True,message="Registration successful.")

@app.route("/login", methods=["POST"])
def login():
    data=request.get_json(silent=True) or {}
    email=data.get("email","").strip();password=data.get("password","")
    uid,user=find_user(email)
    if not user:
        return jsonify(success=False,message="User not found. Please register."),401
    if user["password"]!=password_hash(password):
        return jsonify(success=False,message="Incorrect password."),401
    session["user_id"]=uid
    return jsonify(success=True,message="Login successful.")

@app.route("/profile", methods=["GET","POST"])
def profile():
    uid,user=current_user()
    if not user:return jsonify(success=False,message="Please login."),401

    if request.method=="GET":
        safe={k:user[k] for k in ["name","phone","email","location","device_id"]}
        return jsonify(success=True,user=safe)

    data=request.get_json(silent=True) or {}
    new_device=data.get("device_id",user["device_id"]).strip()
    owner_id,owner=find_device(new_device)
    if owner and owner_id!=uid:
        return jsonify(success=False,message="This Device ID belongs to another user."),400

    user["name"]=data.get("name",user["name"]).strip()
    user["phone"]=data.get("phone",user["phone"]).strip()
    user["email"]=data.get("email",user["email"]).strip()
    user["location"]=data.get("location",user["location"]).strip()
    user["device_id"]=new_device
    return jsonify(success=True,message="Profile updated successfully.")

@app.route("/save-token", methods=["POST"])
def save_token():
    uid,user=current_user()
    if not user:return jsonify(success=False,message="Please login first."),401
    data=request.get_json(silent=True) or {};token=data.get("token","").strip()
    if not token:return jsonify(success=False,message="FCM token is missing."),400
    if token not in user["fcm_tokens"]:user["fcm_tokens"].append(token)
    return jsonify(success=True,message="This phone is registered for fire notifications.")

@app.route("/status")
def status():
    uid,user=current_user()
    if not user:return jsonify(success=False),401
    return jsonify(success=True,fire=fire_status["fire"],flame=fire_status["flame"],
                   temperature=fire_status["temperature"],extinguisher=fire_status["extinguisher"],
                   notification=bool(user["fcm_tokens"]))

@app.route("/api/fire", methods=["POST"])
def esp_fire():
    data=request.get_json(silent=True) or {}
    device=data.get("device_id","").strip()
    if not device:return jsonify(success=False,message="device_id is required."),400

    uid,owner=find_device(device)
    if not owner:return jsonify(success=False,message="Device is not registered."),404

    fire=bool(data.get("fire",False));temperature=data.get("temperature",0)
    fire_status["temperature"]=temperature

    if fire:
        fire_status["fire"]=True;fire_status["flame"]="DETECTED";fire_status["extinguisher"]="ACTIVATED"
        if not fire_status["notification_sent"]:
            if send_fire_notification(owner,temperature):
                fire_status["notification_sent"]=True
        return jsonify(success=True,fire=True,message="Fire detected and owner notified.")

    fire_status["fire"]=False;fire_status["flame"]="SAFE";fire_status["extinguisher"]="OFF"
    return jsonify(success=True,fire=False,message="System is safe.")

@app.route("/api/test-fire", methods=["POST"])
def test_fire():
    uid,user=current_user()
    if not user:return jsonify(success=False,message="Please login."),401
    fire_status["fire"]=True;fire_status["flame"]="DETECTED"
    fire_status["temperature"]=82;fire_status["extinguisher"]="ACTIVATED"
    if not fire_status["notification_sent"]:
        if send_fire_notification(user,82):fire_status["notification_sent"]=True
    return jsonify(success=True,message="Test fire activated.")

@app.route("/api/reset", methods=["POST"])
def reset():
    uid,user=current_user()
    if not user:return jsonify(success=False,message="Please login."),401
    fire_status.update({"fire":False,"flame":"SAFE","temperature":0,
                        "extinguisher":"OFF","notification_sent":False})
    return jsonify(success=True,message="System reset successfully.")

@app.route("/logout")
def logout():
    session.clear()
    return jsonify(success=True)

@app.route("/health")
def health():
    return jsonify(status="ok",firebase=firebase_ready,registered_users=len(users))

if __name__=="__main__":
    port=int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0",port=port)
