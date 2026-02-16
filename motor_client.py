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
            f"{SERVER_URL}/device/motor",
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
            f"{SERVER_URL}/device/command/{DEVICE_ID}",
            timeout=5
        )
        if response.status_code != 200:
            print(f"Poll failed: HTTP {response.status_code} -> {response.text}")
            return

        try:
            payload = response.json()
        except ValueError:
            print(f"Poll failed: Non-JSON response -> {response.text}")
            return

        command = payload.get("command")
        if command:
            print(f"Command received: {command}")
            if command == "MOTOR_ON":
                set_motor_state("ON")
            elif command == "MOTOR_OFF":
                set_motor_state("OFF")
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
