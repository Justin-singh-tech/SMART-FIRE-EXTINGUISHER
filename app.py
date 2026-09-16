from flask import Flask, request, jsonify, render_template_string
import os
import json

import firebase_admin
from firebase_admin import credentials, firestore, messaging, auth


app = Flask(__name__)

# ============================================================
# FIREBASE CONFIG
# ============================================================

FIREBASE_CONFIG = {
    "apiKey": "AIzaSyD1JM4e0Ztg3FUhCkC4t9Yh8UzEOYcdn9k",
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

db = None


# ============================================================
# FIREBASE ADMIN
# ============================================================

try:
    service_account = os.environ.get("FIREBASE_SERVICE_ACCOUNT")

    if service_account:
        if not firebase_admin._apps:
            firebase_admin.initialize_app(
                credentials.Certificate(
                    json.loads(service_account)
                )
            )

        db = firestore.client()
        print("Firebase Admin initialized successfully.")

    else:
        print("WARNING: FIREBASE_SERVICE_ACCOUNT is missing.")

except Exception as error:
    print("Firebase initialization error:", error)


# ============================================================
# AUTHENTICATION HELPER
# ============================================================

def get_logged_in_user():
    """
    Reads the Firebase ID token from:
    Authorization: Bearer <token>
    """

    header = request.headers.get("Authorization", "")

    if not header.startswith("Bearer "):
        return None

    token = header.split(" ", 1)[1]

    try:
        return auth.verify_id_token(token)
    except Exception:
        return None


# ============================================================
# FIRESTORE HELPERS
# ============================================================

def get_user(uid):
    if not db:
        return {}

    document = db.collection("users").document(uid).get()

    if document.exists:
        return document.to_dict()

    return {}


def save_user(uid, data):
    db.collection("users").document(uid).set(
        data,
        merge=True
    )


def get_device(device_id):
    if not db:
        return {}

    document = (
        db.collection("devices")
        .document(device_id)
        .get()
    )

    if document.exists:
        return document.to_dict()

    return {}


def get_user_tokens(uid):
    if not db:
        return []

    documents = (
        db.collection("fcm_tokens")
        .where("uid", "==", uid)
        .stream()
    )

    return [document.id for document in documents]


# ============================================================
# FIREBASE NOTIFICATION
# ============================================================

def send_fire_notification(uid, temperature, location):
    """
    Send notification ONLY to phones belonging to this user.
    """

    if not db:
        print("Firebase/Firestore is not ready.")
        return False

    tokens = get_user_tokens(uid)

    if not tokens:
        print("No registered notification phone for user:", uid)
        return False

    sent = False

    # FCM multicast supports up to 500 tokens per message.
    for start in range(0, len(tokens), 500):

        batch = tokens[start:start + 500]

        message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title="🔥 SMART FIRE GUARD",
                body=(
                    "FIRE DETECTED! "
                    "Please check your location immediately."
                )
            ),
            data={
                "type": "fire_alert",
                "temperature": str(temperature),
                "location": str(location or "")
            },
            tokens=batch
        )

        try:
            response = messaging.send_each_for_multicast(message)

            print(
                "FCM:",
                response.success_count,
                "sent,",
                response.failure_count,
                "failed."
            )

            if response.success_count > 0:
                sent = True

            # Remove invalid tokens.
            for index, result in enumerate(response.responses):

                if not result.success:
                    token = batch[index]

                    try:
                        db.collection(
                            "fcm_tokens"
                        ).document(token).delete()
                    except Exception:
                        pass

        except Exception as error:
            print("FCM notification error:", error)

    return sent


# ============================================================
# SERVICE WORKER
# ============================================================

