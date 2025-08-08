#include <WiFi.h>
#include <WebServer.h>
#include <ESP32Servo.h>

// WiFi bilgileri
const char* ssid = "tameresp";
const char* password = "tameresp";

// Servo motor tanımlamaları
Servo panServo;  // Yatay hareket
Servo tiltServo; // Dikey hareket

// Pin tanımlamaları
const int PAN_PIN = 18;
const int TILT_PIN = 17;

// Servo pozisyonları (0-180 derece)
int panPosition = 90;   // Merkez pozisyon
int tiltPosition = 150;  // Merkez pozisyon

// Web server
WebServer server(80);

void setup() {
  Serial.begin(115200);
  
  // Servo motorları başlat
  panServo.attach(PAN_PIN);
  tiltServo.attach(TILT_PIN);
  
  // Başlangıç pozisyonu (merkez)
  panServo.write(panPosition);
  tiltServo.write(tiltPosition);
  
  // WiFi bağlantısı
  WiFi.begin(ssid, password);
  Serial.print("WiFi'ye bağlanıyor");
  
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  
  Serial.println();
  Serial.println("WiFi bağlandı!");
  Serial.print("IP adresi: ");
  Serial.println(WiFi.localIP());
  
  // Web server rotaları
  server.on("/", handleRoot);
  server.on("/control", HTTP_POST, handleControl);
  server.on("/move", HTTP_GET, handleMove);
  server.on("/center", HTTP_GET, handleCenter);
  server.on("/status", HTTP_GET, handleStatus);
  
  server.begin();
  Serial.println("Web server başlatıldı");
}

void loop() {
  server.handleClient();
}

// Ana sayfa
void handleRoot() {
  String html = "<!DOCTYPE html><html><head><title>Pan-Tilt Kamera Kontrolu</title>";
  html += "<style>body{font-family:Arial;text-align:center;margin:50px;}";
  html += ".control-panel{margin:20px;}button{padding:10px 20px;margin:5px;font-size:16px;}";
  html += ".position{font-size:18px;margin:20px;}</style></head><body>";
  html += "<h1>Pan-Tilt Kamera Kontrolu</h1>";
  html += "<div class='position'><p>Pan: <span id='panPos'>90</span> derece | Tilt: <span id='tiltPos'>90</span> derece</p></div>";
  html += "<div class='control-panel'>";
  html += "<button onclick='moveCamera(\"up\")'>YUKARI</button><br>";
  html += "<button onclick='moveCamera(\"left\")'>SOL</button>";
  html += "<button onclick='moveCamera(\"center\")'>MERKEZ</button>";
  html += "<button onclick='moveCamera(\"right\")'>SAG</button><br>";
  html += "<button onclick='moveCamera(\"down\")'>ASAGI</button>";
  html += "</div><script>";
  html += "function moveCamera(direction){";
  html += "fetch('/move?dir='+direction).then(response=>response.json()).then(data=>{";
  html += "document.getElementById('panPos').textContent=data.pan;";
  html += "document.getElementById('tiltPos').textContent=data.tilt;});} ";
  html += "function updatePosition(){";
  html += "fetch('/status').then(response=>response.json()).then(data=>{";
  html += "document.getElementById('panPos').textContent=data.pan;";
  html += "document.getElementById('tiltPos').textContent=data.tilt;});} ";
  html += "setInterval(updatePosition,1000);</script></body></html>";
  
  server.send(200, "text/html", html);
}

// Hareket kontrolü
void handleMove() {
  String direction = server.arg("dir");
  int stepSize = 10; // Her harekette kaç derece
  
  if (direction == "left") {
    panPosition = constrain(panPosition - stepSize, 0, 180);
    panServo.write(panPosition);
  }
  else if (direction == "right") {
    panPosition = constrain(panPosition + stepSize, 0, 180);
    panServo.write(panPosition);
  }
  else if (direction == "up") {
    tiltPosition = constrain(tiltPosition + stepSize, 0, 180);
    tiltServo.write(tiltPosition);
  }
  else if (direction == "down") {
    tiltPosition = constrain(tiltPosition - stepSize, 0, 180);
    tiltServo.write(tiltPosition);
  }
  else if (direction == "center") {
    panPosition = 90;
    tiltPosition = 90;
    panServo.write(panPosition);
    tiltServo.write(tiltPosition);
  }
  
  // JSON yanıt
  String response = "{\"pan\":" + String(panPosition) + ",\"tilt\":" + String(tiltPosition) + "}";
  server.send(200, "application/json", response);
  
  Serial.println("Hareket: " + direction + " | Pan: " + String(panPosition) + " derece | Tilt: " + String(tiltPosition) + " derece");
}

// Merkeze alma
void handleCenter() {
  panPosition = 90;
  tiltPosition = 90;
  panServo.write(panPosition);
  tiltServo.write(tiltPosition);
  
  String response = "{\"pan\":" + String(panPosition) + ",\"tilt\":" + String(tiltPosition) + "}";
  server.send(200, "application/json", response);
}

// Pozisyon kontrolü (PC'den görüntü işleme için)
void handleControl() {
  if (server.hasArg("pan") && server.hasArg("tilt")) {
    int newPan = server.arg("pan").toInt();
    int newTilt = server.arg("tilt").toInt();
    
    // Güvenli aralıkta tut
    panPosition = constrain(newPan, 0, 180);
    tiltPosition = constrain(newTilt, 0, 180);
    
    panServo.write(panPosition);
    tiltServo.write(tiltPosition);
    
    String response = "{\"status\":\"ok\",\"pan\":" + String(panPosition) + ",\"tilt\":" + String(tiltPosition) + "}";
    server.send(200, "application/json", response);
    
    Serial.println("Pozisyon guncellendi - Pan: " + String(panPosition) + " derece | Tilt: " + String(tiltPosition) + " derece");
  } else {
    server.send(400, "application/json", "{\"error\":\"Missing parameters\"}");
  }
}

// Durum bilgisi
void handleStatus() {
  String response = "{\"pan\":" + String(panPosition) + ",\"tilt\":" + String(tiltPosition) + "}";
  server.send(200, "application/json", response);
}