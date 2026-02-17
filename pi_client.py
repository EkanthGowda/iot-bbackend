from onvif import ONVIFCamera
from ultralytics import YOLO
import time
import os
import threading
from urllib.parse import quote
import requests
import RPi.GPIO as GPIO

# ===============================
# CONFIG
# ===============================
DEVICE_ID = "farm_001"
SERVER_URL = "https://iot-bbackend.onrender.com"

CAMERA_IP = "192.168.0.114"
PORT = 80
USERNAME = "admin"
PASSWORD = "Mysore*88"
WSDL_PATH = "/home/admin/monkey_detection/wsdl"

# LOW QUALITY STREAM (less heat)
RTSP_URL = "rtsp://admin:Mysore%2A88@192.168.0.114:554/cam/realmonitor?channel=1&subtype=1"

MODEL_PATH = "best_ncnn_model"

MODEL_RUNTIME_SECONDS = 60
ALERT_RUNTIME_SECONDS = 20
MONKEY_ALERT_HITS = 3

SOUNDS_DIR = "/home/admin/monkey_detection/sounds"
current_sound = "alert.wav"

# Relay on Physical Pin 12 -> GPIO18
RELAY_PIN = 18
RELAY_ACTIVE_HIGH = False

# Motor relay on Physical Pin 11 -> GPIO17
MOTOR_PIN = 17
MOTOR_ACTIVE_HIGH = False  # Active-low: LOW = ON, HIGH = OFF
MOTOR_DEFAULT_STATE = "OFF"
motor_state = MOTOR_DEFAULT_STATE

# Settings from backend
confidence_threshold = 0.5
auto_sound = True
push_alerts = True
volume = 100

# ===============================
# GPIO SETUP
# ===============================
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(RELAY_PIN, GPIO.OUT)
GPIO.output(RELAY_PIN, GPIO.LOW if RELAY_ACTIVE_HIGH else GPIO.HIGH)

GPIO.setup(MOTOR_PIN, GPIO.OUT)
if MOTOR_DEFAULT_STATE == "ON":
    GPIO.output(MOTOR_PIN, GPIO.HIGH if MOTOR_ACTIVE_HIGH else GPIO.LOW)
else:
    GPIO.output(MOTOR_PIN, GPIO.LOW if MOTOR_ACTIVE_HIGH else GPIO.HIGH)

# ===============================
# SOUND CONTROL
# ===============================
stop_sound_event = threading.Event()


def set_sound_relay_state(is_on):
    if RELAY_ACTIVE_HIGH:
        GPIO.output(RELAY_PIN, GPIO.HIGH if is_on else GPIO.LOW)
    else:
        GPIO.output(RELAY_PIN, GPIO.LOW if is_on else GPIO.HIGH)

# ===============================
# ALERT FUNCTION
# ===============================
def activate_alert():
    if not auto_sound:
        return

    file_path = os.path.join(SOUNDS_DIR, current_sound)
    if not os.path.exists(file_path):
        print("Sound file missing")
        return

    stop_sound_event.clear()
    set_sound_relay_state(True)

    end_time = time.time() + ALERT_RUNTIME_SECONDS

    while time.time() < end_time and not stop_sound_event.is_set():
        os.system(f"amixer sset 'Master' {volume}%")
        os.system(f"aplay {file_path}")

    set_sound_relay_state(False)


def stop_alert():
    stop_sound_event.set()
    set_sound_relay_state(False)


