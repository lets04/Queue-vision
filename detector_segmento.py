
import cv2
import numpy as np
from ultralytics import YOLO
import math
from shapely.geometry import Point
from shapely.geometry.polygon import Polygon
import requests
import time
import threading
import os
import argparse

# CONFIGURACIÓN

URL_BACKEND = "http://127.0.0.1:8000"
INTERVALO_ENVIO = 2

print("Cargando modelo YOLO...")
model = YOLO('yolov8n.pt')
print("Modelo cargado")

try:
    raw_names = model.names
    classNames = raw_names if isinstance(raw_names, dict) else {i: n for i, n in enumerate(raw_names)}
except:
    classNames = {0: 'person'}

# ARGUMENTOS CLI

parser = argparse.ArgumentParser(description='Detector Multi-Cámara para Fila Extendida')

parser.add_argument('--camera-url', type=str, default=None,
                    help='URL de la cámara IP')

parser.add_argument('--camera-id', type=str, required=True,
                    help='ID único de esta cámara (ej: cam_interior, cam_puerta, cam_exterior)')

parser.add_argument('--segmento', type=int, required=True,
                    help='Número de segmento en la fila (1=más cerca de ventanilla, 2=siguiente, 3=más lejos)')

parser.add_argument('--umbral-confianza', type=float, default=0.50,
                    help='Umbral de confianza YOLO')

parser.add_argument('--distancia-fusion', type=int, default=80,
                    help='Distancia para fusionar detecciones (madre-bebé)')

# Zonas personalizables por cámara
parser.add_argument('--zona-fila', type=str, default=None,
                    help='Coordenadas zona fila: "x1,y1,x2,y2,x3,y3,x4,y4"')

parser.add_argument('--distancia-max', type=int, default=100,
                    help='Distancia máxima (px) para hacer matching entre frames')

parser.add_argument('--max-disappeared', type=int, default=45,
                    help='Cantidad de frames sin detección antes de eliminar un objeto')

args = parser.parse_args()

# CONFIGURACIÓN DE CÁMARA

camera_id = args.camera_id
segmento = args.segmento
url_camara = args.camera_url or os.getenv('CAMERA_URL') or "http://192.168.0.8:8080/video"


# ZONA DE FILA 

if args.zona_fila:
    # Parsear coordenadas desde argumento
    coords = [int(x) for x in args.zona_fila.split(',')]
    puntos_zona_fila = [
        [coords[0], coords[1]],
        [coords[2], coords[3]],
        [coords[4], coords[5]],
        [coords[6], coords[7]]
    ]
else:
    # Zona por defecto 
    puntos_zona_fila = [
        [100, 100],
        [1180, 100],
        [1180, 700],
        [100, 700]
    ]

zona_fila = Polygon(puntos_zona_fila)
zona_fila_dibujo = np.array(puntos_zona_fila, np.int32).reshape((-1, 1, 2))

# TRACKER SIMPLE 

