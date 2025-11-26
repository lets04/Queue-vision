import cv2
import numpy as np
from ultralytics import YOLO
import math
from shapely.geometry import Point
from shapely.geometry.polygon import Polygon

# 1. CONFIGURACIÓN
# ----------------
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

# --- DEFINICIÓN DE LA ZONA DE LA FILA (POLÍGONO) ---
# Estos puntos definen un trapezoide en el centro de la pantalla.
# Puedes cambiar estos números para ajustar la zona a tu cámara real.
# Formato: [x, y]
puntos_zona = [
    [100, 100],   # Esquina superior izquierda
    [1180, 100],  # Esquina superior derecha
    [1180, 700],  # Esquina inferior derecha
    [100, 700]    # Esquina inferior izquierda
]

# Creamos el polígono matemático con Shapely
zona_fila = Polygon(puntos_zona)
# Creamos el array para dibujar en OpenCV
zona_dibujo = np.array(puntos_zona, np.int32)
zona_dibujo = zona_dibujo.reshape((-1, 1, 2))

# 2. INICIAR CÁMARA
cap = cv2.VideoCapture(0)
cap.set(3, 1280)
cap.set(4, 720)

while True:
    success, img = cap.read()
    if not success:
        break

    # Dibujar la zona de la fila (Líneas Azules)
    cv2.polylines(img, [zona_dibujo], True, (255, 0, 0), 3)

    # Inferencia
    results = model(img, stream=True)
    
    # Reiniciar contador en cada frame
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
                    # --- LÓGICA ESPACIAL ---
                    # Calculamos el punto de los PIES (centro inferior de la caja)
                    centro_x = int((x1 + x2) / 2)
                    centro_y = int(y2) 

                    punto_pies = Point(centro_x, centro_y)

                    # VERIFICAR: ¿Están los pies dentro de la zona?
                    if zona_fila.contains(punto_pies):
                        # SI: Está en la fila
                        personas_en_fila += 1
                        color = (0, 255, 0) # Verde
                        estado = "En Fila"
                    else:
                        # NO: Está fuera
                        color = (0, 0, 255) # Rojo
                        estado = "Fuera"

                    # Dibujar
                    cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
                    # Dibujar punto en los pies
                    cv2.circle(img, (centro_x, centro_y), 5, color, cv2.FILLED)
                    cv2.putText(img, estado, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

    # Panel de información
    cv2.rectangle(img, (20, 20), (450, 100), (0, 0, 0), -1)
    cv2.putText(img, f'Contador Fila: {personas_en_fila}', (30, 70), 
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)

    cv2.imshow("Sistema de Filas - FASE 2", img)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()