@app.route("/firebase-messaging-sw.js")
def firebase_messaging_sw():

    javascript = f"""
importScripts(
    "https://www.gstatic.com/firebasejs/12.19.0/firebase-app-compat.js"
);

importScripts(
    "https://www.gstatic.com/firebasejs/12.19.0/firebase-messaging-compat.js"
);

firebase.initializeApp(
    {json.dumps(FIREBASE_CONFIG)}
);

const messaging = firebase.messaging();

messaging.onBackgroundMessage(function(payload) {{

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
        "Content-Type": "application/javascript"
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

* {
    box-sizing: border-box;
}

body {

    margin: 0;

    min-height: 100vh;

    display: flex;

    justify-content: center;

    align-items: center;

    font-family: Arial, sans-serif;

    background: #101827;

    color: white;
}

.card {

    width: min(92%, 430px);

    padding: 25px;

    border-radius: 18px;

    background: #1b2638;

    box-shadow: 0 10px 30px rgba(0,0,0,.3);
}

h1 {
    text-align: center;
}

input {

    width: 100%;

    padding: 13px;

    margin: 6px 0;

    border: 0;

    border-radius: 9px;
}

button {

    width: 100%;

    padding: 13px;

    margin: 6px 0;

    border: 0;

    border-radius: 9px;

    background: #e63946;

    color: white;

    font-weight: bold;

    cursor: pointer;
}

.gray {
    background: #40506a;
}

.hidden {
    display: none;
}

#message {
    min-height: 25px;
    margin-top: 10px;
}

</style>

</head>

<body>

<div class="card">

<h1>🔥 Smart Fire Guard</h1>

<!-- REGISTER -->

<div id="registerBox">

<h2>Create Account</h2>

<input
    id="name"
    placeholder="Full name"
>

<input
    id="phone"
    placeholder="Phone number"
>

<input
    id="email"
    type="email"
    placeholder="Email"
>

<input
    id="location"
    placeholder="Location / House"
>

<input
    id="deviceId"
    placeholder="Device ID e.g. HOME001"
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


<!-- LOGIN -->

<div id="loginBox" class="hidden">

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
    Create new account
</button>

</div>


<p id="message"></p>

</div>


<script type="module">

import {
    initializeApp
}
from
"https://www.gstatic.com/firebasejs/12.19.0/firebase-app.js";


import {
    getAuth,
    createUserWithEmailAndPassword,
    signInWithEmailAndPassword,
    onAuthStateChanged
}
from
"https://www.gstatic.com/firebasejs/12.19.0/firebase-auth.js";


const firebaseConfig = __FIREBASE_CONFIG__;

const firebaseApp =
    initializeApp(firebaseConfig);

const auth =
    getAuth(firebaseApp);


const message =
    document.getElementById("message");


window.showLogin = function() {

    registerBox.classList.add("hidden");

    loginBox.classList.remove("hidden");

    message.textContent = "";
};


window.showRegister = function() {

    loginBox.classList.add("hidden");

    registerBox.classList.remove("hidden");

    message.textContent = "";
};


async function getHeaders() {

    const token =
        await auth.currentUser.getIdToken();

    return {

        "Authorization":
            "Bearer " + token,

        "Content-Type":
            "application/json"
    };
}


window.registerUser = async function() {

    try {

        const nameValue =
            document.getElementById("name").value.trim();

        const phoneValue =
            document.getElementById("phone").value.trim();

        const emailValue =
            document.getElementById("email").value.trim();

        const locationValue =
            document.getElementById("location").value.trim();

        const deviceValue =
            document.getElementById("deviceId").value.trim();

        const passwordValue =
            document.getElementById("password").value;


        if (
            !nameValue ||
            !phoneValue ||
            !emailValue ||
            !passwordValue
        ) {

            message.textContent =
                "Please fill all required fields.";

            return;
        }


        const result =
            await createUserWithEmailAndPassword(
                auth,
                emailValue,
                passwordValue
            );


        const response =
            await fetch(
                "/register",
                {

                    method: "POST",

                    headers:
                        await getHeaders(),

                    body:
                        JSON.stringify({

                            name: nameValue,

                            phone: phoneValue,

                            email: emailValue,

                            location:
                                locationValue,

                            device_id:
                                deviceValue
                        })
                }
            );


        const data =
            await response.json();


        if (!response.ok) {

            throw new Error(
                data.message ||
                "Could not save profile."
            );
        }


        localStorage.setItem(
            "smart_fire_logged_in",
            "true"
        );


        window.location.href =
            "/dashboard";

    }

    catch (error) {

        message.textContent =
            error.message;
    }
};


window.loginUser = async function() {

    try {

        const emailValue =
            document.getElementById(
                "loginEmail"
            ).value.trim();

        const passwordValue =
            document.getElementById(
                "loginPassword"
            ).value;


        await signInWithEmailAndPassword(
            auth,
            emailValue,
            passwordValue
        );


        localStorage.setItem(
            "smart_fire_logged_in",
            "true"
        );


        window.location.href =
            "/dashboard";

    }

    catch (error) {

        message.textContent =
            error.message;
    }
};


/*
 Firebase Authentication keeps the login session.
 If the user is already logged in,
 send them directly to Dashboard.
*/

onAuthStateChanged(
    auth,
    function(user) {

        if (
            user &&
            localStorage.getItem(
                "smart_fire_logged_in"
            ) === "true"
        ) {

            window.location.href =
                "/dashboard";
        }
    }
);

</script>

</body>

</html>
""".replace(
    "__FIREBASE_CONFIG__",
    json.dumps(FIREBASE_CONFIG)
)


