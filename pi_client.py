import time
import os
import threading
import requests
from ultralytics import YOLO
import RPi.GPIO as GPIO
from onvif import ONVIFCamera

# =========================
# CONFIG
# =========================
DEVICE_ID = "farm_001"
SERVER_URL = "https://iot-bbackend.onrender.com"

CAMERA_IP = "192.168.0.120"
PORT = 80
USERNAME = "onvifuser"
PASSWORD = "12345678"
WSDL_PATH = "/home/admin/monkey_detection/wsdl"

RTSP_URL = "rtsp://admin:Mysore%2A88@192.168.0.120:554/cam/realmonitor?channel=1&subtype=1"

MODEL_PATH = "best_ncnn_model"
MODEL_RUNTIME_SECONDS = 60
ALERT_RUNTIME_SECONDS = 30

RELAY_PIN = 18
SOUNDS_DIR = "/home/admin/monkey_detection/sounds"
current_sound = "alert.wav"

# Settings from backend
confidence_threshold = 0.5
auto_sound = True
push_alerts = True
volume = 100

# =========================
# GPIO
# =========================
GPIO.setmode(GPIO.BCM)
GPIO.setup(RELAY_PIN, GPIO.OUT)
GPIO.output(RELAY_PIN, GPIO.HIGH)

# =========================
# MODEL
# =========================
model = YOLO(MODEL_PATH)

# =========================
# SOUND CONTROL
# =========================
stop_sound_event = threading.Event()

# =========================
# FUNCTIONS
# =========================

def activate_alert():
    if not auto_sound:
        return

    file_path = os.path.join(SOUNDS_DIR, current_sound)
    if not os.path.exists(file_path):
        print("Sound file missing")
        return

    stop_sound_event.clear()
    GPIO.output(RELAY_PIN, GPIO.LOW)

    end_time = time.time() + ALERT_RUNTIME_SECONDS

    while time.time() < end_time and not stop_sound_event.is_set():
        os.system(f"amixer sset 'Master' {volume}%")
        os.system(f"aplay {file_path}")

    GPIO.output(RELAY_PIN, GPIO.HIGH)


def stop_alert():
    stop_sound_event.set()
    GPIO.output(RELAY_PIN, GPIO.HIGH)


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


def sync_settings():
    global confidence_threshold, auto_sound, push_alerts, volume

    try:
        r = requests.get(f"{SERVER_URL}/settings", timeout=5)
        data = r.json().get("settings", {})

        confidence_threshold = data.get("confidenceThreshold", 0.5)
        auto_sound = data.get("autoSound", True)
        push_alerts = data.get("pushAlerts", True)
        volume = data.get("volume", 100)

        print("Settings synced")

    except Exception:
        print("Settings sync failed")


def download_sound(filename):
    try:
        url = f"{SERVER_URL}/device/download/{filename}"
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            os.makedirs(SOUNDS_DIR, exist_ok=True)
            file_path = os.path.join(SOUNDS_DIR, filename)

            with open(file_path, "wb") as f:
                f.write(response.content)

            print(f"Downloaded {filename}")
        else:
            print("Sound download failed")

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

    except Exception:
        pass


def connect_camera():
    cam = ONVIFCamera(CAMERA_IP, PORT, USERNAME, PASSWORD, WSDL_PATH)
    events_service = cam.create_events_service()
    subscription = events_service.CreatePullPointSubscription()
    pullpoint = cam.create_pullpoint_service(
        subscription.SubscriptionReference.Address
    )
    return pullpoint


# =========================
# START
# =========================

pullpoint_service = connect_camera()
sync_settings()

print("System Running...")

while True:

    send_heartbeat()
    poll_commands()

    try:
        messages = pullpoint_service.PullMessages({
            "Timeout": "PT5S",
            "MessageLimit": 10
        })

        if messages.NotificationMessage:

            start_time = time.time()
            monkey_detected = False

            results = model.predict(
                source=RTSP_URL,
                stream=True,
                conf=confidence_threshold,
                imgsz=640,
                verbose=False
            )

            for r in results:

                if time.time() - start_time > MODEL_RUNTIME_SECONDS:
                    break

                for box in r.boxes:
                    class_name = model.names[int(box.cls[0])]
                    conf = float(box.conf[0])

                    if "monkey" in class_name.lower():

                        if not monkey_detected:
                            monkey_detected = True

                            threading.Thread(
                                target=activate_alert,
                                daemon=True
                            ).start()

                            send_detection(conf)

            print("Detection cycle finished")

    except Exception:
        time.sleep(3)
        pullpoint_service = connect_camera()

    time.sleep(5)
