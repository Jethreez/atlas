import cv2
from ultralytics import YOLO

model = YOLO("duba.pt")

cap = cv2.VideoCapture(0) #harici kamera icin 1
if not cap.isOpened():
    print("kamera yok")
    exit()

while True:
    ret, frame = cap.read()
    if not ret:
        break

    h, w = frame.shape[:2]

    results = model.predict(frame, conf=0.5, verbose=False)

    cone_count = 0

    for r in results:
        boxes = r.boxes
        for i in range(len(boxes)):
            xyxy = boxes.xyxy[i].cpu().numpy()
            cls_id = int(boxes.cls[i].cpu().numpy())

            label = model.names[cls_id].lower().replace("-", "").replace(" ", "")
            if label == "trafficcone":
                cone_count += 1

                x1, y1, x2, y2 = map(int, xyxy)
                obj_h = y2 - y1
                cx = x1 + (x2 - x1) // 2

                distance_m = 1000 / obj_h
                offset_x = cx - (w / 2)
                angle_deg = (offset_x / (w / 2)) * 30

                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, "Duba", (x1, y1 - 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                cv2.putText(frame, f"Yon = {angle_deg:.1f} deg", (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                cv2.putText(frame, f"Uzaklik = {distance_m:.2f} m", (x1, y2 + 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

    cv2.putText(frame, f"Duba Sayisi = {cone_count}", (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    cv2.putText(frame, "Cikmak icin Q'ya basin", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

    cv2.imshow("YOLO Duba Tespiti", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
