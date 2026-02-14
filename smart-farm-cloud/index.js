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
let commandQueue = {};
let motorState = "OFF";

app.get("/", (req, res) => {
  res.send("Smart Farm Cloud Running");
});

// Pi sends detection
app.post("/device/detection", (req, res) => {
  latestDetection = req.body;
  console.log("Detection:", req.body);
  res.json({ status: "received" });
});

// App fetches latest detection
app.get("/app/latest", (req, res) => {
  res.json(latestDetection);
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
  res.json(files);
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
  commandQueue[id] = null;
  res.json({ command });
});

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => console.log("Server running on port", PORT));
