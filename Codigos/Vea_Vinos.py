import requests
import pandas as pd
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Constantes de VEA (VINOS - LISTA PERSONALIZADA) ---
BUSQUEDAS_VEA = [
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/DANTE%20ROBINO?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/DANTE?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/DANTE%20ROBINO%20RESERVA?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/TORO?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/ALMA%20MORA?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/VIÑAS%20DE%20BALBO?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/SANTA%20JULIA?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/TERMIDOR?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/PORTILLO?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/CANCILLER?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/COSECHA%20TARDIA?_from=0&_to=49", # Corregido de COCECHA
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/ELEMENTOS?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/VIÑAS%20DE%20ALVEAR?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/RESERO?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/LOS%20ARBOLES?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/BENJAMIN?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/NAMPE?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/EMILIA?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/CORDERO%20PIEL%20DE%20LOBO?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/FINCA%20LAS%20MORAS?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/DADA?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/FOND%20DE%20CAVE?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/TRUMPETER?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/COLON?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/SALENTEIN?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/NOVECENTO?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/ALARIS?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/FEDERICO%20DE%20ALVEAR?_from=0&_to=49",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/TRAPICHE?_from=0&_to=49",
]


# Headers base para la API de catálogo (búsqueda de items)
HEADERS_CATALOGO = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Content-Type': 'application/json',
    'Referer': 'https://www.vea.com.ar/',
    'Origin': 'https://www.vea.com.ar',
}

# Headers para la API de precios (requiere cookie de sucursal)
HEADERS_PRECIO = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Content-Type': 'application/json',
    'Referer': 'https://www.vea.com.ar/',
    'Origin': 'https://www.vea.com.ar',
}

# Headers para la API de promociones (requiere 'seller' en el body)
HEADERS_PROMO = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Content-Type': 'application/json',
    'Referer': 'https://www.vea.com.ar/',
    'Origin': 'https://www.vea.com.ar',
}

URL_PRECIO_SKU = "https://www.vea.com.ar/api/catalog_system/pub/products/search?fq=skuId:"
URL_PROMO = "https://www.vea.com.ar/_v/search-promotions"
MAX_WORKERS_CATALOGO = 10 # Hilos para la búsqueda inicial de catálogo
MAX_WORKERS_PRECIO = 10  # Hilos para la búsqueda de precios/promos

# --- 1. Lógica de Catálogo (Pre-procesamiento) ---

def fetch_single_item_catalog(url, status_box):
    """Obtiene el catálogo para una única URL de búsqueda."""
    try:
        response = requests.get(url, headers=HEADERS_CATALOGO, timeout=10, verify=False)
        response.raise_for_status()
        products = response.json()
        
        # Procesar la respuesta
        items_encontrados = []
        if not products:
            return []
            
        for product in products:
            # Manejar productos que pueden no tener 'items'
            if not product.get('items'):
                continue
                
            item_id = product.get('items', [{}])[0].get('itemId')
            ean = product.get('items', [{}])[0].get('ean')
            brand = product.get('brand', 'N/D')
            product_name = product.get('productName', 'N/D')
            
            if item_id and ean:
                items_encontrados.append({
                    'itemId': item_id,
                    'ean': ean,
                    'brand': brand,
                    'productName': product_name,
                    'full_json': product # Guardamos el JSON por si lo necesitamos
                })
        return items_encontrados
        
    except requests.exceptions.RequestException as e:
        status_box.warning(f"  [Vea Catalog] URL fallida: {url}. Error: {e}")
        return []

def fetch_vea_items(status_box):
    """
    Paso 1: Obtiene la lista maestra de todos los Item IDs de Vea en paralelo.
    """
    status_box.write(f"→ Iniciando {len(BUSQUEDAS_VEA)} búsquedas paralelas de catálogo maestro...")
    start_time = time.time()
    
    master_items_dict = {}
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_CATALOGO) as executor:
        # Mapeamos cada URL a un 'future'
        futures = {executor.submit(fetch_single_item_catalog, url, status_box): url for url in BUSQUEDAS_VEA}
        
        for future in as_completed(futures):
            items = future.result()
            for item in items:
                # Usamos el EAN como clave única para evitar duplicados
                if item['ean'] not in master_items_dict:
                    master_items_dict[item['ean']] = item

    end_time = time.time()
    total_items = len(master_items_dict)
    
    status_box.write(f"→ Recolectados {total_items} Item IDs únicos para Vea (Tiempo: {end_time - start_time:.2f}s)")
    
    # Devolvemos solo la lista de diccionarios
    return list(master_items_dict.values())


# --- 2. Lógica de Precios y Promociones (Por Sucursal) ---

