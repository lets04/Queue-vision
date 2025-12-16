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
import torch

# CONFIGURACIÓN

URL_BACKEND = "http://192.168.0.5:8000"
INTERVALO_ENVIO = 2
INTERVALO_FRAME = 5  
MAX_INTENTOS_ENVIO = 1
PUNTO_ATENCION = (640, 720)  # Punto de atención (centro inferior)  
# Punto inicial (persona #1 / ventanilla)
ORIGEN_FILA = (720, 700)

# Dirección de la fila (diagonal hacia atrás)
DIRECCION_FILA = (-1, -1)

# Normalizar dirección
norm = math.sqrt(DIRECCION_FILA[0]**2 + DIRECCION_FILA[1]**2)
DIRECCION_FILA = (DIRECCION_FILA[0]/norm, DIRECCION_FILA[1]/norm)


print("Cargando modelo YOLOv8s...")
model = YOLO('yolov8s.pt')

# OPTIMIZACIONES DEL MODELO
if torch.cuda.is_available():
    model.to('cuda')
else:
    print("Modelo en CPU")

# Fusionar capas para mayor velocidad
model.fuse()

# Configurar para detección optimizada de personas
model.overrides['conf'] = 0.25      # Umbral bajo inicial
model.overrides['iou'] = 0.45       # NMS threshold
model.overrides['classes'] = [0]    # Solo clase 
model.overrides['max_det'] = 50     # Máximo 50 personas por frame

print("✓ Modelo optimizado")

try:
    raw_names = model.names
    classNames = raw_names if isinstance(raw_names, dict) else {i: n for i, n in enumerate(raw_names)}
except:
    classNames = {0: 'person'}

OBJETIVO = "person"

# ARGUMENTOS CLI

parser = argparse.ArgumentParser(description='Detector Multi-Cámara Optimizado')

parser.add_argument('--camera-url', type=str, default=None,
                    help='URL de la cámara IP')

parser.add_argument('--camera-id', type=str, required=True,
                    help='ID único de esta cámara')

parser.add_argument('--segmento', type=int, required=True,
                    help='Número de segmento (1=cerca, 2=medio, 3=lejos)')

parser.add_argument('--umbral-confianza', type=float, default=0.35,
                    help='Umbral de confianza YOLO (bajado para detectar personas parciales)')

parser.add_argument('--distancia-fusion', type=int, default=80,
                    help='Distancia para fusionar detecciones')

parser.add_argument('--zona-fila', type=str, default=None,
                    help='Coordenadas zona: "x1,y1,x2,y2,x3,y3,x4,y4"')

parser.add_argument('--distancia-max', type=int, default=150,
                    help='Distancia máxima para matching')

parser.add_argument('--max-disappeared', type=int, default=60,
                    help='Frames sin detección antes de eliminar')

parser.add_argument('--area-minima', type=int, default=400,
                    help='Área mínima del bbox (px²) - reducido para personas parciales')

parser.add_argument('--aspect-min', type=float, default=0.8,
                    help='Aspect ratio mínimo (alto/ancho) - permite personas cortadas')

parser.add_argument('--aspect-max', type=float, default=5.0,
                    help='Aspect ratio máximo (alto/ancho) - más permisivo')

args = parser.parse_args()

# Offset global para numeración continua
global_offset = 0

# CONFIGURACIÓN DE CÁMARA

camera_id = args.camera_id
segmento = args.segmento
url_camara = args.camera_url or os.getenv('CAMERA_URL') or "http://192.168.0.4:8080/video"

# ZONA DE FILA

if args.zona_fila:
    coords = [int(x) for x in args.zona_fila.split(',')]
    puntos_zona_fila = [
        [coords[0], coords[1]],
        [coords[2], coords[3]],
        [coords[4], coords[5]],
        [coords[6], coords[7]]
    ]
else:
    puntos_zona_fila = [
        [0, 0],          
        [1280, 0],
        [1280, 720],
        [0, 720]
    ]

