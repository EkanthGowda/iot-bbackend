import time
import requests
import RPi.GPIO as GPIO

# ===============================
# MOTOR ONLY CONFIG
# ===============================
DEVICE_ID = "farm_001"
SERVER_URL = "https://iot-bbackend.onrender.com"

MOTOR_PIN = 17  # Physical pin 11 -> GPIO17
MOTOR_ACTIVE_LOW = True  # Active-low: LOW = ON, HIGH = OFF
POLL_INTERVAL_SECONDS = 1

# ===============================
# GPIO SETUP
# ===============================
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(MOTOR_PIN, GPIO.OUT)
GPIO.output(MOTOR_PIN, GPIO.HIGH if MOTOR_ACTIVE_LOW else GPIO.LOW)


def send_state(state):
    try:
        requests.post(
            f"{SERVER_URL}/motor/state",
            json={"device_id": DEVICE_ID, "state": state},
            timeout=5
        )
    except Exception as exc:
        print(f"State update failed: {exc}")


def set_motor_state(state):
    if state not in ("ON", "OFF"):
        return

    if state == "ON":
        GPIO.output(MOTOR_PIN, GPIO.LOW if MOTOR_ACTIVE_LOW else GPIO.HIGH)
    else:
        GPIO.output(MOTOR_PIN, GPIO.HIGH if MOTOR_ACTIVE_LOW else GPIO.LOW)

    print(f"Motor set to {state}")
    send_state(state)


def poll_command():
    try:
        response = requests.get(
            f"{SERVER_URL}/motor/poll/{DEVICE_ID}",
            timeout=5
        )
        action = response.json().get("action")
        if action:
            print(f"Command received: {action}")
            set_motor_state(action)
    except Exception as exc:
        print(f"Poll failed: {exc}")


send_state("OFF")
print("Motor client started. Waiting for commands...")

try:
    while True:
        poll_command()
        time.sleep(POLL_INTERVAL_SECONDS)
except KeyboardInterrupt:
    GPIO.cleanup()
    print("Motor client stopped.")