# ============================================================
# DASHBOARD
# ============================================================

DASHBOARD_HTML = """

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
      content="width=device-width, initial-scale=1">

<title>Smart Fire Guard Dashboard</title>

<style>

* {
    box-sizing: border-box;
}

body {

    margin: 0;

    background: #101827;

    color: white;

    font-family: Arial, sans-serif;
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
        repeat(auto-fit, minmax(210px, 1fr));

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

    border-radius: 9px;

    background: #e63946;

    color: white;

    font-weight: bold;

    cursor: pointer;
}

.gray {
    background: #40506a;
}

input {

    width: 100%;

    padding: 12px;

    margin: 5px 0;

    border: 0;

    border-radius: 9px;
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


<!-- USER -->

<div class="card">

<h2>
Welcome,
<span id="ownerName">User</span>
</h2>

<p>
Registered phone:
<span id="ownerPhone">-</span>
</p>

<button
    class="gray"
    onclick="toggleProfile()"
>
My Profile
</button>

<button
    onclick="enableNotifications()"
>
Enable Notifications
</button>

</div>


<!-- PROFILE -->

<div
    id="profileBox"
    class="card hidden"
>

<h2>
My Profile
</h2>

<input
    id="profileName"
    placeholder="Name"
>

<input
    id="profilePhone"
    placeholder="Phone"
>

<input
    id="profileEmail"
    placeholder="Email"
>

<input
    id="profileLocation"
    placeholder="Location"
>

<input
    id="profileDevice"
    placeholder="Device ID"
>

<button onclick="saveProfile()">
Save Profile
</button>

<p id="profileMessage"></p>

</div>


<!-- STATUS -->

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


<div class="card">

Registered Phones

<div
    id="phoneCount"
    class="value"
>
0
</div>

</div>


</div>


<!-- TEST -->

<div class="card">

<h2>
System Test
</h2>

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


<!-- ESP8266 -->

<div class="card">

<h2>
ESP8266 Device
</h2>

<p>

Your registered Device ID is used to connect
the NodeMCU to your account.

</p>

<p>

When the ESP8266 sends a fire event,
the server finds the owner of that Device ID
and sends the Firebase notification only to
that owner's registered phone.

</p>

</div>


</main>


<script type="module">

import {
    initializeApp
}
from
"https://www.gstatic.com/firebasejs/12.19.0/firebase-app.js";


import {
    getAuth,
    onAuthStateChanged,
    signOut
}
from
"https://www.gstatic.com/firebasejs/12.19.0/firebase-auth.js";


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
    initializeApp(firebaseConfig);


const auth =
    getAuth(firebaseApp);


const messaging =
    getMessaging(firebaseApp);


let currentUser = null;


async function headers() {

    const token =
        await currentUser.getIdToken();

    return {

        "Authorization":
            "Bearer " + token,

        "Content-Type":
            "application/json"
    };
}


onAuthStateChanged(
    auth,
    async function(user) {

        if (!user) {

            localStorage.removeItem(
                "smart_fire_logged_in"
            );

            window.location.href = "/";

            return;
        }


        currentUser = user;


        localStorage.setItem(
            "smart_fire_logged_in",
            "true"
        );


        await loadProfile();

        await updateStatus();

    }
);


async function loadProfile() {

    const response =
        await fetch(
            "/profile",
            {
                headers:
                    await headers()
            }
        );


    const data =
        await response.json();


    if (!data.success) {
        return;
    }


    const user =
        data.user;


    ownerName.textContent =
        user.name || currentUser.email;


    ownerPhone.textContent =
        user.phone || "-";


    profileName.value =
        user.name || "";


    profilePhone.value =
        user.phone || "";


    profileEmail.value =
        user.email || currentUser.email || "";


    profileLocation.value =
        user.location || "";


    profileDevice.value =
        user.device_id || "";
}


window.toggleProfile = function() {

    profileBox.classList.toggle(
        "hidden"
    );
};


window.saveProfile = async function() {

    const response =
        await fetch(
            "/profile",
            {

                method: "POST",

                headers:
                    await headers(),

                body:
                    JSON.stringify({

                        name:
                            profileName.value.trim(),

                        phone:
                            profilePhone.value.trim(),

                        email:
                            profileEmail.value.trim(),

                        location:
                            profileLocation.value.trim(),

                        device_id:
                            profileDevice.value.trim()
                    })
            }
        );


    const data =
        await response.json();


    profileMessage.textContent =
        data.message;


    await loadProfile();
};


window.enableNotifications = async function() {

    try {

        if (!("Notification" in window)) {

            alert(
                "This browser does not support notifications."
            );

            return;
        }


        const permission =
            await Notification.requestPermission();


        if (permission !== "granted") {

            alert(
                "Notification permission was not granted."
            );

            return;
        }


        const registration =
            await navigator.serviceWorker.register(
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
                "Firebase did not return a notification token."
            );
        }


        const response =
            await fetch(
                "/save-fcm-token",
                {

                    method: "POST",

                    headers:
                        await headers(),

                    body:
                        JSON.stringify({
                            token: token
                        })
                }
            );


        const data =
            await response.json();


        alert(
            data.message
        );


        await updateStatus();

    }

    catch (error) {

        alert(
            "Notification error: " +
            error.message
        );
    }
};


onMessage(
    messaging,
    function(payload) {

        if (
            Notification.permission ===
            "granted"
        ) {

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
    }
);


async function updateStatus() {

    if (!currentUser) {
        return;
    }


    const response =
        await fetch(
            "/status",
            {
                headers:
                    await headers()
            }
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
        "value " +
        (
            data.fire
                ? "danger"
                : "safe"
        );


    flame.textContent =
        data.flame;


    temperature.textContent =
        data.temperature +
        " °C";


    relay.textContent =
        data.extinguisher;


    notification.textContent =
        data.registered_tokens > 0
            ? "ENABLED"
            : "OFF";


    phoneCount.textContent =
        data.registered_tokens;
}


window.testFire = async function() {

    const response =
        await fetch(
            "/api/test-fire",
            {

                method: "POST",

                headers:
                    await headers()
            }
        );


    const data =
        await response.json();


    result.textContent =
        data.message;


    await updateStatus();
};


window.resetSystem = async function() {

    const response =
        await fetch(
            "/api/reset",
            {

                method: "POST",

                headers:
                    await headers()
            }
        );


    const data =
        await response.json();


    result.textContent =
        data.message;


    await updateStatus();
};


window.logout = async function() {

    await signOut(auth);

    localStorage.removeItem(
        "smart_fire_logged_in"
    );

    window.location.href = "/";
};


setInterval(
    updateStatus,
    3000
);

</script>

</body>

</html>

""".replace(
    "__FIREBASE_CONFIG__",
    json.dumps(FIREBASE_CONFIG)
).replace(
    "__VAPID_KEY__",
    VAPID_KEY
)