def send_detection(conf):
    if not push_alerts:
        return

    try:
        requests.post(
            f"{SERVER_URL}/device/detection",
            json={
                "device_id": DEVICE_ID,
                "confidence": conf,
                "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            },
            timeout=5
        )
    except Exception:
        pass


def send_heartbeat():
    try:
        requests.post(
            f"{SERVER_URL}/device/heartbeat",
            json={"device_id": DEVICE_ID},
            timeout=5
        )
    except Exception:
        pass


def send_motor_state(state):
    try:
        requests.post(
            f"{SERVER_URL}/device/motor",
            json={"device_id": DEVICE_ID, "state": state},
            timeout=5
        )
    except Exception:
        pass


def set_motor_state(state):
    global motor_state
    if state not in ("ON", "OFF"):
        return

    if state == "ON":
        GPIO.output(MOTOR_PIN, GPIO.HIGH if MOTOR_ACTIVE_HIGH else GPIO.LOW)
        print(f"Motor turned ON (GPIO{MOTOR_PIN} = {'HIGH' if MOTOR_ACTIVE_HIGH else 'LOW'})")
    else:
        GPIO.output(MOTOR_PIN, GPIO.LOW if MOTOR_ACTIVE_HIGH else GPIO.HIGH)
        print(f"Motor turned OFF (GPIO{MOTOR_PIN} = {'HIGH' if not MOTOR_ACTIVE_HIGH else 'LOW'})")

    motor_state = state
    send_motor_state(state)
    print(f"Motor state updated and sent to backend: {state}")


def sync_settings():
    global confidence_threshold, auto_sound, push_alerts, volume, current_sound

    try:
        r = requests.get(f"{SERVER_URL}/settings", timeout=5)
        data = r.json().get("settings", {})

        confidence_threshold = data.get("confidenceThreshold", 0.5)
        auto_sound = data.get("autoSound", True)
        push_alerts = data.get("pushAlerts", True)
        volume = data.get("volume", 100)
        current_sound = data.get("defaultSound", "alert.wav")

        print("Settings synced")

    except Exception:
        print("Settings sync failed")


def download_sound(filename):
    try:
        safe_name = os.path.basename(filename)
        encoded_name = quote(safe_name)
        url = f"{SERVER_URL}/device/download/{encoded_name}"
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            os.makedirs(SOUNDS_DIR, exist_ok=True)
            file_path = os.path.join(SOUNDS_DIR, safe_name)

            with open(file_path, "wb") as f:
                f.write(response.content)

            print(f"Downloaded {safe_name}")
            send_sound_list()
        else:
            print(f"Sound download failed: HTTP {response.status_code}")

    except Exception:
        print("Sound download failed")


def poll_commands():
    global current_sound

    try:
        r = requests.get(
            f"{SERVER_URL}/device/command/{DEVICE_ID}",
            timeout=5
        )
        command = r.json().get("command")

        if command:
            print("Command:", command)

            if command == "PLAY_SOUND":
                threading.Thread(target=activate_alert, daemon=True).start()

            elif command == "STOP_SOUND":
                stop_alert()

            elif command == "SYNC_SETTINGS":
                sync_settings()

            elif command == "SET_VOLUME":
                sync_settings()

            elif command.startswith("UPLOAD_SOUND:"):
                filename = command.split(":", 1)[1]
                download_sound(filename)

            elif command.startswith("SET_SOUND:"):
                current_sound = command.split(":", 1)[1]

            elif command == "MOTOR_ON":
                set_motor_state("ON")

            elif command == "MOTOR_OFF":
                set_motor_state("OFF")

    except Exception:
        pass


def get_local_sounds():
    try:
        if not os.path.exists(SOUNDS_DIR):
            print(f"Sounds directory does not exist: {SOUNDS_DIR}")
            return []
        files = [
            f
            for f in os.listdir(SOUNDS_DIR)
            if os.path.isfile(os.path.join(SOUNDS_DIR, f))
        ]
        print(f"Found {len(files)} sound files in {SOUNDS_DIR}")
        return files
    except Exception as e:
        print(f"Error listing sounds: {e}")
        return []


def send_sound_list():
    try:
        sounds = get_local_sounds()
        print(f"Sending sound list to backend: {sounds}")
        response = requests.post(
            f"{SERVER_URL}/device/sounds",
            json={"device_id": DEVICE_ID, "sounds": sounds},
            timeout=5
        )
        if response.status_code == 200:
            print(f"Sound list synced successfully: {len(sounds)} files")
        else:
            print(f"Sound list sync failed: {response.status_code}")
    except Exception as e:
        print(f"Sound list sync error: {e}")


send_motor_state(MOTOR_DEFAULT_STATE)
send_sound_list()


# ===============================
# CONNECT CAMERA
# ===============================
def connect_camera():
    cam = ONVIFCamera(CAMERA_IP, PORT, USERNAME, PASSWORD, WSDL_PATH)
    events_service = cam.create_events_service()
    subscription = events_service.CreatePullPointSubscription()
    pullpoint = cam.create_pullpoint_service(
        subscription.SubscriptionReference.Address
    )
    return pullpoint


# ===============================
# MAIN
# ===============================
print("Loading YOLO model...")
model = YOLO(MODEL_PATH)

sync_settings()

print("Connecting to camera...")
pullpoint_service = None

print("Waiting for motion...")

last_heartbeat = 0
last_settings_sync = 0
last_sound_sync = 0

while True:
    now = time.time()

    # Periodic tasks
    if now - last_heartbeat >= 10:
        send_heartbeat()
        last_heartbeat = now

    if now - last_settings_sync >= 60:
        sync_settings()
        last_settings_sync = now

    if now - last_sound_sync >= 300:
        send_sound_list()
        last_sound_sync = now

    # Motor commands are polled independently
    poll_commands()

    # Connect to camera if not already connected
    if pullpoint_service is None:
        try:
            pullpoint_service = connect_camera()
            pullpoint_service.PullMessages({
                "Timeout": "PT1S",
                "MessageLimit": 50
            })
            print("Camera connected.")
        except Exception as exc:
            print(f"Camera connect failed: {exc}. Retrying...")
            time.sleep(3)
            continue

    # Check for motion events
    try:
        messages = pullpoint_service.PullMessages({
            "Timeout": "PT5S",
            "MessageLimit": 10
        })

        if messages.NotificationMessage:
            print("Motion detected -> Running AI for 60 sec")

            start_time = time.time()
            monkey_detected = False
            monkey_hit_count = 0

            results = model.predict(
                source=RTSP_URL,
                stream=True,
                conf=confidence_threshold,
                imgsz=640,
                verbose=False,
                task="detect"
            )

            for r in results:
                if time.time() - start_time > MODEL_RUNTIME_SECONDS:
                    break

                # Still poll motor commands during detection
                poll_commands()

                for box in r.boxes:
                    class_id = int(box.cls[0])
                    class_name = model.names[class_id]
                    confidence = float(box.conf[0])

                    print(f"Detected: {class_name} ({confidence:.2f})")

                    if "monkey" in class_name.lower():
                        if not monkey_detected:
                            monkey_hit_count += 1
                            print(f"Monkey detection hit {monkey_hit_count}/{MONKEY_ALERT_HITS}")

                            if monkey_hit_count >= MONKEY_ALERT_HITS:
                                monkey_detected = True
                                print("MONKEY DETECTED!")

                                threading.Thread(
                                    target=activate_alert,
                                    daemon=True
                                ).start()

                                send_detection(confidence)

            print("Detection stopped. Waiting for next motion...")

    except Exception as exc:
        print(f"Connection lost: {exc}. Reconnecting...")
        time.sleep(3)
        pullpoint_service = None

    time.sleep(1)
