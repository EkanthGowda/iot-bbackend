const express = require("express");
const cors = require("cors");
const multer = require("multer");
const fs = require("fs");
const path = require("path");

const uploadDir = "uploads";

if (!fs.existsSync(uploadDir)) {
  fs.mkdirSync(uploadDir);
}

const storage = multer.diskStorage({
  destination: uploadDir,
  filename: (req, file, cb) => {
    cb(null, file.originalname);
  }
});

const upload = multer({ storage });

const app = express();
app.use(cors());
app.use(express.json());

let latestDetection = null;
let alerts = [];
let commandQueue = {};
let deviceStatus = {};
let motorState = "OFF";
let deviceSounds = {};
let settings = {
  confidenceThreshold: 0.5,
  autoSound: true,
  pushAlerts: true,
  volume: 70,
  defaultSound: "alert.wav"
};

app.get("/", (req, res) => {
  res.send("Smart Farm Cloud Running");
});

// Pi sends detection
app.post("/device/detection", (req, res) => {
  latestDetection = req.body;
  const confidence =
    typeof req.body?.confidence === "number" ? req.body.confidence : 0.5;
  const time = req.body?.time || new Date().toISOString();

  alerts.unshift({
    id: String(Date.now()),
    time,
    confidence
  });

  if (alerts.length > 50) {
    alerts.pop();
  }

  console.log("Detection:", req.body);
  res.json({ status: "received" });
});

// Pi heartbeat
app.post("/device/heartbeat", (req, res) => {
  const { device_id } = req.body;
  deviceStatus[device_id] = {
    online: true,
    lastSeen: Date.now()
  };
  res.json({ status: "alive" });
});

// Pi reports motor state
app.post("/device/motor", (req, res) => {
  const { device_id, state } = req.body;

  if (state === "ON" || state === "OFF") {
    motorState = state;
    if (device_id) {
      deviceStatus[device_id] = {
        ...(deviceStatus[device_id] || {}),
        lastSeen: Date.now()
      };
    }
    res.json({ status: "motor state updated", state: motorState });
  } else {
    res.status(400).json({ error: "Invalid state" });
  }
});

// App fetches latest detection
app.get("/app/latest", (req, res) => {
  res.json(latestDetection);
});

// Alerts list for the app
app.get("/alerts", (req, res) => {
  res.json({ alerts });
});

// App checks device status
app.get("/app/status/:id", (req, res) => {
  const id = req.params.id;
  res.json(deviceStatus[id] || { online: false });
});

// App settings
app.get("/settings", (req, res) => {
  res.json({ settings });
});

app.put("/settings", (req, res) => {
  const { confidenceThreshold, autoSound, pushAlerts, volume, defaultSound } = req.body;

  if (typeof confidenceThreshold === "number") {
    settings.confidenceThreshold = confidenceThreshold;
  }

  if (typeof autoSound === "boolean") {
    settings.autoSound = autoSound;
  }

  if (typeof pushAlerts === "boolean") {
    settings.pushAlerts = pushAlerts;
  }

  if (typeof volume === "number") {
    settings.volume = volume;
  }

  if (typeof defaultSound === "string") {
    settings.defaultSound = defaultSound;
  }

  commandQueue["farm_001"] = "SYNC_SETTINGS";

  res.json({ status: "updated", settings });
});

// App sends command
app.post("/app/command", (req, res) => {
  const { device_id, action } = req.body;
  commandQueue[device_id] = action;
  res.json({ status: "queued" });
});

// App sends motor control
app.post("/app/motor", (req, res) => {
  const { device_id, action } = req.body;

  if (action === "ON" || action === "OFF") {
    motorState = action;
    commandQueue[device_id] = `MOTOR_${action}`;
    console.log(`[MOTOR] Queued command for ${device_id}: MOTOR_${action}`);
    res.json({ status: "motor command queued", state: motorState });
  } else {
    res.status(400).json({ error: "Invalid action" });
  }
});

// App fetch motor state
app.get("/app/motor", (req, res) => {
  res.json({ motorState });
});

// Upload Sound From App
app.post("/app/upload-sound", upload.single("file"), (req, res) => {
  res.json({ status: "uploaded", file: req.file.filename });
});

// List Available Sounds
app.get("/app/sounds", (req, res) => {
  const files = fs.readdirSync(uploadDir);
  const deviceId = req.query.device_id || "farm_001";
  console.log(`[SOUNDS] Request from app - Uploads: ${files.length}, Device: ${(deviceSounds[deviceId] || []).length}`);
  res.json({
    uploads: files,
    device: deviceSounds[deviceId] || []
  });
});

// Pi sends local sound list
app.post("/device/sounds", (req, res) => {
  const { device_id, sounds } = req.body;
  if (!device_id || !Array.isArray(sounds)) {
    return res.status(400).json({ error: "Invalid payload" });
  }
  deviceSounds[device_id] = sounds;
  console.log(`[SOUNDS] Synced ${sounds.length} sounds from ${device_id}:`, sounds);
  res.json({ status: "sounds synced", count: sounds.length });
});

// Pi Downloads Sound
app.get("/device/download/:filename", (req, res) => {
  const filePath = path.join(uploadDir, req.params.filename);
  res.download(filePath);
});

// Pi polls for command
app.get("/device/command/:id", (req, res) => {
  const id = req.params.id;
  const command = commandQueue[id] || null;
  if (command) {
    console.log(`[CMD] Sending command to ${id}: ${command}`);
  }
  commandQueue[id] = null;
  res.json({ command });
});

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => console.log("Server running on port", PORT));
