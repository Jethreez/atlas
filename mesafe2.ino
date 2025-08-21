#define SENSOR_COUNT 3

//      
//        \ 1 /     \ 2 /    \ 3 / 
//         \ /       \ /      \ /
//      +------------------------+
//      |                        |      1:sol ön
//      |                        |      2:orta
//      |                        |      3:sağ ön
//      |                        |      4:sol arka
//      |          araç          |      5:sağ arka
//      |                        |
//    4>|                        |<5
//      |                        |
//      |                        |
//      +------------------------+
//
//     
//     HCSR04
//
//
//

int trigPins[SENSOR_COUNT] = {2, 4, 6};
int echoPins[SENSOR_COUNT] = {3, 5, 7};

long sure[SENSOR_COUNT];
int mesafe[SENSOR_COUNT];

String yonler[3] = {"sol","duz","sag"};

int sol_aci = 15; // sağ ve sol ön sensörlerin açısı
int sag_aci = -(sol_aci); //acilara sonra bakacagim

void setup() {
  Serial.begin(9600);
  for (int i = 0; i < SENSOR_COUNT; i++) {
    pinMode(trigPins[i], OUTPUT);
    pinMode(echoPins[i], INPUT);
  }
}

int sensorOku(int trigPin, int echoPin) {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);

  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  long sure = pulseIn(echoPin, HIGH);
  int mesafe = sure * 0.034 / 2;

  return mesafe;
}

int yonAl() {
  int maxIndex = 0;  // en uzak sensörün indexi
  int maxValue = mesafe[0]; // başlangıç değeri (sensör 1)

  // 1,2,3 sensörlerini kontrol et (array index 0,1,2)
  for (int i = 0; i < 3; i++) {
    if (mesafe[i] > maxValue) {
      maxValue = mesafe[i];
      maxIndex = i;
    }
  }

  return maxIndex; // sensör numarası (1–3)
}

void loop() {
  Serial.print("\n\n");
  for (int i = 0; i < SENSOR_COUNT; i++) {
    mesafe[i] = sensorOku(trigPins[i], echoPins[i]);

    Serial.print("Sensor ");
    Serial.print(i + 1); 
    Serial.print(": ");
    Serial.print(mesafe[i]);
    Serial.println(" cm");
  }
    Serial.print("ideal yon: ");
    Serial.println(yonler[yonAl()]);


  
  delay(400);
}

