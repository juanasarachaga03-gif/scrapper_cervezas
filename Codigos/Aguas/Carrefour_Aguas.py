import requests
import pandas as pd
import json
import time
import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONSTANTES DE CARREFOUR (ADAPTADAS PARA AGUAS) ---
URL_BASE_BUSQUEDA = "https://www.carrefour.com.ar/api/catalog_system/pub/products/search/"
URL_BASE_SKU = "https://www.carrefour.com.ar/api/catalog_system/pub/products/search?fq=skuId:"

# Parámetros de búsqueda adaptados para la categoría "Aguas"
BUSQUEDAS_CARREFOUR = [
    # Aguas Minerales (Búsqueda genérica)
    "?ft=agua-mineral&_from=0&_to=39",
    "?ft=agua-mineral&_from=40&_to=79",
    "?ft=agua-mineral&_from=80&_to=129",

    # Aguas con Gas
    "?ft=agua-con-gas&_from=0&_to=39",
    "?ft=soda&_from=0&_to=19", # Búsqueda de soda/agua gasificada
]

HEADERS_CARREFOUR = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Content-Type': 'application/json',
    'Referer': 'https://www.carrefour.com.ar/',
    'Origin': 'https://www.carrefour.com.ar',
}

# --- CORRECCIÓN 1: Reducir la concurrencia para el catálogo ---
MAX_WORKERS_CATALOGO = 4 
MAX_WORKERS_PRECIO = 10 

# --- 1. LÓGICA DE CATÁLOGO (Pre-procesamiento) ---

def fetch_single_item_catalog_carrefour(url, status_box):
    """Obtiene el catálogo para una única URL de búsqueda."""
    
    # --- CORRECCIÓN 2: Pausa antes de cada solicitud (Aleatoria) ---
    sleep_time = random.uniform(1, 4)
    time.sleep(sleep_time)
    
    try:
        response = requests.get(url, headers=HEADERS_CARREFOUR, timeout=10, verify=False)
        response.raise_for_status()
        productos_json = response.json()
        
        items_encontrados = set()
        if not productos_json:
            return items_encontrados

        for prod in productos_json:
            primera_variante = prod.get('items', [None])[0]
            if primera_variante and primera_variante.get('itemId'):
                items_encontrados.add(primera_variante['itemId'])
        
        return items_encontrados

    except requests.exceptions.RequestException as e:
        status_box.warning(f"  [Carrefour Catalog] URL fallida: {url}. Error: {e}")
        return set()

def fetch_carrefour_items(status_box):
    """
    Paso 1: Obtiene la lista maestra de todos los Item IDs de Carrefour en paralelo.
    """
    status_box.write(f"→ Iniciando {len(BUSQUEDAS_CARREFOUR)} búsquedas paralelas de catálogo maestro (Carrefour)...")
    start_time = time.time()
    
    all_item_ids = set()
    
    num_workers_catalogo = min(MAX_WORKERS_CATALOGO, len(BUSQUEDAS_CARREFOUR))
    if num_workers_catalogo == 0: num_workers_catalogo = 1 

    with ThreadPoolExecutor(max_workers=num_workers_catalogo) as executor:
        futures = {executor.submit(fetch_single_item_catalog_carrefour, f"{URL_BASE_BUSQUEDA}{params}", status_box): params for params in BUSQUEDAS_CARREFOUR}
        
        for future in as_completed(futures):
            items_set = future.result()
            all_item_ids.update(items_set)

    end_time = time.time()
    total_items = len(all_item_ids)
    status_box.write(f"→ Recolectados {total_items} Item IDs únicos para Carrefour (Tiempo: {end_time - start_time:.2f}s)")
    
    return list(all_item_ids)


# --- 2. LÓGICA DE PRECIOS (Por Sucursal y Paralela) ---