def fetch_single_item_data(item, codigo_suc_vtex, codigo_ccx):
    """
    Función que se ejecuta en un hilo.
    Obtiene el precio (GET) y la promoción (POST) para un solo item.
    """
    item_id = item['itemId']
    
    # 1. Obtener Precio (usando cookie vtex_segment)
    url_precio = f"{URL_PRECIO_SKU}{item_id}"
    cookies = {'vtex_segment': codigo_suc_vtex}
    
    try:
        response_precio = requests.get(url_precio, headers=HEADERS_PRECIO, cookies=cookies, timeout=10, verify=False)
        response_precio.raise_for_status()
        
        try:
            data_precio = response_precio.json()
            if isinstance(data_precio, list) and not data_precio:
                return None 
            
            if isinstance(data_precio, list):
                product_data = data_precio[0]
            else:
                product_data = data_precio
                
            offer = product_data.get('items', [{}])[0].get('sellers', [{}])[0].get('commertialOffer', {})
            
        except (json.JSONDecodeError, IndexError, AttributeError) as e:
            return None

        stock = offer.get('AvailableQuantity', 0)
        
        if stock > 0:
            
            # Lógica de Precios (basada en n8n)
            precio_real = offer.get('Price', 0.0) 
            precio_base = precio_real
            precio_promo = precio_real
            
            # 2. Obtener Promoción (usando 'seller'/'codigo_ccx')
            payload_promo = {"seller": str(codigo_ccx), "skus": [str(item_id)]}
            
            try:
                response_promo = requests.post(URL_PROMO, headers=HEADERS_PROMO, json=payload_promo, timeout=10, verify=False)
                response_promo.raise_for_status()
                data_promo = response_promo.json()
                
                # --- LÓGICA DE EXTRACCIÓN DE PROMO ---
                promo_data = data_promo.get('promotions', {}).get('generic', {}).get('promotions', {})
                promo_desc = "Sin promo"
                promo_inicio = "Sin fecha" 
                promo_fin = "Sin fecha"    
                
                if promo_data:
                    first_promo_key = next(iter(promo_data))
                    promo_info = promo_data[first_promo_key] # Obtenemos todo el objeto de la promo
                    
                    promo_desc = promo_info.get('code', 'Promo s/desc')
                    promo_inicio = promo_info.get('start', 'Sin fecha') 
                    promo_fin = promo_info.get('end', 'Sin fecha')      

                # Combinar datos
                return {
                    'codinterno': item['ean'],
                    'descripcion': item['productName'],
                    'marca_desc': item['brand'],
                    'precio_anterior': float(precio_base),
                    'precio_promo': float(precio_promo),
                    'cantidad_promo': promo_desc,
                    'vigencia_promo': promo_fin,        
                    'vigencia_promo_desde': promo_inicio, 
                }

            except requests.exceptions.RequestException as e_promo:
                # Si falla la promo pero tenemos precio, lo devolvemos igual
                return {
                    'codinterno': item['ean'],
                    'descripcion': item['productName'],
                    'marca_desc': item['brand'],
                    'precio_anterior': float(precio_base),
                    'precio_promo': float(precio_promo),
                    'cantidad_promo': "Error promo",
                    'vigencia_promo': "Error promo",    
                    'vigencia_promo_desde': "Error promo", 
                }
        else:
            return None # Producto sin stock
            
    except requests.exceptions.RequestException as e_precio:
        return None # Falla la llamada de precio

def fetch_and_process_vea_prices_parallel(master_items_vea, nombre_suc, provincia, codigo_suc_vtex, codigo_ccx, status_box, progress_bar, current_step, total_steps):
    """
    Paso 2: Obtiene precios y promos para todos los items de la lista maestra, en paralelo.
    """
    
    total_items = len(master_items_vea)
    status_box.write(f"→ Iniciando {total_items} tareas paralelas (Precio y Promo) para {nombre_suc}...")
    
    lista_productos_sucursal = []
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_PRECIO) as executor:
        # Creamos un future por cada item
        futures = {
            executor.submit(fetch_single_item_data, item, codigo_suc_vtex, codigo_ccx): item 
            for item in master_items_vea
        }
        
        items_procesados = 0
        for future in as_completed(futures):
            resultado = future.result()
            items_procesados += 1
            
            # Actualizar barra de progreso general
            current_step_local = current_step + items_procesados 
            
            if hasattr(progress_bar, 'progress'):
                progress_value = 0.0
                if total_steps > 0:
                    progress_value = current_step_local / total_steps
                
                progress_bar.progress(progress_value, text=f"Procesando {nombre_suc} ({items_procesados}/{total_items})")
            
            if resultado:
                # Añadir datos de la sucursal
                resultado['sucursal'] = nombre_suc
                resultado['provincia'] = provincia
                resultado['Cadena'] = 'Vea'
                resultado['fecha_exportacion'] = pd.Timestamp.now().strftime("%Y-%m-%d")
                lista_productos_sucursal.append(resultado)
    
    # Actualizamos el contador de pasos global
    current_step += total_items 

    status_box.write(f"→ Finalizado Vea para {nombre_suc}. Se obtuvieron {len(lista_productos_sucursal)} productos con stock.")
    
    if not lista_productos_sucursal:
        return pd.DataFrame(), current_step

    df_sucursal = pd.DataFrame(lista_productos_sucursal)
    
    # Asegurar tipos de datos numéricos
    df_sucursal['precio_anterior'] = pd.to_numeric(df_sucursal['precio_anterior'], errors='coerce').fillna(0.0)
    df_sucursal['precio_promo'] = pd.to_numeric(df_sucursal['precio_promo'], errors='coerce').fillna(0.0)

    # Limpieza división por cero
    unit_price_cols = ['precio_x_lt', 'precio_x_kg', 'precio_por_unidad'] 

    for col in unit_price_cols:
        if col in df_sucursal.columns:
            df_sucursal[col] = df_sucursal[col].replace([float('inf'), float('-inf')], 0.0)
            df_sucursal[col] = pd.to_numeric(df_sucursal[col], errors='coerce').fillna(0.0)

    return df_sucursal, current_step