zona_fila = Polygon(puntos_zona_fila)
zona_fila_dibujo = np.array(puntos_zona_fila, np.int32).reshape((-1, 1, 2))

# TRACKER MEJORADO CON PREDICCIÓN

class TrackerSegmento:
    """Tracker avanzado con predicción de movimiento"""
    
    def __init__(self, distancia_fusion=80, distancia_max=100, max_disappeared=45):
        self.distancia_fusion = distancia_fusion
        self.distancia_max = distancia_max
        self.max_disappeared = max_disappeared
        
        self.next_id = 0
        self.objects = {}           # id -> centro
        self.disappeared = {}       # id -> frames sin detectar
        self.bboxes = {}            # id -> bbox
        self.tiempo_entrada = {}    # id -> timestamp
        
        self.velocidades = {}       # id -> (vx, vy)
        self.last_update = {}       # id -> timestamp
        self.confianzas = {}        # id -> confianza promedio
    
    def _fusionar_detecciones(self, detecciones, bboxes, confianzas):
        """Fusionar detecciones cercanas (madre-bebé)"""
        if len(detecciones) <= 1:
            return detecciones, bboxes, confianzas
        
        fusionadas = []
        bboxes_f = []
        confs_f = []
        usadas = set()
        
        for i, (c1, b1, conf1) in enumerate(zip(detecciones, bboxes, confianzas)):
            if i in usadas:
                continue
            
            grupo_c = [c1]
            grupo_b = [b1]
            grupo_conf = [conf1]
            usadas.add(i)
            
            for j, (c2, b2, conf2) in enumerate(zip(detecciones, bboxes, confianzas)):
                if j in usadas:
                    continue
                
                dist = np.linalg.norm(np.array(c1) - np.array(c2))
                if dist < self.distancia_fusion:
                    grupo_c.append(c2)
                    grupo_b.append(b2)
                    grupo_conf.append(conf2)
                    usadas.add(j)
            
            # Usar bbox con mayor confianza
            if len(grupo_c) > 1:
                idx = np.argmax(grupo_conf)
                bbox_f = grupo_b[idx]
                centro_f = (int((bbox_f[0]+bbox_f[2])/2), int(bbox_f[3]))
                conf_f = grupo_conf[idx]
            else:
                centro_f = grupo_c[0]
                bbox_f = grupo_b[0]
                conf_f = grupo_conf[0]
            
            fusionadas.append(centro_f)
            bboxes_f.append(bbox_f)
            confs_f.append(conf_f)
        
        return fusionadas, bboxes_f, confs_f
    
    def _predecir_posicion(self, oid):
        """Predecir posicion basada en velocidad"""
        if oid not in self.velocidades:
            return self.objects[oid]
        
        vx, vy = self.velocidades[oid]
        x, y = self.objects[oid]
        
        # Predicción simple
        return (int(x + vx), int(y + vy))
    
    def actualizar(self, detecciones, bboxes=None, confianzas=None):
        if bboxes is None:
            bboxes = [None] * len(detecciones)
        if confianzas is None:
            confianzas = [1.0] * len(detecciones)
        
        # Fusionar detecciones cercanas
        if len(detecciones) > 0 and bboxes[0] is not None:
            detecciones, bboxes, confianzas = self._fusionar_detecciones(
                detecciones, bboxes, confianzas
            )
        
        # Sin detecciones: incrementar disappeared
        if len(detecciones) == 0:
            for oid in list(self.disappeared.keys()):
                self.disappeared[oid] += 1
                if self.disappeared[oid] > self.max_disappeared:
                    self._eliminar(oid)
            return self.objects
        
        # Sin objetos previos: registrar todos
        if len(self.objects) == 0:
            for c, b, conf in zip(detecciones, bboxes, confianzas):
                self._registrar(c, b, conf)
            return self.objects
        
        #  MATCHING CON PREDICCIÓN
        obj_ids = list(self.objects.keys())
        costos = np.full((len(obj_ids), len(detecciones)), np.inf)
        
        for i, oid in enumerate(obj_ids):
            # Usar posición predicha
            pos_predicha = self._predecir_posicion(oid)
            
            for j, c in enumerate(detecciones):
                d = np.linalg.norm(np.array(pos_predicha) - np.array(c))
                if d <= self.distancia_max:
                    costos[i, j] = d
        
        # Algoritmo húngaro simplificado
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
        
        for oid, j in asignaciones.items():
            pos_anterior = self.objects[oid]
            pos_nueva = detecciones[j]
            
            # Calcular velocidad
            vx = pos_nueva[0] - pos_anterior[0]
            vy = pos_nueva[1] - pos_anterior[1]
            
            # Suavizado de velocidad 
            if oid in self.velocidades:
                vx_old, vy_old = self.velocidades[oid]
                vx = 0.7 * vx + 0.3 * vx_old
                vy = 0.7 * vy + 0.3 * vy_old
            
            self.velocidades[oid] = (vx, vy)
            self.objects[oid] = pos_nueva
            self.disappeared[oid] = 0
            self.last_update[oid] = time.time()
            
            # Actualizar confianza 
            if oid in self.confianzas:
                self.confianzas[oid] = 0.8 * self.confianzas[oid] + 0.2 * confianzas[j]
            else:
                self.confianzas[oid] = confianzas[j]
            
            if bboxes[j]:
                self.bboxes[oid] = bboxes[j]
        
        # Incrementar disappeared para no asignados
        for i, oid in enumerate(obj_ids):
            if oid not in asignaciones:
                self.disappeared[oid] += 1
                if self.disappeared[oid] > self.max_disappeared:
                    self._eliminar(oid)
        
        # Registrar nuevas detecciones
        for j, (c, b, conf) in enumerate(zip(detecciones, bboxes, confianzas)):
            if j not in usadas:
                self._registrar(c, b, conf)
        
        return self.objects
    
    def _registrar(self, centro, bbox, confianza=1.0):
        self.objects[self.next_id] = centro
        self.disappeared[self.next_id] = 0
        self.tiempo_entrada[self.next_id] = time.time()
        self.velocidades[self.next_id] = (0, 0)
        self.last_update[self.next_id] = time.time()
        self.confianzas[self.next_id] = confianza
        if bbox:
            self.bboxes[self.next_id] = bbox
        print(f"[tracker] ✓ Registrar ID={self.next_id} conf={confianza:.2f}")
        self.next_id += 1
    
    def _eliminar(self, oid):
        print(f"[tracker] ✗ Eliminar ID={oid}")
        for d in [self.objects, self.disappeared, self.bboxes, 
                    self.tiempo_entrada, self.velocidades, self.last_update, 
                    self.confianzas]:
            if oid in d:
                del d[oid]
    
    def obtener_personas_ordenadas(self, zona_polygon):
   
        personas = []

        for oid, centro in self.objects.items():
            if zona_polygon.contains(Point(centro[0], centro[1])):

                # Vector desde origen de la fila
                vx = centro[0] - ORIGEN_FILA[0]
                vy = centro[1] - ORIGEN_FILA[1]

                # Proyección escalar sobre la dirección de la fila
                proyeccion = vx * DIRECCION_FILA[0] + vy * DIRECCION_FILA[1]

                personas.append({
                    'local_id': oid,
                    'centro': centro,
                    'centro_x': centro[0],
                    'centro_y': centro[1],
                    'proyeccion': proyeccion,
                    'bbox': self.bboxes.get(oid),
                    'confianza': self.confianzas.get(oid, 0.0)
                })

        #ORDEN REAL DE FILA
        personas.sort(key=lambda x: x['proyeccion'])

        return personas




