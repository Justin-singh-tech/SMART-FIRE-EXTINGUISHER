from flask import Flask, request, jsonify, render_template_string, session
import os
import secrets
import hashlib

import firebase_admin
from firebase_admin import credentials, messaging


app = Flask(__name__)

# Change this to a long random secret before deployment.
app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "smart-fire-guard-secret-change-me"
)


# ============================================================
# FIREBASE - ONLY FOR NOTIFICATIONS
# ============================================================

FIREBASE_CONFIG = {
    "apiKey": "YOUR_FIREBASE_WEB_API_KEY",
    "authDomain": "smart-fire-project.firebaseapp.com",
    "projectId": "smart-fire-project",
    "storageBucket": "smart-fire-project.firebasestorage.app",
    "messagingSenderId": "591246962485",
    "appId": "1:591246962485:web:2030ebe6c34a81f5bd667c"
}

VAPID_KEY = (
    "BDMQ6bqrix1EQOm7fOuz-PBd_jHarjFNl3WrQtmFYVg72scD_rwzvLleIwVw0jJ9"
    "JXAxrlb0ygUSquZBWYBLm4I"
)


firebase_ready = False

try:
    service_account = os.environ.get(
        "FIREBASE_SERVICE_ACCOUNT"
    )

    if service_account:

        if not firebase_admin._apps:

            firebase_admin.initialize_app(
                credentials.Certificate(
                    __import__("json").loads(
                        service_account
                    )
                )
            )

        firebase_ready = True

        print("Firebase notification system ready.")

    else:
        print(
            "WARNING: FIREBASE_SERVICE_ACCOUNT "
            "not found."
        )

except Exception as error:

    print(
        "Firebase initialization error:",
        error
    )


# ============================================================
# SIMPLE IN-MEMORY USER STORAGE
# ============================================================

users = {}

"""
Example:

users = {
    "user_id": {
        "name": "Justin",
        "phone": "1234567890",
        "email": "abc@gmail.com",
        "location": "Home",
        "device_id": "fire1",
        "password": "hashed password",
        "fcm_tokens": []
    }
}
"""


def hash_password(password):

    return hashlib.sha256(
        password.encode()
    ).hexdigest()


def find_user_by_email(email):

    for user_id, user in users.items():

        if user["email"].lower() == email.lower():

            return user_id, user

    return None, None


def current_user():

    user_id = session.get("user_id")

    if not user_id:
        return None, None

    user = users.get(user_id)

    if not user:
        session.clear()
        return None, None

    return user_id, user


# ============================================================
# FIRE NOTIFICATION
# ============================================================

def send_notification(user, temperature):

    if not firebase_ready:

        print(
            "Firebase is not ready."
        )

        return False


    tokens = user.get(
        "fcm_tokens",
        []
    )


    if not tokens:

        print(
            "No notification phone registered."
        )

        return False


    sent = False


    for token in tokens:

        try:

            message = messaging.Message(

                notification=messaging.Notification(

                    title="🔥 SMART FIRE GUARD",

                    body=(
                        "FIRE DETECTED! "
                        "Please check immediately."
                    )
                ),

                data={

                    "type": "fire_alert",

                    "temperature":
                        str(temperature),

                    "location":
                        user.get(
                            "location",
                            ""
                        )
                },

                token=token
            )


            messaging.send(message)

            sent = True

            print(
                "Fire notification sent to:",
                user["name"]
            )


        except Exception as error:

            print(
                "Notification error:",
                error
            )


    return sent


# ============================================================
# FIRE STATUS
# ============================================================

fire_status = {

    "fire": False,

    "flame": "SAFE",

    "temperature": 0,

    "extinguisher": "OFF",

    "notification_sent": False
}


# ============================================================
# FIREBASE SERVICE WORKER
# ============================================================