def fetch_single_item_data_carrefour(item_id, id_sucursal_cookie, nombre_suc, provincia):
    """
    Función que se ejecuta en un hilo.
    Obtiene y procesa el precio de un solo item_id.
    """
    url_completa = f"{URL_BASE_SKU}{item_id}"
    
    headers_con_cookie = HEADERS_CARREFOUR.copy()
    headers_con_cookie['Cookie'] = f'vtex_segment={id_sucursal_cookie}'

    try:
        response = requests.get(url_completa, headers=headers_con_cookie, timeout=10, verify=False)
        response.raise_for_status() 
        
        productos_api = response.json()
        if not productos_api:
            return [] # No se encontró el producto para esta sucursal

        # Procesamos la respuesta JSON
        return procesar_respuesta_carrefour_json(productos_api, nombre_suc, provincia)
        
    except requests.exceptions.RequestException:
        return [] # Retorna lista vacía en caso de error

# --- MODIFICACIÓN: NUEVA FUNCIÓN AÑADIDA ---
def calculate_effective_discount_percentage(promo_name):
    """
    Calcula el porcentaje de descuento efectivo (ahorro promedio unitario)
    o el porcentaje de descuento directo basado en el nombre de la promoción.
    """
    
    # 1. Extracción del patrón -Reg-X-Y-
    match = re.search(r'-Reg-(\d+)-(\d+)-', promo_name)
    if not match:
        return ''
    
    X = int(match.group(1)) # Unidades Mínimas/Factor (ej: 1, 2, 3, 6)
    Y = int(match.group(2)) # Porcentaje de Descuento (ej: 20, 50, 80, 100)
    
    # 2. Lógica de Cálculo
    
    # Caso 1: Descuento directo (Reg-1-Y-) -> X=1
    # Ejemplo: -Reg-1-20- (20% Off), -Reg-1-40- (40% Off)
    if X == 1:
        return f"{Y:.2f}%"
    
    # Caso 2: Promociones 2do al Z% OFF (donde Z es Y)
    # X=2 (El segundo) y Y es el descuento aplicado al segundo.
    # El ahorro total es: 1 * (Y/100)
    # El descuento promedio unitario (efectivo) es: (Ahorro Total / 2 unidades) * 100
    if X == 2 and Y != 100:
        # Ejemplo: 2do al 50% (Y=50). Ahorro total = 0.5. Descuento efectivo = (0.5 / 2) * 100 = 25%
        # Ejemplo: 2do al 80% (Y=80). Ahorro total = 0.8. Descuento efectivo = (0.8 / 2) * 100 = 40%
        effective_discount = ((Y / 100) / X) * 100
        return f"{effective_discount:.2f}%"

    # Caso 3: Promociones N x M (donde M = N-1 y el descuento es 100%)
    # Ejemplo 3x2, 2x1, 6x5. Esto significa que 1 unidad es gratis (100% OFF).
    # Unidades Totales = X (ej: 2 para 2x1, 3 para 3x2)
    # Unidades Gratis = 1
    if Y == 100 and X > 1:
        # Ejemplo 2x1 (X=2). Descuento efectivo = (1 / 2) * 100 = 50%
        # Ejemplo 3x2 (X=3). Descuento efectivo = (1 / 3) * 100 = 33.33%
        # Ejemplo 6x5 (X=6). Descuento efectivo = (1 / 6) * 100 = 16.67%
        units_bought = X
        units_free = 1 # Asumimos que 1 unidad es gratis para Xx(X-1)
        effective_discount = (units_free / units_bought) * 100
        return f"{effective_discount:.2f}%"

    # Si no coincide con un patrón conocido, devuelve vacío
    return ''
# --- FIN DE LA NUEVA FUNCIÓN ---