# ============================================================
# ROUTES
# ============================================================

@app.route("/")
def home():

    return render_template_string(
        AUTH_HTML
    )


@app.route("/dashboard")
def dashboard():

    return render_template_string(
        DASHBOARD_HTML
    )


# ============================================================
# REGISTER USER
# ============================================================

@app.route(
    "/register",
    methods=["POST"]
)
def register():

    user = get_logged_in_user()

    if not user:

        return jsonify(
            success=False,
            message="Login required."
        ), 401


    data = request.get_json(
        silent=True
    ) or {}


    uid = user["uid"]


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


    if not name or not phone:

        return jsonify(
            success=False,
            message="Name and phone are required."
        ), 400


    save_user(
        uid,
        {

            "name": name,

            "phone": phone,

            "email": email,

            "location": location,

            "device_id": device_id
        }
    )


    # Connect Device ID to this Firebase user.
    if device_id:

        db.collection(
            "devices"
        ).document(
            device_id
        ).set(

            {

                "owner_id": uid,

                "device_id": device_id,

                "name":
                    "Smart Fire Guard"

            },

            merge=True
        )


    return jsonify(
        success=True,
        message="Registration saved successfully."
    )


# ============================================================
# PROFILE
# ============================================================

@app.route(
    "/profile",
    methods=["GET", "POST"]
)
def profile():

    user = get_logged_in_user()

    if not user:

        return jsonify(
            success=False,
            message="Login required."
        ), 401


    uid = user["uid"]


    if request.method == "GET":

        return jsonify(
            success=True,
            user=get_user(uid)
        )


    data = request.get_json(
        silent=True
    ) or {}


    device_id = data.get(
        "device_id",
        ""
    ).strip()


    save_user(
        uid,
        {

            "name":
                data.get(
                    "name",
                    ""
                ).strip(),

            "phone":
                data.get(
                    "phone",
                    ""
                ).strip(),

            "email":
                data.get(
                    "email",
                    ""
                ).strip(),

            "location":
                data.get(
                    "location",
                    ""
                ).strip(),

            "device_id":
                device_id
        }
    )


    if device_id:

        db.collection(
            "devices"
        ).document(
            device_id
        ).set(

            {

                "owner_id": uid,

                "device_id":
                    device_id,

                "name":
                    "Smart Fire Guard"

            },

            merge=True
        )


    return jsonify(
        success=True,
        message="Profile updated successfully."
    )