@app.route(
    "/firebase-messaging-sw.js"
)
def firebase_service_worker():

    javascript = f"""
importScripts(
"https://www.gstatic.com/firebasejs/12.19.0/firebase-app-compat.js"
);

importScripts(
"https://www.gstatic.com/firebasejs/12.19.0/firebase-messaging-compat.js"
);

firebase.initializeApp(
{FIREBASE_CONFIG}
);

const messaging =
firebase.messaging();

messaging.onBackgroundMessage(
function(payload) {{

    const title =
        payload.notification?.title ||
        "SMART FIRE GUARD";

    const options = {{

        body:
            payload.notification?.body ||
            "FIRE DETECTED! Please check immediately.",

        data:
            payload.data || {{}}
    }};

    self.registration.showNotification(
        title,
        options
    );
}});
"""

    return javascript, 200, {
        "Content-Type":
            "application/javascript"
    }


# ============================================================
# LOGIN / REGISTER PAGE
# ============================================================

AUTH_HTML = """

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>Smart Fire Guard</title>

<style>

body {

    margin: 0;

    min-height: 100vh;

    display: flex;

    justify-content: center;

    align-items: center;

    background: #101827;

    color: white;

    font-family: Arial;
}

.card {

    width: min(92%, 430px);

    background: #1b2638;

    padding: 25px;

    border-radius: 18px;
}

input {

    width: 100%;

    padding: 13px;

    margin: 6px 0;

    box-sizing: border-box;

    border: 0;

    border-radius: 8px;
}

button {

    width: 100%;

    padding: 13px;

    margin: 6px 0;

    border: 0;

    border-radius: 8px;

    background: #e63946;

    color: white;

    font-weight: bold;
}

.gray {

    background: #40506a;
}

.hidden {

    display: none;
}

</style>

</head>

<body>

<div class="card">

<h1>🔥 Smart Fire Guard</h1>


<div id="registerBox">

<h2>Create Account</h2>

<input
id="name"
placeholder="Full Name"
>

<input
id="phone"
placeholder="Phone Number"
>

<input
id="email"
type="email"
placeholder="Email"
>

<input
id="location"
placeholder="Location"
>

<input
id="device"
placeholder="Device ID"
>

<input
id="password"
type="password"
placeholder="Password"
>

<button onclick="registerUser()">
Register
</button>

<button
class="gray"
onclick="showLogin()"
>
Already registered? Login
</button>

</div>


<div
id="loginBox"
class="hidden"
>

<h2>Login</h2>

<input
id="loginEmail"
type="email"
placeholder="Email"
>

<input
id="loginPassword"
type="password"
placeholder="Password"
>

<button onclick="loginUser()">
Login
</button>

<button
class="gray"
onclick="showRegister()"
>
Create Account
</button>

</div>


<p id="message"></p>

</div>


<script>

function showLogin() {

    registerBox.classList.add(
        "hidden"
    );

    loginBox.classList.remove(
        "hidden"
    );
}


function showRegister() {

    loginBox.classList.add(
        "hidden"
    );

    registerBox.classList.remove(
        "hidden"
    );
}


async function registerUser() {

    const data = {

        name:
            document.getElementById(
                "name"
            ).value,

        phone:
            document.getElementById(
                "phone"
            ).value,

        email:
            document.getElementById(
                "email"
            ).value,

        location:
            document.getElementById(
                "location"
            ).value,

        device_id:
            document.getElementById(
                "device"
            ).value,

        password:
            document.getElementById(
                "password"
            ).value
    };


    const response =
        await fetch(
            "/register",
            {

                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body:
                    JSON.stringify(data)
            }
        );


    const result =
        await response.json();


    document.getElementById(
        "message"
    ).textContent =
        result.message;


    if (result.success) {

        window.location.href =
            "/dashboard";
    }
}


async function loginUser() {

    const data = {

        email:
            document.getElementById(
                "loginEmail"
            ).value,

        password:
            document.getElementById(
                "loginPassword"
            ).value
    };


    const response =
        await fetch(
            "/login",
            {

                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body:
                    JSON.stringify(data)
            }
        );


    const result =
        await response.json();


    document.getElementById(
        "message"
    ).textContent =
        result.message;


    if (result.success) {

        window.location.href =
            "/dashboard";
    }
}

</script>

</body>

</html>

"""