# Inicializar tracker
tracker = TrackerSegmento(
    distancia_fusion=args.distancia_fusion,
    distancia_max=args.distancia_max,
    max_disappeared=args.max_disappeared
)

# CONEXIÓN A CÁMARA

cap = cv2.VideoCapture(url_camara)

if not cap.isOpened():
    print(f" No se pudo conectar a {url_camara}, probando webcam...")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print(" Error: No hay camara disponible")
        exit()

print("Cámara conectada")

# COMUNICACIÓN CON BACKEND 

# Variables de control
ultimo_envio_datos = 0
ultimo_envio_frame = 0
envios_pendientes = 0
MAX_ENVIOS_PENDIENTES = 2  

def enviar_datos_segmento(datos):
    """Enviar datos de este segmento al backend y obtener offset para numeración global"""
    global envios_pendientes
    try:
        envios_pendientes += 1
        url = f"{URL_BACKEND}/segmento-fila"
        response = requests.post(url, json=datos, timeout=0.5) 
        response.raise_for_status()
        data = response.json()
        return data.get('offset', 0)
    except requests.exceptions.Timeout:
        return 0
    except Exception as e:
        return 0
    finally:
        envios_pendientes = max(0, envios_pendientes - 1)


def enviar_frame(img):
    """Enviar frame al backend (muy optimizado)"""
    global envios_pendientes
    
    # No enviar si hay muchos pendientes
    if envios_pendientes > MAX_ENVIOS_PENDIENTES:
        return
    
    try:
        envios_pendientes += 1
        
        # Comprimir MUCHO más 
        small = cv2.resize(img, (320, 180), interpolation=cv2.INTER_AREA)
        
        # Calidad JPEG más baja 
        ret, jpeg = cv2.imencode('.jpg', small, [int(cv2.IMWRITE_JPEG_QUALITY), 40])
        
        if ret:
            url = f"{URL_BACKEND}/upload-frame"
            files = {'frame': ('frame.jpg', jpeg.tobytes(), 'image/jpeg')}
            
            # Timeout MUY corto para frames 
            response = requests.post(
                url, 
                files=files, 
                data={'camera_id': camera_id}, 
                timeout=0.3  # ← Solo 300ms
            )
            response.raise_for_status()
    except requests.exceptions.Timeout:
        pass  
    except Exception as e:
        pass 
    finally:
        envios_pendientes = max(0, envios_pendientes - 1)