class TrackerSegmento:
    """
    Tracker simple para un segmento de la fila.
    No necesita Re-ID porque solo cuenta personas en SU zona.
    """
    
    def __init__(self, distancia_fusion=80, distancia_max=100, max_disappeared=45):
        self.distancia_fusion = distancia_fusion
        self.distancia_max = distancia_max
        self.max_disappeared = max_disappeared
        
        self.next_id = 0
        self.objects = {}           # id -> centro
        self.disappeared = {}       # id -> frames
        self.bboxes = {}            # id -> bbox
        self.tiempo_entrada = {}    # id -> timestamp
    
    def _fusionar_detecciones(self, detecciones, bboxes):
        """Fusionar detecciones cercanas (madre-bebé)"""
        if len(detecciones) <= 1:
            return detecciones, bboxes
        
        fusionadas = []
        bboxes_f = []
        usadas = set()
        
        for i, (c1, b1) in enumerate(zip(detecciones, bboxes)):
            if i in usadas:
                continue
            
            grupo_c = [c1]
            grupo_b = [b1]
            usadas.add(i)
            
            for j, (c2, b2) in enumerate(zip(detecciones, bboxes)):
                if j in usadas:
                    continue
                
                dist = np.linalg.norm(np.array(c1) - np.array(c2))
                if dist < self.distancia_fusion:
                    grupo_c.append(c2)
                    grupo_b.append(b2)
                    usadas.add(j)
            
            # Usar bbox más grande
            if len(grupo_c) > 1:
                areas = [(b[2]-b[0])*(b[3]-b[1]) for b in grupo_b]
                idx = np.argmax(areas)
                bbox_f = grupo_b[idx]
                centro_f = (int((bbox_f[0]+bbox_f[2])/2), int(bbox_f[3]))
            else:
                centro_f = grupo_c[0]
                bbox_f = grupo_b[0]
            
            fusionadas.append(centro_f)
            bboxes_f.append(bbox_f)
        
        return fusionadas, bboxes_f
    
    def actualizar(self, detecciones, bboxes=None):
        if bboxes is None:
            bboxes = [None] * len(detecciones)
        
        # Fusionar
        if len(detecciones) > 0 and bboxes[0] is not None:
            detecciones, bboxes = self._fusionar_detecciones(detecciones, bboxes)
        
        # Sin detecciones
        if len(detecciones) == 0:
            for oid in list(self.disappeared.keys()):
                self.disappeared[oid] += 1
                if self.disappeared[oid] > self.max_disappeared:
                    self._eliminar(oid)
            return self.objects
        
        # Sin objetos previos
        if len(self.objects) == 0:
            for c, b in zip(detecciones, bboxes):
                self._registrar(c, b)
            return self.objects
        
        # Matching
        obj_ids = list(self.objects.keys())
        costos = np.full((len(obj_ids), len(detecciones)), np.inf)
        
        for i, oid in enumerate(obj_ids):
            for j, c in enumerate(detecciones):
                d = np.linalg.norm(np.array(self.objects[oid]) - np.array(c))
                if d <= self.distancia_max:
                    costos[i, j] = d
        
        asignaciones = {}
        usadas = set()
        
        while not np.all(np.isinf(costos)):
            i, j = np.unravel_index(np.argmin(costos), costos.shape)
            if costos[i, j] == np.inf:
                break
            
            asignaciones[obj_ids[i]] = j
            usadas.add(j)
            costos[i, :] = np.inf
            costos[:, j] = np.inf
        
        # Actualizar asignados
        for oid, j in asignaciones.items():
            self.objects[oid] = detecciones[j]
            self.disappeared[oid] = 0
            if bboxes[j]:
                self.bboxes[oid] = bboxes[j]
        
        # Disappeared
        for i, oid in enumerate(obj_ids):
            if oid not in asignaciones:
                self.disappeared[oid] += 1
                if self.disappeared[oid] > self.max_disappeared:
                    self._eliminar(oid)
        
        # Nuevas
        for j, (c, b) in enumerate(zip(detecciones, bboxes)):
            if j not in usadas:
                self._registrar(c, b)
        
        return self.objects
    
    def _registrar(self, centro, bbox):
        self.objects[self.next_id] = centro
        self.disappeared[self.next_id] = 0
        self.tiempo_entrada[self.next_id] = time.time()
        if bbox:
            self.bboxes[self.next_id] = bbox
        print(f"[tracker] registrar id={self.next_id} centro={centro} bbox={'yes' if bbox else 'no'}")
        self.next_id += 1
    
    def _eliminar(self, oid):
        print(f"[tracker] eliminar id={oid}")
        for d in [self.objects, self.disappeared, self.bboxes, self.tiempo_entrada]:
            if oid in d:
                del d[oid]
    
    def obtener_personas_ordenadas(self, zona_polygon):
        """Obtener personas en la zona ordenadas por Y"""
        personas = []
        for oid, centro in self.objects.items():
            if zona_polygon.contains(Point(centro[0], centro[1])):
                personas.append({
                    'local_id': oid,
                    'centro': centro,
                    'centro_y': centro[1],
                    'bbox': self.bboxes.get(oid)
                })
        
        # Ordenar por Y (menor = más adelante)
        personas.sort(key=lambda x: x['centro_y'])
        return personas


tracker = TrackerSegmento(
    distancia_fusion=args.distancia_fusion,
    distancia_max=args.distancia_max,
    max_disappeared=args.max_disappeared
)

# CONEXIÓN A CÁMARA

cap = cv2.VideoCapture(url_camara)

if not cap.isOpened():
    print(f"No se pudo conectar a {url_camara}, probando webcam...")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: No hay cámara")
        exit()

print("Cámara conectada ✓")

# COMUNICACIÓN CON BACKEND

def enviar_datos_segmento(datos):
    """Enviar datos de este segmento al backend"""
    try:
        url = f"{URL_BACKEND}/segmento-fila"
        requests.post(url, json=datos, timeout=2)
    except Exception as e:
        pass


def enviar_frame(img):
    """Enviar frame al backend"""
    try:
        ret, jpeg = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if ret:
            url = f"{URL_BACKEND}/upload-frame"
            files = {'frame': ('frame.jpg', jpeg.tobytes(), 'image/jpeg')}
            requests.post(url, files=files, data={'camera_id': camera_id}, timeout=3)
    except:
        pass


# BUCLE PRINCIPAL

def preprocesar(img):
    return cv2.resize(img, (1280, 720))


ultimo_envio = time.time()
frame_count = 0
UMBRAL = args.umbral_confianza
last_diag_time = 0