# ============================================================
# DASHBOARD
# ============================================================

DASHBOARD_HTML = """

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>Smart Fire Guard</title>

<style>

body {

    margin: 0;

    background: #101827;

    color: white;

    font-family: Arial;
}

header {

    background: #1b2638;

    padding: 16px;

    display: flex;

    justify-content: space-between;

    align-items: center;
}

main {

    width: min(95%, 900px);

    margin: 20px auto;
}

.card {

    background: #1b2638;

    padding: 18px;

    border-radius: 16px;

    margin-bottom: 15px;
}

.grid {

    display: grid;

    grid-template-columns:
    repeat(
        auto-fit,
        minmax(200px, 1fr)
    );

    gap: 15px;
}

.value {

    font-size: 27px;

    font-weight: bold;

    margin-top: 8px;
}

.safe {
    color: #58d68d;
}

.danger {
    color: #ff6262;
}

button {

    padding: 12px 16px;

    margin: 5px;

    border: 0;

    border-radius: 8px;

    background: #e63946;

    color: white;

    font-weight: bold;
}

.gray {
    background: #40506a;
}

input {

    width: 100%;

    padding: 12px;

    margin: 5px 0;

    box-sizing: border-box;

    border: 0;

    border-radius: 8px;
}

.hidden {
    display: none;
}

</style>

</head>

<body>


<header>

<strong>
🔥 Smart Fire Guard
</strong>

<button
class="gray"
onclick="logout()"
>
Logout
</button>

</header>


<main>


<div class="card">

<h2>
Welcome,
<span id="userName">
User
</span>
</h2>

<p>
Phone:
<span id="userPhone">
-
</span>
</p>

<button
onclick="toggleProfile()"
class="gray"
>
My Profile
</button>

<button
onclick="enableNotifications()"
>
Enable Notifications
</button>

</div>


<div
id="profile"
class="card hidden"
>

<h2>My Profile</h2>

<input
id="pName"
placeholder="Name"
>

<input
id="pPhone"
placeholder="Phone"
>

<input
id="pEmail"
placeholder="Email"
>

<input
id="pLocation"
placeholder="Location"
>

<input
id="pDevice"
placeholder="Device ID"
>

<button onclick="saveProfile()">
Save Profile
</button>

<p id="profileMessage"></p>

</div>


<div class="grid">


<div class="card">

System

<div
id="system"
class="value safe"
>
SAFE
</div>

</div>


<div class="card">

IR Sensor

<div
id="flame"
class="value"
>
SAFE
</div>

</div>


<div class="card">

Temperature

<div
id="temperature"
class="value"
>
0 °C
</div>

</div>


<div class="card">

Relay / Pump

<div
id="relay"
class="value"
>
OFF
</div>

</div>


<div class="card">

Notification

<div
id="notification"
class="value"
>
OFF
</div>

</div>


</div>


<div class="card">

<h2>System Test</h2>

<button onclick="testFire()">
TEST FIRE
</button>

<button
class="gray"
onclick="resetSystem()"
>
RESET
</button>

<p id="result"></p>

</div>


</main>


<script type="module">

import {
    initializeApp
}
from
"https://www.gstatic.com/firebasejs/12.19.0/firebase-app.js";


import {
    getMessaging,
    getToken,
    onMessage
}
from
"https://www.gstatic.com/firebasejs/12.19.0/firebase-messaging.js";


const firebaseConfig =
    __FIREBASE_CONFIG__;


const firebaseApp =
    initializeApp(
        firebaseConfig
    );


const messaging =
    getMessaging(
        firebaseApp
    );


async function loadProfile() {

    const response =
        await fetch(
            "/profile"
        );


    const data =
        await response.json();


    if (!data.success) {

        window.location.href =
            "/";

        return;
    }


    const user =
        data.user;


    document.getElementById(
        "userName"
    ).textContent =
        user.name;


    document.getElementById(
        "userPhone"
    ).textContent =
        user.phone;


    document.getElementById(
        "pName"
    ).value =
        user.name;


    document.getElementById(
        "pPhone"
    ).value =
        user.phone;


    document.getElementById(
        "pEmail"
    ).value =
        user.email;


    document.getElementById(
        "pLocation"
    ).value =
        user.location;


    document.getElementById(
        "pDevice"
    ).value =
        user.device_id;
}


window.toggleProfile =
function() {

    document.getElementById(
        "profile"
    ).classList.toggle(
        "hidden"
    );
};


window.saveProfile =
async function() {

    const data = {

        name:
            pName.value,

        phone:
            pPhone.value,

        email:
            pEmail.value,

        location:
            pLocation.value,

        device_id:
            pDevice.value
    };


    const response =
        await fetch(
            "/profile",
            {

                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body:
                    JSON.stringify(data)
            }
        );


    const result =
        await response.json();


    profileMessage.textContent =
        result.message;


    loadProfile();
};


window.enableNotifications =
async function() {

    try {

        const permission =
            await Notification.requestPermission();


        if (
            permission !==
            "granted"
        ) {

            alert(
                "Notification permission denied."
            );

            return;
        }


        const registration =
            await navigator
            .serviceWorker
            .register(
                "/firebase-messaging-sw.js"
            );


        const token =
            await getToken(
                messaging,
                {

                    vapidKey:
                        "__VAPID_KEY__",

                    serviceWorkerRegistration:
                        registration
                }
            );


        if (!token) {

            throw new Error(
                "FCM token was not created."
            );
        }


        const response =
            await fetch(
                "/save-token",
                {

                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            token: token
                        })
                }
            );


        const result =
            await response.json();


        alert(
            result.message
        );


        updateStatus();

    }

    catch(error) {

        alert(
            "Notification error: " +
            error.message
        );
    }
};


onMessage(
    messaging,
    function(payload) {

        new Notification(

            payload.notification?.title ||
            "SMART FIRE GUARD",

            {

                body:
                    payload.notification?.body ||
                    "FIRE DETECTED!"
            }
        );
    }
);


async function updateStatus() {

    const response =
        await fetch(
            "/status"
        );


    const data =
        await response.json();


    if (!data.success) {
        return;
    }


    system.textContent =
        data.fire
        ? "FIRE DETECTED"
        : "SAFE";


    system.className =
        data.fire
        ? "value danger"
        : "value safe";


    flame.textContent =
        data.flame;


    temperature.textContent =
        data.temperature +
        " °C";


    relay.textContent =
        data.extinguisher;


    notification.textContent =
        data.notification
        ? "ENABLED"
        : "OFF";
}


window.testFire =
async function() {

    const response =
        await fetch(
            "/api/test-fire",
            {
                method: "POST"
            }
        );


    const data =
        await response.json();


    result.textContent =
        data.message;


    updateStatus();
};


window.resetSystem =
async function() {

    const response =
        await fetch(
            "/api/reset",
            {
                method: "POST"
            }
        );


    const data =
        await response.json();


    result.textContent =
        data.message;


    updateStatus();
};


window.logout =
async function() {

    await fetch(
        "/logout"
    );

    window.location.href =
        "/";
};


loadProfile();

updateStatus();

setInterval(
    updateStatus,
    3000
);

</script>

</body>

</html>

""".replace(
    "__FIREBASE_CONFIG__",
    __import__("json").dumps(
        FIREBASE_CONFIG
    )
).replace(
    "__VAPID_KEY__",
    VAPID_KEY
)


