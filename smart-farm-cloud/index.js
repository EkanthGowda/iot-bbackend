const express = require("express");
const cors = require("cors");

const app = express();
app.use(cors());
app.use(express.json());

let latestDetection = null;
let commandQueue = {};

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

// Pi polls for command
app.get("/device/command/:id", (req, res) => {
  const id = req.params.id;
  const command = commandQueue[id] || null;
  commandQueue[id] = null;
  res.json({ command });
});

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => console.log("Server running on port", PORT));
