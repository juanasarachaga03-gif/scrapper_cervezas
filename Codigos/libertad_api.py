import requests
import pandas as pd
import time
import random
from datetime import datetime
import urllib3

# --- SILENCIAR ADVERTENCIAS SSL ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =================================================================
#               CONFIGURACIÓN ESPECÍFICA DE HIPERLIBERTAD
# =================================================================
# URL Base de la API de VTEX para Hiperlibertad
URL_BASE_API = "https://www.hiperlibertad.com.ar/api/catalog_system/pub/products/search/"

# Rutas de categorías corregidas para asegurar que devuelvan datos.
# Las rutas que no funcionen deben ser reemplazadas manualmente después de investigar el sitio.
CATEGORIAS_BUSQUEDA = [
    "bebidas/gaseosas",      # <-- CONFIRMADA
    "bebidas",               # <-- RUTA MÁS GENERAL, suele funcionar
    # "almacen/bebidas/cervezas-y-sidras", # <-- Ejemplo de cómo puede ser la ruta real
    "bebidas/aguas/saborizadas"
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json'
}

# =================================================================
#                       FUNCIÓN DE EXTRACCIÓN (Contiene el logging mejorado)
# =================================================================

def fetch_libertad_category_api(categoria, status_box):
    """
    Obtiene productos JSON de la API de Hiperlibertad, con paginado y manejo de errores.
    """
    productos_categoria = []
    _from = 0
    _to = 49  # Rango de 50 productos
    step = 50 
    
    MAX_ITERATIONS = 3
    current_iteration = 0
    
    while current_iteration < MAX_ITERATIONS:
        url = f"{URL_BASE_API}{categoria}?_from={_from}&_to={_to}&O=OrderByScoreDESC"
        
        try:
            time.sleep(random.uniform(0.5, 1.0))
            
            response = requests.get(url, headers=HEADERS, timeout=20, verify=False)
            
            if response.status_code not in [200, 206]:
                # Muestra la URL y el código de error.
                status_box.warning(f"⚠️ API Error {response.status_code} en {categoria}. URL fallida: {url}")
                if response.status_code == 404:
                    status_box.error(f"❌ La ruta de categoría '{categoria}' no existe en Hiperlibertad. Revise el sitio web.")
                break
            
            data = response.json()
            
            if not data:
                # Confirma que la URL se consultó pero no devolvió datos.
                status_box.info(f"ℹ️ URL consultada ({categoria}), pero no devolvió productos. Fin de la paginación.")
                break
                
            productos_categoria.extend(data)
            
            if len(data) < step:
                break
                
            _from += step
            _to += step
            current_iteration += 1
            
        except requests.exceptions.Timeout:
            status_box.error(f"❌ Timeout de conexión para {url}")
            break
            
        except requests.exceptions.RequestException as e:
            status_box.error(f"❌ Error de red/request en Hiperlibertad ({categoria}): {e}")
            break
            
        except Exception as e:
            status_box.error(f"❌ Error de procesamiento desconocido en Hiperlibertad ({categoria}): {e}. URL: {url}")
            break
            
    return productos_categoria

# =================================================================
#                       FUNCIÓN DE PROCESAMIENTO (Igual a la de Toledo)
# =================================================================

def procesar_producto_libertad(producto_json, nombre_suc, nodo):
    filas = []
    
    nombre_producto = producto_json.get('productName', '') or producto_json.get('name', '')
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
                "Cadena": "Hiperlibertad", 
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

# =================================================================
#                       FUNCIÓN PRINCIPAL DE PROCESO
# =================================================================

def fetch_and_process_libertad_prices(nombre_suc, nodo, provincia, status_box, progress_bar):
    # Validación para evitar el error 'nan'
    if pd.isna(nombre_suc) or nombre_suc is None:
        status_box.error("❌ ERROR: Nombre de Sucursal es nulo ('nan'). Revise la columna 'Sucursal' en su Excel.")
        return pd.DataFrame()
        
    status_box.info(f"🚀 Procesando Hiperlibertad: {nombre_suc} (Vía API)...")
    
    todos_los_productos = []
    total_cats = len(CATEGORIAS_BUSQUEDA)
    
    for i, categoria in enumerate(CATEGORIAS_BUSQUEDA):
        progreso = (i / total_cats)
        progress_bar.progress(progreso, text=f"Hiperlibertad ({nombre_suc}): Bajando {categoria}...")
        
        items_raw = fetch_libertad_category_api(categoria, status_box)
        
        for p in items_raw:
            filas_procesadas = procesar_producto_libertad(p, nombre_suc, nodo)
            todos_los_productos.extend(filas_procesadas)
            
    progress_bar.progress(1.0, text=f"Hiperlibertad {nombre_suc}: Finalizado.")
    
    if not todos_los_productos:
        status_box.warning(f"⚠️ Hiperlibertad devolvió 0 productos para {nombre_suc} en las categorías buscadas.")
        return pd.DataFrame()

    df = pd.DataFrame(todos_los_productos)

    columnas_ordenadas = [
        "Fecha extracción", "Cadena", "Sucursal", "NODO", "EAN", "Descripcion", 
        "Marca", "Precio Fleje", "Precio Dinamizado", "Promocion Desc", 
        "Inicio Promo", "Fin Promo"
    ]
    
    return df.reindex(columns=columnas_ordenadas)