# ============================================================
# ROUTES
# ============================================================

@app.route("/")
def home():

    # If already logged in,
    # go directly to dashboard.

    if session.get("user_id") in users:

        return dashboard()

    return render_template_string(
        AUTH_HTML
    )


@app.route("/dashboard")
def dashboard():

    if session.get("user_id") not in users:

        return render_template_string(
            AUTH_HTML
        )

    return render_template_string(
        DASHBOARD_HTML
    )


# ============================================================
# REGISTER
# ============================================================

@app.route(
    "/register",
    methods=["POST"]
)
def register():

    data = request.get_json(
        silent=True
    ) or {}


    name = data.get(
        "name",
        ""
    ).strip()


    phone = data.get(
        "phone",
        ""
    ).strip()


    email = data.get(
        "email",
        ""
    ).strip()


    location = data.get(
        "location",
        ""
    ).strip()


    device_id = data.get(
        "device_id",
        ""
    ).strip()


    password = data.get(
        "password",
        ""
    )


    if not name:

        return jsonify(
            success=False,
            message="Enter your name."
        )


    if not phone:

        return jsonify(
            success=False,
            message="Enter your phone number."
        )


    if not email:

        return jsonify(
            success=False,
            message="Enter your email."
        )


    if not password:

        return jsonify(
            success=False,
            message="Enter a password."
        )


    existing_id, existing_user = (
        find_user_by_email(email)
    )


    if existing_user:

        return jsonify(
            success=False,
            message="Email already registered. Please login."
        )


    user_id = secrets.token_hex(16)


    users[user_id] = {

        "name": name,

        "phone": phone,

        "email": email,

        "location": location,

        "device_id": device_id,

        "password":
            hash_password(password),

        "fcm_tokens": []
    }


    session["user_id"] =
        user_id


    return jsonify(

        success=True,

        message=
            "Registration successful."
    )


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["POST"]
)
def login():

    data = request.get_json(
        silent=True
    ) or {}


    email = data.get(
        "email",
        ""
    ).strip()


    password = data.get(
        "password",
        ""
    )


    user_id, user = (
        find_user_by_email(email)
    )


    if not user:

        return jsonify(

            success=False,

            message=
                "User not found. Please register."
        )


    if user["password"] != hash_password(
        password
    ):

        return jsonify(

            success=False,

            message=
                "Incorrect password."
        )


    session["user_id"] =
        user_id


    return jsonify(

        success=True,

        message=
            "Login successful."
    )


