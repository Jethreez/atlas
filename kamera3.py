from ultralytics import YOLO
import cv2
import numpy as np
import requests
import threading
import time
import json
model = YOLO("yolo11n-seg.pt")

class PanTiltController:
    def __init__(self, esp32_ip="192.168.43.185"):  # ESP32'nizin IP adresini buraya yazın
        self.esp32_ip = esp32_ip
        self.camera = None
        self.running = False
        self.click_mode = True  # Tıklama modunda başla
        self.face_tracking = False  # Yüz takibi modu
        self.target_x = None
        self.target_y = None
        
        # Kamera çözünürlüğü
        self.frame_width = 1280
        self.frame_height = 720
        
        # Zoom kontrol parametreleri
        self.zoom_level = 1.0  # 1.0 = normal, >1.0 = zoom in
        self.zoom_min = 1.0
        self.zoom_max = 5.0
        self.zoom_step = 0.2
        
        # Yüz tanıma için cascade classifier
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        
        # Yüz takibi için kontrol parametreleri - YAVASLATILDI
        self.last_face_move_time = 0
        self.face_move_interval = 0.3  # Minimum 300ms bekle her hareket arasında
        self.face_dead_zone = 80  # Merkez bölgede bu kadar piksel tolerans
        
        # Otomatik zoom ve boyut kontrolü
        self.target_face_width = 200  # İdeal yüz genişliği (piksel)
        self.min_face_width = 80      # Bu boyuttan küçükse zoom at
        self.max_face_width = 400     # Bu boyuttan büyükse zoom out
        self.auto_zoom_enabled = True  # Otomatik zoom aktif/pasif
        self.last_auto_zoom_time = 0
        self.auto_zoom_interval = 1.0  # 1 saniye ara ile zoom ayarı
        
        # Kayıp hedef takip sistemi
        self.last_face_detection_time = time.time()
        self.no_face_timeout = 5.0  # 5 saniye hedef göremezse merkeze dön
        self.lost_target_recovery = False
        
        # Servo sınırları (güvenlik için)
        self.pan_min = 30   # Sol limit
        self.pan_max = 290  # Sağ limit  
        self.tilt_min = 45  # Alt limit (fazla geriye gitmesin)
        self.tilt_max = 240 # Üst limit

    def auto_adjust_zoom(self, face_width):
        """Yüz boyutuna göre otomatik zoom ayarı"""
        if not self.auto_zoom_enabled:
            return
        
        current_time = time.time()
        if (current_time - self.last_auto_zoom_time) < self.auto_zoom_interval:
            return  # Çok sık zoom ayarı yapma
        
        zoom_changed = False
        
        # Yüz çok küçükse zoom in
        if face_width < self.min_face_width and self.zoom_level < self.zoom_max:
            self.zoom_level = min(self.zoom_max, self.zoom_level + 0.1)
            zoom_changed = True
            print(f"🔍 Hedef küçük, zoom in: {self.zoom_level:.1f}x (yüz genişlik: {face_width}px)")
        
        # Yüz çok büyükse zoom out
        elif face_width > self.max_face_width and self.zoom_level > self.zoom_min:
            self.zoom_level = max(self.zoom_min, self.zoom_level - 0.1)
            zoom_changed = True
            print(f"🔍 Hedef büyük, zoom out: {self.zoom_level:.1f}x (yüz genişlik: {face_width}px)")
        
        if zoom_changed:
            self.last_auto_zoom_time = current_time
            # Zoom değiştiğinde dead zone'u da güncelle
            self.update_dead_zone()

    def update_dead_zone(self):
        """Zoom seviyesine göre dead zone'u güncelle"""
        # Zoom arttıkça dead zone küçülsün (daha hassas olsun)
        base_dead_zone = 80
        self.face_dead_zone = int(base_dead_zone / self.zoom_level)
        # Minimum 20 piksel olsun
        self.face_dead_zone = max(20, self.face_dead_zone)
        
    def initialize_camera(self, camera_index=0):
        """Kamerayı başlat"""
        self.camera = cv2.VideoCapture(camera_index)
        if not self.camera.isOpened():
            print(f"Kamera {camera_index} açılamadı!")
            return False
            
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_width)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_height)
        
        # Zoom desteği için kamera özelliklerini kontrol et
        try:
            self.camera.set(cv2.CAP_PROP_ZOOM, 1.0)
            print("Kamera zoom desteği aktif")
        except:
            print("Kamera donanımsal zoom desteklemiyor, yazılımsal zoom kullanılacak")
        
        print("Kamera başlatıldı")
        return True
    
    def apply_zoom(self, frame):
        """Zoom uygula (yazılımsal)"""
        if self.zoom_level <= 1.0:
            return frame
        
        h, w = frame.shape[:2]
        
        # Yeni boyutları hesapla
        new_w = int(w / self.zoom_level)
        new_h = int(h / self.zoom_level)
        
        # Merkezi kırp
        start_x = (w - new_w) // 2
        start_y = (h - new_h) // 2
        
        # Kırp ve boyutlandır
        cropped = frame[start_y:start_y + new_h, start_x:start_x + new_w]
        zoomed = cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)
        
        return zoomed
    
    def send_servo_command(self, pan=None, tilt=None):
        """ESP32'ye servo komutları gönder"""
        try:
            if pan is not None and tilt is not None:
                # Direkt pozisyon gönder
                url = f"http://{self.esp32_ip}/control"
                data = {"pan": pan, "tilt": tilt}
                response = requests.post(url, data=data, timeout=2)
            else:
                # Durum bilgisi al
                url = f"http://{self.esp32_ip}/status"
                response = requests.get(url, timeout=2)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"ESP32 yanıt hatası: {response.status_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"ESP32 bağlantı hatası: {e}")
            return None
    
    def calculate_servo_position(self, x, y, is_face_tracking=False):
        """Tıklanan koordinatları servo pozisyonlarına çevir - YAVASLATILDI + Dinamik hız"""
        # Kamera merkezini hesapla
        center_x = self.frame_width // 2
        center_y = self.frame_height // 2
        
        # Mevcut servo pozisyonlarını al
        status = self.send_servo_command()
        if not status:
            return 90, 90  # Varsayılan merkez pozisyon
        
        current_pan = status.get('pan', 90)
        current_tilt = status.get('tilt', 90)
        
        # Koordinat farkını hesapla (eksenleri ters çevir)
        diff_x = center_x - x  # X eksenini ters çevir (sol-sağ)
        diff_y = y - center_y  # Y eksenini ters çevir (yukarı-aşağı)
        
        # Zoom seviyesine göre dinamik hız ayarı
        zoom_speed_factor = 1.0 / self.zoom_level  # Zoom arttıkça hız azalır
        
        # Hassasiyet ayarları - YARILANDI + ZOOMa göre ayarlandı
        if is_face_tracking:
            # Yüz takibi için çok daha yavaş hareket + zoom faktörü
            base_pan_sensitivity = 0.04   # Temel hız
            base_tilt_sensitivity = 0.02  # Temel hız
            pan_sensitivity = base_pan_sensitivity * zoom_speed_factor
            tilt_sensitivity = base_tilt_sensitivity * zoom_speed_factor
        else:
            # Normal tıklama için daha yavaş + zoom faktörü
            base_pan_sensitivity = 0.15   # Temel hız
            base_tilt_sensitivity = 0.15  # Temel hız
            pan_sensitivity = base_pan_sensitivity * zoom_speed_factor
            tilt_sensitivity = base_tilt_sensitivity * zoom_speed_factor
        
        # Yeni pozisyonları hesapla
        new_pan = current_pan + (diff_x * pan_sensitivity)
        new_tilt = current_tilt + (diff_y * tilt_sensitivity)
        
        # Servo sınırlarını uygula
        new_pan = max(self.pan_min, min(self.pan_max, new_pan))
        new_tilt = max(self.tilt_min, min(self.tilt_max, new_tilt))
        
        return int(new_pan), int(new_tilt)
    
    def mouse_callback(self, event, x, y, flags, param):
        """Fare tıklama olayları"""
        if event == cv2.EVENT_LBUTTONDOWN and self.click_mode:
            print(f"Tıklanan nokta: ({x}, {y})")
            pan, tilt = self.calculate_servo_position(x, y, is_face_tracking=False)
            print(f"Servo pozisyonları - Pan: {pan}, Tilt: {tilt}")
            self.send_servo_command(pan, tilt)
            
            # Hedef noktayı göster
            self.target_x = x
            self.target_y = y
    
    def detect_and_track_faces(self, frame):
        """Yüz tanıma ve takip - Kayıp hedef kurtarma + Otomatik zoom sistemi eklendi"""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)
        
        current_time = time.time()
        
        if len(faces) > 0:
            # Hedef bulundu, zamanı güncelle
            self.last_face_detection_time = current_time
            self.lost_target_recovery = False
            
            # En büyük yüzü seç (en yakın olduğunu varsayıyoruz)
            largest_face = max(faces, key=lambda f: f[2] * f[3])
            x, y, w, h = largest_face
            
            # Yüzün merkez noktası
            face_center_x = x + w // 2
            face_center_y = y + h // 2
            
            # Otomatik zoom ayarı
            self.auto_adjust_zoom(w)
            
            # Yüzü çerçevele - Renk boyuta göre değişsin
            if w < self.min_face_width:
                color = (0, 0, 255)  # Kırmızı - çok küçük
            elif w > self.max_face_width:
                color = (255, 0, 255)  # Magenta - çok büyük
            else:
                color = (255, 0, 0)  # Mavi - ideal boyut
                
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            cv2.circle(frame, (face_center_x, face_center_y), 5, (0, 255, 0), -1)
            
            # Boyut bilgisini göster
            cv2.putText(frame, f"Boyut: {w}x{h}", (x, y-10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            
            # Kamera merkezinden uzaklık
            center_x = self.frame_width // 2
            center_y = self.frame_height // 2
            
            distance_x = abs(face_center_x - center_x)
            distance_y = abs(face_center_y - center_y)
            
            # Dead zone kontrolü ve zaman sınırlaması
            should_move = (
                (distance_x > self.face_dead_zone or distance_y > self.face_dead_zone) and
                (current_time - self.last_face_move_time) > self.face_move_interval
            )
            
            if should_move:
                pan, tilt = self.calculate_servo_position(face_center_x, face_center_y, is_face_tracking=True)
                
                # Debug bilgileri
                print(f"Yüz merkezi: ({face_center_x}, {face_center_y}) | "
                      f"Boyut: {w}x{h} | Uzaklık: X={distance_x}, Y={distance_y} | "
                      f"Servo: Pan={pan}, Tilt={tilt} | Zoom: {self.zoom_level:.1f}x")
                
                self.send_servo_command(pan, tilt)
                self.last_face_move_time = current_time
            
            # Dead zone'u görselleştir - Zoom seviyesine göre
            cv2.rectangle(frame, 
                         (center_x - self.face_dead_zone, center_y - self.face_dead_zone),
                         (center_x + self.face_dead_zone, center_y + self.face_dead_zone),
                         (0, 255, 255), 1)
            
            # Sarı kare ve mavi kare orantı kontrolü
            dead_zone_area = (2 * self.face_dead_zone) ** 2
            face_area = w * h
            ratio = face_area / dead_zone_area if dead_zone_area > 0 else 0
            
            # Orantı bilgisini göster
            ratio_color = (0, 255, 0) if 0.1 <= ratio <= 2.0 else (0, 0, 255)
            cv2.putText(frame, f"Oran: {ratio:.2f}", (center_x + self.face_dead_zone + 10, center_y), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, ratio_color, 1)
            
        else:
            # Hedef bulunamadı
            time_since_last_face = current_time - self.last_face_detection_time
            
            if time_since_last_face > self.no_face_timeout and not self.lost_target_recovery:
                # 5 saniyedir hedef görülmüyor, merkeze dön
                print(f"⚠️ {self.no_face_timeout} saniyedir hedef bulunamadı! Merkeze dönülüyor...")
                self.center_camera()
                self.zoom_level = 1.0  # Zoom'u sıfırla
                self.update_dead_zone()  # Dead zone'u güncelle
                self.lost_target_recovery = True
                
            # Geri sayımı göster
            if time_since_last_face < self.no_face_timeout:
                remaining_time = self.no_face_timeout - time_since_last_face
                cv2.putText(frame, f"Hedef aranıyor... {remaining_time:.1f}s", 
                           (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            else:
                cv2.putText(frame, "HEDEF KAYBOLDU - MERKEZE DÖNÜYOR", 
                           (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        
        return frame
    
    def draw_interface(self, frame):
        """Arayüz çiz - Gelişmiş bilgiler eklendi"""
        # Merkez çizgisi
        center_x = self.frame_width // 2
        center_y = self.frame_height // 2
        cv2.line(frame, (center_x - 20, center_y), (center_x + 20, center_y), (0, 255, 0), 2)
        cv2.line(frame, (center_x, center_y - 20), (center_x, center_y + 20), (0, 255, 0), 2)
        
        # Hedef noktası (tıklandıysa)
        if self.target_x is not None and self.target_y is not None:
            cv2.circle(frame, (self.target_x, self.target_y), 10, (0, 0, 255), 2)
        
        # Durum bilgisi
        mode_text = "Tıklama Modu" if self.click_mode else "Yüz Takip Modu"
        cv2.putText(frame, mode_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Zoom bilgisi - Dinamik hız gösterimi
        zoom_speed_factor = 1.0 / self.zoom_level
        zoom_text = f"Zoom: {self.zoom_level:.1f}x (Hız: {zoom_speed_factor:.1f}x)"
        cv2.putText(frame, zoom_text, (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        
        # Auto-zoom durumu
        auto_zoom_text = f"Auto-Zoom: {'AÇIK' if self.auto_zoom_enabled else 'KAPALI'}"
        auto_zoom_color = (0, 255, 0) if self.auto_zoom_enabled else (0, 0, 255)
        cv2.putText(frame, auto_zoom_text, (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.5, auto_zoom_color, 1)
        
        # Hedef boyut bilgileri
        cv2.putText(frame, f"İdeal boyut: {self.target_face_width}px", (10, 100), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
        cv2.putText(frame, f"Min: {self.min_face_width}px, Max: {self.max_face_width}px", 
                   (10, 115), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        
        # Dead zone boyutu
        cv2.putText(frame, f"Dead Zone: {self.face_dead_zone}px", (10, 130), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
        
        # Kontroller
        controls_start_y = frame.shape[0] - 170
        cv2.putText(frame, "Kontroller:", (10, controls_start_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, "SPACE: Mod Degistir", (10, controls_start_y + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        cv2.putText(frame, "C: Merkez", (10, controls_start_y + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        cv2.putText(frame, "+ / -: Manuel Zoom", (10, controls_start_y + 45), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
        cv2.putText(frame, "R: Zoom Reset", (10, controls_start_y + 60), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
        cv2.putText(frame, "A: Auto-Zoom Aç/Kapa", (10, controls_start_y + 75), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
        cv2.putText(frame, "Q: Cikis", (10, controls_start_y + 90), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        cv2.putText(frame, "Mouse: Tikla ve yonelt", (10, controls_start_y + 105), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        cv2.putText(frame, f"Servo Limitleri: Pan({self.pan_min}-{self.pan_max}), Tilt({self.tilt_min}-{self.tilt_max})", 
                   (10, controls_start_y + 120), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 255, 255), 1)
        cv2.putText(frame, f"Dinamik Hız: Zoom arttıkça yavaşlar", 
                   (10, controls_start_y + 135), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 255, 0), 1)
        cv2.putText(frame, f"Akıllı Zoom: Hedef boyutuna göre otomatik ayar", 
                   (10, controls_start_y + 150), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 255, 255), 1)
        
        return frame
    
    def zoom_in(self):
        """Yakınlaştır"""
        if self.zoom_level < self.zoom_max:
            self.zoom_level = min(self.zoom_max, self.zoom_level + self.zoom_step)
            self.update_dead_zone()  # Dead zone'u güncelle
            print(f"Zoom: {self.zoom_level:.1f}x")
    
    def zoom_out(self):
        """Uzaklaştır"""
        if self.zoom_level > self.zoom_min:
            self.zoom_level = max(self.zoom_min, self.zoom_level - self.zoom_step)
            self.update_dead_zone()  # Dead zone'u güncelle
            print(f"Zoom: {self.zoom_level:.1f}x")
    
    def reset_zoom(self):
        """Zoom'u sıfırla"""
        self.zoom_level = 1.0
        self.update_dead_zone()  # Dead zone'u güncelle
        print("Zoom reset edildi")
    
    def toggle_auto_zoom(self):
        """Otomatik zoom'u aç/kapat"""
        self.auto_zoom_enabled = not self.auto_zoom_enabled
        status = "AÇIK" if self.auto_zoom_enabled else "KAPALI"
        print(f"Otomatik zoom: {status}")
    
    def center_camera(self):
        """Kamerayı merkeze getir"""
        print("Kamera merkeze getiriliyor...")
        self.send_servo_command(90, 150)
        self.target_x = None
        self.target_y = None
        # Kayıp hedef recovery'yi sıfırla
        self.last_face_detection_time = time.time()
        self.lost_target_recovery = False
    
    def run(self):
        """Ana döngü"""
        if not self.initialize_camera():
            return
        
        cv2.namedWindow('Pan-Tilt Kamera Kontrolu')
        cv2.setMouseCallback('Pan-Tilt Kamera Kontrolu', self.mouse_callback)
        
        print("Kamera kontrolü başladı...")
        print("ESP32 IP adresi:", self.esp32_ip)
        print("🎯 BULLSEYE MODU AKTIF - Hareket hızı %50'ye düşürüldü")
        print("Kontroller:")
        print("- Mouse ile tıklayın: Kamera o noktaya yönelir")
        print("- SPACE: Tıklama modu / Yüz takip modu arası geçiş")
        print("- C: Kamerayı merkeze getir")
        print("- + / -: Zoom kontrolü")
        print("- R: Zoom reset")
        print("- A: Auto-zoom aç/kapat")
        print("- Q: Çıkış")
        print("🛡️ Kayıp hedef koruması: 5 saniye hedef görülmezse merkeze döner")
        
        self.running = True
        
        while self.running:
            ret, frame = self.camera.read()
            if not ret:
                print("Kamera görüntüsü alınamıyor!")
                break
            
            # Zoom uygula
            frame = self.apply_zoom(frame)
            
            # Yüz takip modu aktifse yüz tanıma yap
            if self.face_tracking:
                frame = self.detect_and_track_faces(frame)
            
            # Arayüzü çiz
            frame = self.draw_interface(frame)
            
            cv2.imshow('Pan-Tilt Kamera Kontrolu', frame)
            
            # Klavye kontrolleri
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                self.running = False
            elif key == ord(' '):  # Space tuşu
                self.click_mode = not self.click_mode
                self.face_tracking = not self.face_tracking
                mode = "Tıklama Modu" if self.click_mode else "Yüz Takip Modu"
                print(f"Mod değiştirildi: {mode}")
                # Mod değişirken kayıp hedef korumasını sıfırla
                self.last_face_detection_time = time.time()
                self.lost_target_recovery = False
            elif key == ord('c'):
                self.center_camera()
            elif key == ord('+') or key == ord('='):
                self.zoom_in()
            elif key == ord('-'):
                self.zoom_out()
            elif key == ord('r'):
                self.reset_zoom()
            elif key == ord('a'):
                self.toggle_auto_zoom()
        
        self.cleanup()
    
    def cleanup(self):
        """Temizleme işlemleri"""
        print("Temizlik yapılıyor...")
        if self.camera:
            self.camera.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    # ESP32'nizin IP adresini buraya yazın
    esp32_ip = "192.168.43.185"  # Arduino kodunuzdan aldığınız IP adresini yazın
    
    controller = PanTiltController(esp32_ip)
    
    try:
        controller.run()
    except KeyboardInterrupt:
        print("Program sonlandırılıyor...")
        controller.cleanup()