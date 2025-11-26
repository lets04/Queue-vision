import cv2
import numpy as np
from ultralytics import YOLO
import math
from shapely.geometry import Point
from shapely.geometry.polygon import Polygon
import requests  # <--- NUEVO
import time      # <--- NUEVO
import threading # <--- NUEVO (Para enviar datos sin congelar el video)

# --- CONFIGURACIÓN ---
URL_BACKEND = "http://127.0.0.1:8000/actualizar-fila" # Dirección de tu servidor local
INTERVALO_ENVIO = 2 # Enviar datos cada 2 segundos

model = YOLO('yolov8n.pt')

classNames = ["person", "bicycle", "car", "motorbike", "aeroplane", "bus", "train", "truck", "boat",
              "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
              "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
              "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite", "baseball bat",
              "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
              "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange", "broccoli",
              "carrot", "hot dog", "pizza", "donut", "cake", "chair", "sofa", "pottedplant", "bed",
              "diningtable", "toilet", "tvmonitor", "laptop", "mouse", "remote", "keyboard", "cell phone",
              "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors",
              "teddy bear", "hair drier", "toothbrush"]

# --- ZONA DE FILA (CALIBRAR ESTO CON TU CÁMARA REAL) ---
puntos_zona = [
    [100, 100], 
    [1180, 100], 
    [1180, 700], 
    [100, 700]
]
zona_fila = Polygon(puntos_zona)
zona_dibujo = np.array(puntos_zona, np.int32).reshape((-1, 1, 2))

# --- CAMBIAR POR TU IP DE CELULAR ---
url_camara = "http://192.168.0.107:8080/video"  # Reemplaza con la URL de tu cámara IP cap = cv2.VideoCapture(url_camara)
cap = cv2.VideoCapture(url_camara) 

# Función para enviar datos en segundo plano (para no laggear el video)
def enviar_al_servidor(cantidad):
    try:
        data = {"conteo": cantidad}
        requests.post(URL_BACKEND, json=data)
        # print(f"Enviado: {cantidad}")
    except:
        print("Error: El servidor backend parece estar apagado.")

ultimo_envio = time.time()
conteo_actual = 0

while True:
    success, img = cap.read()
    if not success:
        print("Error al leer cámara")
        break

    # Redimensionar para mejorar rendimiento si la cámara del celular es 4K
    img = cv2.resize(img, (1280, 720))

    cv2.polylines(img, [zona_dibujo], True, (255, 0, 0), 3)

    results = model(img, stream=True, verbose=False) # verbose=False para limpiar la terminal
    
    personas_en_fila = 0

    for r in results:
        boxes = r.boxes
        for box in boxes:
            cls = int(box.cls[0])
            if classNames[cls] == "person":
                x1, y1, x2, y2 = box.xyxy[0]
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                conf = math.ceil((box.conf[0] * 100)) / 100

                if conf > 0.50:
                    centro_x = int((x1 + x2) / 2)
                    centro_y = int(y2) 
                    punto_pies = Point(centro_x, centro_y)

                    if zona_fila.contains(punto_pies):
                        personas_en_fila += 1
                        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    else:
                        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2)

    # --- LÓGICA DE ENVÍO ---
    # Solo enviamos al servidor si han pasado X segundos
    if time.time() - ultimo_envio > INTERVALO_ENVIO:
        # Usamos un hilo (thread) para que el 'request' no pause el video
        threading.Thread(target=enviar_al_servidor, args=(personas_en_fila,)).start()
        ultimo_envio = time.time()

    # Panel visual
    cv2.rectangle(img, (20, 20), (450, 100), (0, 0, 0), -1)
    cv2.putText(img, f'En Fila: {personas_en_fila}', (30, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)

    cv2.imshow("Sistema Fila - Cliente", img)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()