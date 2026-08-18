import requests
import pandas as pd
import time
import random
from datetime import datetime
import urllib3

# --- SILENCIAR ADVERTENCIAS SSL ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIGURACIÓN ---
URL_BASE_API = "https://www.toledodigital.com.ar/api/catalog_system/pub/products/search/"

CATEGORIAS_BUSQUEDA = [
    "bebidas/cervezas",
    "cervezas",
    "beer"
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json'
}

def fetch_toledo_category_api(categoria, status_box):
    """
    Obtiene productos JSON de la API, usando el paginado OBLIGATORIO de 50 items.
    Limita las peticiones a 3 páginas (max 150 ítems) para cubrir la solicitud de 120.
    """
    productos_categoria = []
    _from = 0
    _to = 49  # Rango de 50 productos
    step = 50 # Paso fijo de 50
    
    # Ejecutamos 3 veces (0-49, 50-99, 100-149) para asegurar cubrir los 120 ítems
    MAX_ITERATIONS = 10
    current_iteration = 0
    
    while current_iteration < MAX_ITERATIONS:
        url = f"{URL_BASE_API}{categoria}?_from={_from}&_to={_to}&O=OrderByScoreDESC"
        
        try:
            time.sleep(random.uniform(0.5, 1.0))
            
            response = requests.get(url, headers=HEADERS, timeout=20, verify=False)
            
            if response.status_code not in [200, 206]:
                status_box.warning(f"⚠️ API Error {response.status_code} en {categoria} (Pág {_from})")
                break
            
            data = response.json()
            
            if not data:
                break
                
            productos_categoria.extend(data)
            
            # Si devuelve menos datos que el paso (50), llegamos al final del catálogo.
            if len(data) < step:
                break
                
            _from += step
            _to += step
            current_iteration += 1 # Contamos la iteración
            
        except Exception as e:
            status_box.error(f"❌ Error conexión Toledo ({categoria}): {e}")
            break
            
    return productos_categoria

def procesar_producto_toledo(producto_json, nombre_suc, nodo):
    filas = []
    
    nombre_producto = producto_json.get('productName', '') or producto_json.get('name', '')
    # --- FILTRO CERVEZA ---
    keywords_beer = ['cerveza', 'beer', 'lager', 'ipa', 'stout']
    if not any(k in descripcion.lower() for k in keywords_beer):
        return []

    marca = producto_json.get('brand', '')
    
    for item in producto_json.get('items', []):
        ean = item.get('ean', '')
        if not ean and 'referenceId' in item:
            refs = item['referenceId']
            if isinstance(refs, list) and len(refs) > 0:
                ean = refs[0].get('Value', '')
        if not ean:
            ean = item.get('itemId', '')

        seller = item.get('sellers', [{}])[0]
        offer = seller.get('commertialOffer', {})
        
        precio_dinamico = float(offer.get('Price') or 0)
        precio_lista_raw = float(offer.get('ListPrice') or 0)
        
        if precio_lista_raw > 0:
            precio_fleje = precio_lista_raw
        else:
            precio_fleje = precio_dinamico

        promocion_desc = ""
        if precio_fleje > precio_dinamico:
            try:
                descuento_pct = round(100 - ((precio_dinamico / precio_fleje) * 100))
                promocion_desc = f"{descuento_pct}% OFF"
            except:
                pass

        stock = offer.get('AvailableQuantity', 0)
        
        if stock > 0:
            fila = {
                "Fecha extracción": datetime.now().strftime("%d/%m/%Y"),
                "Cadena": "Toledo",
                "Sucursal": nombre_suc,
                "NODO": nodo,
                "EAN": ean,
                "Descripcion": nombre_producto,
                "Marca": marca,
                "Precio Fleje": precio_fleje,
                "Precio Dinamizado": precio_dinamico,
                "Promocion Desc": promocion_desc,
                "Inicio Promo": "",
                "Fin Promo": ""
            }
            filas.append(fila)
            
    return filas

def fetch_and_process_toledo_prices(nombre_suc, nodo, provincia, status_box, progress_bar):
    status_box.info(f"🚀 Procesando Toledo: {nombre_suc} (Vía API)...")
    
    todos_los_productos = []
    total_cats = len(CATEGORIAS_BUSQUEDA)
    
    for i, categoria in enumerate(CATEGORIAS_BUSQUEDA):
        progreso = (i / total_cats)
        progress_bar.progress(progreso, text=f"Toledo ({nombre_suc}): Bajando {categoria}...")
        
        items_raw = fetch_toledo_category_api(categoria, status_box)
        
        for p in items_raw:
            filas_procesadas = procesar_producto_toledo(p, nombre_suc, nodo)
            todos_los_productos.extend(filas_procesadas)
            
    progress_bar.progress(1.0, text=f"Toledo {nombre_suc}: Finalizado.")
    
    if not todos_los_productos:
        status_box.warning(f"⚠️ Toledo devolvió 0 productos para {nombre_suc}.")
        return pd.DataFrame()

    df = pd.DataFrame(todos_los_productos)

    columnas_ordenadas = [
        "Fecha extracción",
        "Cadena",
        "Sucursal",
        "NODO",
        "EAN",
        "Descripcion",
        "Marca",
        "Precio Fleje",
        "Precio Dinamizado",
        "Promocion Desc",
        "Inicio Promo",
        "Fin Promo"
    ]
    
    return df.reindex(columns=columnas_ordenadas)