# PREPROCESAMIENTO MEJORADO

def preprocesar(img):
    """Preprocesar con aspect ratio y padding"""
    h, w = img.shape[:2]
    target_h, target_w = 720, 1280
    
    # Redimensionar manteniendo aspect ratio
    scale = min(target_w / w, target_h / h)
    new_w, new_h = int(w * scale), int(h * scale)
    
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    
    # Crear canvas con padding
    canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)
    x_offset = (target_w - new_w) // 2
    y_offset = (target_h - new_h) // 2
    canvas[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized
    
    return canvas

# BUCLE PRINCIPAL

ultimo_envio_datos = 0
ultimo_envio_frame = 0
frame_count = 0
UMBRAL = args.umbral_confianza
last_diag_time = 0

# Estadísticas
total_detecciones = 0
total_filtradas = 0

# Colores según segmento
COLORES_SEGMENTO = {
    1: (0, 255, 0),      # Verde
    2: (255, 165, 0),    # Naranja
    3: (255, 0, 0),      # Rojo
}
color_segmento = COLORES_SEGMENTO.get(segmento, (255, 255, 255))

print(f"""
  Cámara: {camera_id}
  Segmento: {segmento}
  Modelo: YOLOv8s
  Umbral: {UMBRAL}
  
  Controles:
    'q' → Salir
    '+' → Aumentar umbral (+0.05)
    '-' → Disminuir umbral (-0.05)
    'z' → Mostrar/ocultar zona
    'i' → Toggle info detallada

""")

mostrar_zona = True
mostrar_info_detallada = False

while True:
    success, img = cap.read()
    if not success:
        print("✗ Error leyendo cámara")
        break
    
    frame_count += 1
    img = preprocesar(img)
    
    # DIBUJAR INFO DEL SEGMENTO
    
    cv2.putText(img, f"SEGMENTO {segmento}: {camera_id}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, color_segmento, 2)
    
    if mostrar_zona:
        cv2.polylines(img, [zona_fila_dibujo], True, color_segmento, 2)
    
    # DETECCIÓN YOLO CON FILTROS AVANZADOS
    
    results = model(img, stream=True, verbose=False)
    
    centros = []
    bboxes = []
    confianzas = []
    detecciones_brutas = 0
    
    for r in results:
        for box in r.boxes:
            if classNames[int(box.cls[0])] == OBJETIVO:
                detecciones_brutas += 1
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])
                
                # FILTRO 1: Confianza
                if conf <= UMBRAL:
                    continue
                
                # FILTRO 2: Dimensiones del bbox 
                ancho = x2 - x1
                alto = y2 - y1
                area = ancho * alto
                aspect_ratio = alto / ancho if ancho > 0 else 0
                
                if area < args.area_minima:
                    continue
                
                # Ancho/Alto mínimos individuales 
                if ancho < 30 or alto < 40:
                    continue
                
                # Proporción humana AMPLIA 
                if aspect_ratio < args.aspect_min or aspect_ratio > args.aspect_max:
                    continue
                
                # Tamaño máximo MÁS PERMISIVO 
                if ancho > 600 or alto > 900:
                    continue
                
                # FILTRO 3: Proximidad a la zona 
                cx = int((x1 + x2) / 2)
                cy = int(y2)  # Punto inferior del bbox
                
                punto = Point(cx, cy)
                
                if zona_fila.contains(punto):
                    centros.append((cx, cy))
                    bboxes.append((x1, y1, x2, y2))
                    confianzas.append(conf)
    
    total_detecciones += detecciones_brutas
    total_filtradas += (detecciones_brutas - len(centros))
    
    # TRACKING
    
    tracker.actualizar(centros, bboxes, confianzas)
    personas_ordenadas = tracker.obtener_personas_ordenadas(zona_fila)
    personas_en_segmento = len(personas_ordenadas)
    
    # Diagnóstico
    if time.time() - last_diag_time > INTERVALO_ENVIO:
        tasa_filtrado = (total_filtradas / total_detecciones * 100) if total_detecciones > 0 else 0
        print(f"[diag] Frame={frame_count} | YOLO={len(centros)} | Tracked={len(tracker.objects)} | Fila={personas_en_segmento} | Filtrado={tasa_filtrado:.1f}%")
        last_diag_time = time.time()
    
    # DIBUJAR PERSONAS
    
    for idx, persona in enumerate(personas_ordenadas):
        centro = persona['centro']
        bbox = persona['bbox']
        conf = persona['confianza']
        
        num_local = idx + 1 + global_offset
        
        # Color según confianza
        if conf > 0.75:
            color_bbox = (0, 255, 0)  # Verde alto
        elif conf > 0.60:
            color_bbox = (255, 255, 0)  # Amarillo medio
        else:
            color_bbox = (255, 165, 0)  # Naranja bajo
        
        # Dibujar bbox
        if bbox:
            cv2.rectangle(img, (bbox[0], bbox[1]), (bbox[2], bbox[3]), color_bbox, 2)
            
            # Etiqueta con confianza
            label = f"#{num_local}"
            if mostrar_info_detallada:
                label += f" {conf:.2f}"
            
            # Fondo para texto
            (w_txt, h_txt), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(img, (bbox[0], bbox[1]-h_txt-8), 
                            (bbox[0]+w_txt+8, bbox[1]), color_bbox, -1)
            cv2.putText(img, label, (bbox[0]+4, bbox[1]-4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        
        # Centro
        cv2.circle(img, centro, 5, color_segmento, -1)
        
        # Velocidad (opcional)
        if mostrar_info_detallada and persona['local_id'] in tracker.velocidades:
            vx, vy = tracker.velocidades[persona['local_id']]
            if abs(vx) > 1 or abs(vy) > 1:
                end_x = int(centro[0] + vx * 5)
                end_y = int(centro[1] + vy * 5)
                cv2.arrowedLine(img, centro, (end_x, end_y), (0, 255, 255), 2)
    
    # PANEL DE INFORMACIÓN
    
    overlay = img.copy()
    panel_h = 210 if mostrar_info_detallada else 180
    cv2.rectangle(overlay, (10, 50), (320, 50 + panel_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.7, img, 0.3, 0, img)
    
    y = 75
    cv2.putText(img, f'Personas: {personas_en_segmento}', (20, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    
    y += 35
    cv2.putText(img, f'Umbral: {UMBRAL:.2f}', (20, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 1)
    
    y += 25
    cv2.putText(img, f'Frame: {frame_count}', (20, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
    
    y += 25
    cv2.putText(img, f'Detecciones: {len(centros)}', (20, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
    
    y += 25
    cv2.putText(img, f'Tracked: {len(tracker.objects)}', (20, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
    
    if mostrar_info_detallada:
        y += 25
        tasa = (total_filtradas / total_detecciones * 100) if total_detecciones > 0 else 0
        cv2.putText(img, f'Filtrado: {tasa:.1f}%', (20, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
    
    # Estado conexión
    tiempo_actual = time.time()
    online_datos = tiempo_actual - ultimo_envio_datos < (INTERVALO_ENVIO + 1)
    online_frame = tiempo_actual - ultimo_envio_frame < (INTERVALO_FRAME + 1)
    
    # Indicador de conexión 
    if online_datos and online_frame:
        color_conexion = (0, 255, 0)  # Verde
    elif online_datos or online_frame:
        color_conexion = (0, 255, 255)  # Amarillo
    else:
        color_conexion = (0, 0, 255)  # Rojo
    
    cv2.circle(img, (290, 65), 8, color_conexion, -1)
    
    if envios_pendientes > 0:
        cv2.putText(img, f'Queue: {envios_pendientes}', (245, 85),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
    
    # ENVIAR AL BACKEND 
    
    tiempo_actual = time.time()
    
    # ENVIAR DATOS 
    if tiempo_actual - ultimo_envio_datos > INTERVALO_ENVIO:  
        if envios_pendientes <= MAX_ENVIOS_PENDIENTES:
            datos = {
                "camera_id": camera_id,
                "segmento": segmento,
                "personas_count": personas_en_segmento,
                "personas": [
                    {
                        "local_pos": idx + 1,
                        "centro_x": p["centro_x"],
                        "centro_y": p["centro_y"],
                        "confianza": p["confianza"]
                    }
                    for idx, p in enumerate(personas_ordenadas)
                ],
                "timestamp": tiempo_actual
            }
            
            offset = enviar_datos_segmento(datos)
            global_offset = offset
            ultimo_envio_datos = tiempo_actual
    
    # ENVIAR FRAME 

    if tiempo_actual - ultimo_envio_frame > INTERVALO_FRAME:  
        if envios_pendientes <= MAX_ENVIOS_PENDIENTES:
            try:
                threading.Thread(target=enviar_frame, args=(img.copy(),), daemon=True).start()
                ultimo_envio_frame = tiempo_actual
            except:
                pass
    
    # MOSTRAR
    
    cv2.imshow(f"Segmento {segmento} - {camera_id}", img)
    
    # CONTROLES
    
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    elif key == ord('+') or key == ord('='):
        UMBRAL = min(0.95, UMBRAL + 0.05)
        print(f"✓ Umbral: {UMBRAL:.2f}")
    elif key == ord('-'):
        UMBRAL = max(0.20, UMBRAL - 0.05)
        print(f"✓ Umbral: {UMBRAL:.2f}")
    elif key == ord('z'):
        mostrar_zona = not mostrar_zona
        print(f"✓ Zona: {'visible' if mostrar_zona else 'oculta'}")
    elif key == ord('i'):
        mostrar_info_detallada = not mostrar_info_detallada
        print(f"✓ Info detallada: {'ON' if mostrar_info_detallada else 'OFF'}")

# FINALIZACIÓN

cap.release()
cv2.destroyAllWindows()

tasa_final = (total_filtradas / total_detecciones * 100) if total_detecciones > 0 else 0
