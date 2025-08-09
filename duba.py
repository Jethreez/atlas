import cv2
import numpy as np

#renk algilayarak calisiyor.

cap = cv2.VideoCapture(0)  # 0 dahili, 1 harici webcam

if not cap.isOpened():
    print("Kamera açılamadı!")
    exit()

while True:
    ret, frame = cap.read()
    if not ret:
        print("Kare alınamadı!")
        break

    # Görüntüyü HSV renk uzayına çevir
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # Turuncu/Kırmızı aralığı (duba rengi için yaklaşık)
    lower_orange = np.array([5, 100, 100])
    upper_orange = np.array([20, 255, 255])

    # Maske oluştur
    mask = cv2.inRange(hsv, lower_orange, upper_orange)

    # Gürültü temizleme (morfolojik işlemler)
    kernel = np.ones((5,5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_DILATE, kernel)

    # Kontur bulma
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > 500:  # Küçük nesneleri ele
            x, y, w, h = cv2.boundingRect(cnt)
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
            cv2.putText(frame, "Duba", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 
                        0.6, (0, 255, 0), 2)

    # Görüntüleri göster
    cv2.imshow("Kamera", frame)
    cv2.imshow("Maske", mask)

    # q tuşu ile çıkış
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
