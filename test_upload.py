import numpy as np
import cv2
import requests
import time

# Crear imagen de prueba
img = np.zeros((360,640,3), dtype=np.uint8)
img[:] = (0,128,255)
cv2.putText(img, 'TEST', (50,200), cv2.FONT_HERSHEY_SIMPLEX, 4, (255,255,255), 6)
cv2.imwrite('test.jpg', img)

# Subir imagen de prueba
try:
    with open('test.jpg','rb') as f:
        r = requests.post('http://127.0.0.1:8000/upload-frame', files={'frame':('frame.jpg', f, 'image/jpeg')}, data={'camera_id':'cam_exterior'}, timeout=5)
        print('POST /upload-frame ->', r.status_code, r.text)
except Exception as e:
    print('Error al POST /upload-frame:', e)

# Consultar /cameras
try:
    r2 = requests.get('http://127.0.0.1:8000/cameras', timeout=5)
    print('/cameras ->', r2.status_code)
    print(r2.text)
except Exception as e:
    print('Error al GET /cameras:', e)

# Intentar obtener algunos bytes del stream
try:
    s = requests.get('http://127.0.0.1:8000/stream/cam_exterior.mjpg', timeout=5, stream=True)
    print('/stream status ->', s.status_code)
    it = s.iter_content(chunk_size=1024)
    chunk = next(it)
    print('Stream chunk len:', len(chunk))
    s.close()
except Exception as e:
    print('Error al GET /stream:', e)