# ============================================================
# PROFILE
# ============================================================

@app.route(
    "/profile",
    methods=["GET", "POST"]
)
def profile():

    user_id, user = (
        current_user()
    )


    if not user:

        return jsonify(
            success=False
        ), 401


    if request.method == "GET":

        safe_user = {

            "name":
                user["name"],

            "phone":
                user["phone"],

            "email":
                user["email"],

            "location":
                user["location"],

            "device_id":
                user["device_id"]
        }


        return jsonify(

            success=True,

            user=safe_user
        )


    data = request.get_json(
        silent=True
    ) or {}


    old_device =
        user["device_id"]


    user["name"] =
        data.get(
            "name",
            user["name"]
        ).strip()


    user["phone"] =
        data.get(
            "phone",
            user["phone"]
        ).strip()


    user["email"] =
        data.get(
            "email",
            user["email"]
        ).strip()


    user["location"] =
        data.get(
            "location",
            user["location"]
        ).strip()


    user["device_id"] =
        data.get(
            "device_id",
            user["device_id"]
        ).strip()


    return jsonify(

        success=True,

        message=
            "Profile updated."
    )


# ============================================================
# SAVE FCM TOKEN
# ============================================================

@app.route(
    "/save-token",
    methods=["POST"]
)
def save_token():

    user_id, user = (
        current_user()
    )


    if not user:

        return jsonify(
            success=False,
            message="Please login."
        ), 401


    data = request.get_json(
        silent=True
    ) or {}


    token = data.get(
        "token",
        ""
    ).strip()


    if not token:

        return jsonify(

            success=False,

            message=
                "Notification token missing."
        )


    if token not in user[
        "fcm_tokens"
    ]:

        user[
            "fcm_tokens"
        ].append(token)


    return jsonify(

        success=True,

        message=
            "This phone is registered for fire notifications."
    )