def procesar_respuesta_carrefour_json(productos_api, nombre_suc, provincia):
    """
    Procesa la respuesta JSON de un SKU de Carrefour y la convierte en una lista de diccionarios.
    """
    lista_productos = []
    
    for producto in productos_api:
        product_name = producto.get('productName', 'N/D')
        brand = producto.get('brand', 'N/D')
        
        for variante in producto.get('items', []):
            item_id = variante.get('itemId')
            
            ean = None
            ref_ids = variante.get('referenceId', [])
            if ref_ids and ref_ids[0].get('Value'):
                ean = ref_ids[0]['Value']
                
            seller = variante.get('sellers', [None])[0]
            if not seller:
                continue

            offer = seller.get('commertialOffer', {})
            
            list_price = offer.get('ListPrice') # Precio Regular (Precio Anterior)
            price = offer.get('Price')         # Precio Promocional (Precio Promo)
            stock = offer.get('AvailableQuantity', 0)
            
            # Solo procesar si hay stock y precio
            if (not list_price or list_price == 0) and (not price or price == 0):
                continue
            if stock <= 0:
                continue

            # Lógica de Promoción (del n8n)
            promo_name = ''
            discount_highlight = offer.get('DiscountHighLight', [])
            if discount_highlight:
                promo_raw = discount_highlight[0]
                promo_name_key = next((key for key in promo_raw if 'Name' in key), None)
                if promo_name_key:
                    promo_name = promo_raw.get(promo_name_key, '')
            
            if not promo_name:
                teasers = offer.get('PromotionTeasers', [])
                promo = teasers[2] if len(teasers) > 2 else teasers[1] if len(teasers) > 1 else teasers[0] if len(teasers) > 0 else None
                if promo and promo.get('Name'):
                    promo_name = promo['Name']
            
            # --- MODIFICACIÓN: CÁLCULO DE DESCUENTO ---
            descuento_calculado = calculate_effective_discount_percentage(promo_name)
            
            # Mapeo a formato estandarizado
            registro = {
                'sucursal': nombre_suc,
                'provincia': provincia,
                'codinterno': ean or item_id,
                'descripcion': product_name,
                'marca_desc': brand,
                'precio_anterior': float(list_price) if list_price is not None else float(price), # Usar 'Price' si 'ListPrice' no existe
                'precio_promo': float(price) if price is not None else 0.0,
                'cantidad_promo': promo_name,
                # --- MODIFICACIÓN: ASIGNACIÓN DE DESCUENTO ---
                'descuento_porcentaje_promo': descuento_calculado,
                'Cadena': 'Carrefour', 
                'fecha_exportacion': pd.Timestamp.now().strftime("%Y-%m-%d"),
            }
            lista_productos.append(registro)
        
    return lista_productos

# --- 3. FUNCIÓN PRINCIPAL (Llamada desde Scrapper.py) ---

def fetch_and_process_carrefour_prices_parallel(master_items_carrefour, nombre_suc, provincia, id_sucursal_cookie, status_box, progress_bar, current_step, total_steps):
    """
    Función paralela que Scrapper.py llamará.
    """
    total_items = len(master_items_carrefour)
    status_box.write(f"→ Iniciando {total_items} tareas paralelas (Precio) para {nombre_suc}...")
    
    lista_de_listas_productos = [] # Cada hilo devuelve una lista de productos
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_PRECIO) as executor:
        futures = {
            executor.submit(fetch_single_item_data_carrefour, item_id, id_sucursal_cookie, nombre_suc, provincia): item_id 
            for item_id in master_items_carrefour
        }
        
        items_procesados = 0
        for future in as_completed(futures):
            lista_resultado = future.result() # Esto es una lista de diccionarios
            items_procesados += 1
            
            current_step_local = current_step + items_procesados
            
            # --- INICIO DE LA CORRECCIÓN ---
            progress_value = 0.0
            if total_steps > 0:
                progress_value = current_step_local / total_steps
            
            progress_bar.progress(progress_value, text=f"Procesando {nombre_suc} ({items_procesados}/{total_items})")
            # --- FIN DE LA CORRECCIÓN ---
            
            if lista_resultado:
                lista_de_listas_productos.append(lista_resultado)
    
    # Aplanar la lista de listas
    lista_final_productos = [item for sublist in lista_de_listas_productos for item in sublist]
    
    current_step += total_items 

    status_box.write(f"→ Finalizado Carrefour para {nombre_suc}. Se obtuvieron {len(lista_final_productos)} productos con stock.")
    
    if not lista_final_productos:
        return pd.DataFrame(), current_step

    df_sucursal = pd.DataFrame(lista_final_productos)
    
    # Asegurar tipos de datos numéricos
    df_sucursal['precio_anterior'] = pd.to_numeric(df_sucursal['precio_anterior'], errors='coerce').fillna(0.0)
    df_sucursal['precio_promo'] = pd.to_numeric(df_sucursal['precio_promo'], errors='coerce').fillna(0.0)
    
    return df_sucursal, current_step