# ============================================================
# SAVE THIS PHONE'S FCM TOKEN
# ============================================================

@app.route(
    "/save-fcm-token",
    methods=["POST"]
)
def save_fcm_token():

    user = get_logged_in_user()

    if not user:

        return jsonify(
            success=False,
            message="Login required."
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
            message="FCM token is missing."
        ), 400


    # IMPORTANT:
    # The token is connected to the currently
    # authenticated Firebase user.
    db.collection(
        "fcm_tokens"
    ).document(
        token
    ).set(

        {

            "uid":
                user["uid"],

            "email":
                user.get(
                    "email",
                    ""
                )
        },

        merge=True
    )


    return jsonify(
        success=True,
        message=(
            "This phone is now registered "
            "for fire notifications."
        )
    )


# ============================================================
# STATUS
# ============================================================

fire_status = {}


def user_status(uid):

    if uid not in fire_status:

        fire_status[uid] = {

            "fire": False,

            "flame": "SAFE",

            "temperature": 0,

            "extinguisher": "OFF",

            "notification_sent": False
        }


    return fire_status[uid]


@app.route("/status")
def status():

    user = get_logged_in_user()

    if not user:

        return jsonify(
            success=False
        ), 401


    uid = user["uid"]

    current = user_status(uid)


    return jsonify(

        success=True,

        fire=current["fire"],

        flame=current["flame"],

        temperature=current["temperature"],

        extinguisher=
            current["extinguisher"],

        notification_sent=
            current["notification_sent"],

        registered_tokens=
            len(
                get_user_tokens(uid)
            )
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


    if not db:

        return jsonify(

            success=False,

            message=
                "Firebase is not configured."

        ), 500


    # Find which Firebase user owns this device.
    device = get_device(
        device_id
    )


    uid = device.get(
        "owner_id"
    )


    if not uid:

        return jsonify(

            success=False,

            message=
                "This ESP8266 device is not registered."

        ), 404


    fire = bool(
        data.get(
            "fire",
            False
        )
    )


    flame = data.get(
        "flame",
        "DETECTED"
    )


    temperature = data.get(
        "temperature",
        0
    )


    current = user_status(
        uid
    )


    current["temperature"] = (
        temperature
    )


    if fire:

        current["fire"] = True

        current["flame"] = (
            "DETECTED"
        )

        current["extinguisher"] = (
            "ACTIVATED"
        )


        # Send only once for this fire event.
        if not current[
            "notification_sent"
        ]:

            owner = get_user(
                uid
            )


            sent = send_fire_notification(

                uid,

                temperature,

                owner.get(
                    "location",
                    ""
                )
            )


            if sent:

                current[
                    "notification_sent"
                ] = True


        return jsonify(

            success=True,

            fire=True,

            message=(
                "Fire detected. "
                "Alert sent to the "
                "registered user's phone."
            )
        )


    # No fire.
    current["fire"] = False

    current["flame"] = flame

    current["extinguisher"] = "OFF"


    return jsonify(

        success=True,

        fire=False,

        message="System is safe."
    )


# ============================================================
# TEST FIRE FROM DASHBOARD
# ============================================================

@app.route(
    "/api/test-fire",
    methods=["POST"]
)
def test_fire():

    user = get_logged_in_user()

    if not user:

        return jsonify(
            success=False,
            message="Login required."
        ), 401


    uid = user["uid"]

    current = user_status(
        uid
    )


    current["fire"] = True

    current["flame"] = (
        "DETECTED"
    )

    current["temperature"] = 82

    current["extinguisher"] = (
        "ACTIVATED"
    )


    if not current[
        "notification_sent"
    ]:

        owner = get_user(
            uid
        )


        sent = send_fire_notification(

            uid,

            82,

            owner.get(
                "location",
                ""
            )
        )


        if sent:

            current[
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

    user = get_logged_in_user()

    if not user:

        return jsonify(
            success=False,
            message="Login required."
        ), 401


    uid = user["uid"]


    fire_status[uid] = {

        "fire": False,

        "flame": "SAFE",

        "temperature": 0,

        "extinguisher": "OFF",

        "notification_sent": False
    }


    return jsonify(

        success=True,

        message=
            "System reset successfully."
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    return jsonify(

        status="ok",

        firebase=
            bool(db)
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