# Colores según segmento
COLORES_SEGMENTO = {
    1: (0, 255, 0),    # Verde - cerca de ventanilla
    2: (255, 165, 0),  # Naranja - medio
    3: (255, 0, 0),    # Rojo - exterior/lejos
}
color_segmento = COLORES_SEGMENTO.get(segmento, (255, 255, 255))

print(f"""
Controles:
  'q' - Salir
  '+' - Aumentar umbral
  '-' - Disminuir umbral
  'z' - Mostrar/ocultar zona

Iniciando detección...
""")

mostrar_zona = True

while True:
    success, img = cap.read()
    if not success:
        print("Error leyendo cámara")
        break
    
    frame_count += 1
    img = preprocesar(img)
    
    #  DIBUJAR INFO DEL SEGMENTO 
    
    # Etiqueta del segmento
    cv2.putText(img, f"SEGMENTO {segmento}: {camera_id}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, color_segmento, 2)
    
    # Dibujar zona de fila
    if mostrar_zona:
        cv2.polylines(img, [zona_fila_dibujo], True, color_segmento, 2)
    
    #  DETECCIÓN YOLO
    
    results = model(img, stream=True, verbose=False)
    
    centros = []
    bboxes = []
    
    for r in results:
        for box in r.boxes:
            if classNames[int(box.cls[0])] == "person":
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])
                
                if conf > UMBRAL:
                    cx = int((x1 + x2) / 2)
                    cy = int(y2)
                    centros.append((cx, cy))
                    bboxes.append((x1, y1, x2, y2))
    
    # TRACKING 
    
    tracker.actualizar(centros, bboxes)
    personas_ordenadas = tracker.obtener_personas_ordenadas(zona_fila)
    personas_en_segmento = len(personas_ordenadas)
    
    # Diagnostic mínimo: cada INTERVALO_ENVIO mostrar conteos
    try:
        if time.time() - last_diag_time > INTERVALO_ENVIO:
            print(f"[diag] frame={frame_count} detecciones_yolo={len(centros)} tracked={len(tracker.objects)} personas_en_segmento={personas_en_segmento}")
            last_diag_time = time.time()
    except NameError:
        last_diag_time = time.time()
    
    # DIBUJAR PERSONAS 
    
    for idx, persona in enumerate(personas_ordenadas):
        centro = persona['centro']
        bbox = persona['bbox']
        
        # Número local en este segmento
        num_local = idx + 1
        
        if bbox:
            cv2.rectangle(img, (bbox[0], bbox[1]), (bbox[2], bbox[3]), color_segmento, 2)
        
        # Mostrar posición en la fila
        cv2.putText(img, f"#{num_local}", (centro[0]-15, centro[1]-15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        
        cv2.circle(img, centro, 5, color_segmento, -1)
    
    # PANEL INFO 
    
    overlay = img.copy()
    cv2.rectangle(overlay, (10, 50), (300, 180), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.7, img, 0.3, 0, img)
    
    y = 75
    cv2.putText(img, f'Personas en segmento: {personas_en_segmento}', (20, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    
    y += 30
    cv2.putText(img, f'Umbral: {UMBRAL:.2f}', (20, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
    
    y += 25
    cv2.putText(img, f'Frame: {frame_count}', (20, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
    
    # Estado conexión
    online = time.time() - ultimo_envio < 3
    cv2.circle(img, (280, 65), 8, (0, 255, 0) if online else (0, 0, 255), -1)
    
    # ENVIAR AL BACKEND 
    
    if time.time() - ultimo_envio > INTERVALO_ENVIO:
        datos = {
            "camera_id": camera_id,
            "segmento": segmento,
            "personas_count": personas_en_segmento,
            "personas": [
                {
                    "local_pos": idx + 1,
                    "centro_y": p["centro_y"]
                }
                for idx, p in enumerate(personas_ordenadas)
            ],
            "timestamp": time.time()
        }
        
        threading.Thread(target=enviar_datos_segmento, args=(datos,)).start()
        
        try:
            small = cv2.resize(img, (640, 360))
            threading.Thread(target=enviar_frame, args=(small,)).start()
        except:
            pass
        
        ultimo_envio = time.time()
    
    #  MOSTRAR
    
    cv2.imshow(f"Segmento {segmento} - {camera_id}", img)
    
    #  CONTROLES 
    
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    elif key == ord('+') or key == ord('='):
        UMBRAL = min(0.95, UMBRAL + 0.05)
        print(f"Umbral: {UMBRAL:.2f}")
    elif key == ord('-'):
        UMBRAL = max(0.20, UMBRAL - 0.05)
        print(f"Umbral: {UMBRAL:.2f}")
    elif key == ord('z'):
        mostrar_zona = not mostrar_zona

cap.release()
cv2.destroyAllWindows()
print(f"\nSegmento {segmento} detenido. Frames: {frame_count}")