# ============================================================
# STATUS
# ============================================================

@app.route("/status")
def status():

    user_id, user = (
        current_user()
    )


    if not user:

        return jsonify(
            success=False
        ), 401


    return jsonify(

        success=True,

        fire=
            fire_status["fire"],

        flame=
            fire_status["flame"],

        temperature=
            fire_status["temperature"],

        extinguisher=
            fire_status["extinguisher"],

        notification=
            len(
                user["fcm_tokens"]
            ) > 0
    )


# ============================================================
# ESP8266 FIRE API
# ============================================================

@app.route(
    "/api/fire",
    methods=["POST"]
)
def esp_fire():

    data = request.get_json(
        silent=True
    ) or {}


    device_id = data.get(
        "device_id",
        ""
    ).strip()


    if not device_id:

        return jsonify(

            success=False,

            message=
                "device_id is required."
        ), 400


    fire = bool(
        data.get(
            "fire",
            False
        )
    )


    temperature = data.get(
        "temperature",
        0
    )


    # Find the user who registered this device.
    owner_id = None
    owner = None


    for uid, user in users.items():

        if (
            user["device_id"]
            == device_id
        ):

            owner_id = uid

            owner = user

            break


    if not owner:

        return jsonify(

            success=False,

            message=
                "Device is not registered."
        ), 404


    fire_status[
        "temperature"
    ] = temperature


    if fire:

        fire_status[
            "fire"
        ] = True


        fire_status[
            "flame"
        ] = "DETECTED"


        fire_status[
            "extinguisher"
        ] = "ACTIVATED"


        # Send only once until reset.
        if not fire_status[
            "notification_sent"
        ]:

            sent = send_notification(

                owner,

                temperature
            )


            if sent:

                fire_status[
                    "notification_sent"
                ] = True


        return jsonify(

            success=True,

            fire=True,

            message=
                "Fire detected."
        )


    fire_status[
        "fire"
    ] = False


    fire_status[
        "flame"
    ] = "SAFE"


    fire_status[
        "extinguisher"
    ] = "OFF"


    return jsonify(

        success=True,

        fire=False,

        message=
            "System is safe."
    )


# ============================================================
# TEST FIRE
# ============================================================

@app.route(
    "/api/test-fire",
    methods=["POST"]
)
def test_fire():

    user_id, user = (
        current_user()
    )


    if not user:

        return jsonify(
            success=False,
            message="Please login."
        ), 401


    fire_status[
        "fire"
    ] = True


    fire_status[
        "flame"
    ] = "DETECTED"


    fire_status[
        "temperature"
    ] = 82


    fire_status[
        "extinguisher"
    ] = "ACTIVATED"


    if not fire_status[
        "notification_sent"
    ]:

        sent = send_notification(

            user,

            82
        )


        if sent:

            fire_status[
                "notification_sent"
            ] = True


    return jsonify(

        success=True,

        message=
            "Test fire activated."
    )


# ============================================================
# RESET
# ============================================================

@app.route(
    "/api/reset",
    methods=["POST"]
)
def reset():

    user_id, user = (
        current_user()
    )


    if not user:

        return jsonify(
            success=False
        ), 401


    fire_status[
        "fire"
    ] = False


    fire_status[
        "flame"
    ] = "SAFE"


    fire_status[
        "temperature"
    ] = 0


    fire_status[
        "extinguisher"
    ] = "OFF"


    fire_status[
        "notification_sent"
    ] = False


    return jsonify(

        success=True,

        message=
            "System reset."
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return jsonify(
        success=True
    )


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

    return jsonify(

        status="ok",

        users=len(users),

        firebase=firebase_ready
    )


# ============================================================
# START
# ============================================================

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
