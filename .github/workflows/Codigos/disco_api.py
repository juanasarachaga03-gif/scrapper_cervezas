import requests
import pandas as pd
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Constantes de Disco (CORREGIDAS) ---

BUSQUEDAS_DISCO = [
    # cerveza principal (muchas páginas)
    *(f"https://www.disco.com.ar/api/catalog_system/pub/products/search/cerveza?_from={i}&_to={i+49}" for i in range(0, 600, 50)),

    # variantes clave (muy importante)
    *(f"https://www.disco.com.ar/api/catalog_system/pub/products/search/beer?_from={i}&_to={i+49}" for i in range(0, 200, 50)),
    *(f"https://www.disco.com.ar/api/catalog_system/pub/products/search/lager?_from={i}&_to={i+49}" for i in range(0, 200, 50)),
    *(f"https://www.disco.com.ar/api/catalog_system/pub/products/search/ipa?_from={i}&_to={i+49}" for i in range(0, 200, 50)),

]





# Headers base para la API de catálogo (búsqueda de items)
HEADERS_CATALOGO = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Content-Type': 'application/json',
    'Referer': 'https://www.disco.com.ar/',
    'Origin': 'https://www.disco.com.ar',
}

# Headers para la API de precios (requiere cookie de sucursal)
HEADERS_PRECIO = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Content-Type': 'application/json',
    'Referer': 'https://www.disco.com.ar/',
    'Origin': 'https://www.disco.com.ar',
}

# Headers para la API de promociones (requiere 'seller' en el body)
HEADERS_PROMO = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Content-Type': 'application/json',
    'Referer': 'https://www.disco.com.ar/',
    'Origin': 'https://www.disco.com.ar',
}

URL_PRECIO_SKU = "https://www.disco.com.ar/api/catalog_system/pub/products/search?fq=skuId:"
URL_PROMO = "https://www.disco.com.ar/_v/search-promotions"
MAX_WORKERS_CATALOGO = 5 # Hilos para la búsqueda inicial de catálogo
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
        status_box.warning(f"  [Disco Catalog] URL fallida: {url}. Error: {e}")
        return []

def fetch_disco_items(status_box):
    """
    Paso 1: Obtiene la lista maestra de todos los Item IDs de Disco en paralelo.
    """
    status_box.write(f"→ Iniciando {len(BUSQUEDAS_DISCO)} búsquedas paralelas de catálogo maestro...")
    start_time = time.time()
    
    master_items_dict = {}
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_CATALOGO) as executor:
        # Mapeamos cada URL a un 'future'
        futures = {executor.submit(fetch_single_item_catalog, url, status_box): url for url in BUSQUEDAS_DISCO}
        
        for future in as_completed(futures):
            items = future.result()
            for item in items:
                # Usamos el EAN como clave única para evitar duplicados
                if item['ean'] not in master_items_dict:
                    master_items_dict[item['ean']] = item

    end_time = time.time()
    total_items = len(master_items_dict)
    
    status_box.write(f"→ Recolectados {total_items} Item IDs únicos para Disco (Tiempo: {end_time - start_time:.2f}s)")
    
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
        
        # --- DEBUGGING ---
        # print(f"--- PRECIO (SKU: {item_id}) ---")
        # print(json.dumps(response_precio.json(), indent=2))
        # --- FIN DEBUGGING ---

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
                    print("PROMO RESPONSE:", data_promo)

                    # --- LÓGICA DE EXTRACCIÓN DE PROMO (CORREGIDA) ---
                    promo_data = data_promo.get('promotions', {}).get('generic', {}).get('promotions', {})
                    promo_desc = "Sin promo"

                    if promo_data:
                        first_promo_key = next(iter(promo_data))
                        promo_info = promo_data[first_promo_key]
                        promo_desc = promo_info.get('code', 'Promo s/desc')

                    promo_inicio = "Sin fecha" # <-- CAMBIO: Inicializar fecha inicio
                    promo_fin = "Sin fecha"    # <-- CAMBIO: Inicializar fecha fin
                    
                    if promo_data:
                        first_promo_key = next(iter(promo_data))
                        promo_info = promo_data[first_promo_key] # Obtenemos todo el objeto de la promo
                        
                        promo_desc = promo_info.get('code', 'Promo s/desc')
                        promo_inicio = promo_info.get('start', 'Sin fecha') # <-- CAMBIO: Extraer 'start'
                        promo_fin = promo_info.get('end', 'Sin fecha')      # <-- CAMGIO: Extraer 'end'

                    # --- INICIO DE LA CORRECCIÓN ---
                    # Se invierten las variables para que coincidan las columnas.
                    # 'vigencia_promo' debe ser la fecha de FIN.
                    # 'vigencia_promo_desde' debe ser la fecha de INICIO.
                    # Combinar datos
                    return {
                        'codinterno': item['ean'],
                        'descripcion': item['productName'],
                        'marca_desc': item['brand'],
                        'precio_anterior': float(precio_base),
                        'precio_promo': float(precio_promo),
                        'cantidad_promo': promo_desc,
                        'vigencia_promo': promo_fin,        # <-- CORREGIDO (Fecha Fin)
                        'vigencia_promo_desde': promo_inicio, # <-- CORREGIDO (Fecha Inicio)
                    }
                    # --- FIN DE LA CORRECCIÓN ---
                except requests.exceptions.RequestException as e_promo:
                # Si falla la promo pero tenemos precio, lo devolvemos igual
                    return {
                        'codinterno': item['ean'],
                        'descripcion': item['productName'],
                        'marca_desc': item['brand'],
                        'precio_anterior': float(precio_base),
                        'precio_promo': float(precio_promo),
                        'cantidad_promo': "Error promo",
                        'vigencia_promo': "Error promo",    # <-- CAMBIO
                        'vigencia_promo_desde': "Error promo", # <-- CAMBIO
                    }
        else:
            # print(f"[Debug Disco] SKU {item_id}: Stock 0. (Cookie: {codigo_suc_vtex})")
            return None # Producto sin stock
            
    except requests.exceptions.RequestException as e_precio:
        # print(f"[Debug Disco] SKU {item_id}: Falló la llamada de PRECIO. Error: {e_precio}")
        return None # Falla la llamada de precio

def fetch_and_process_disco_prices_parallel(master_items_disco, nombre_suc, provincia, codigo_suc_vtex, codigo_ccx, status_box, progress_bar, current_step, total_steps):
    print("SUCURSAL:", nombre_suc)
    """
    Paso 2: Obtiene precios y promos para todos los items de la lista maestra, en paralelo.
    """
    
    total_items = len(master_items_disco)
    status_box.write(f"→ Iniciando {total_items} tareas paralelas (Precio y Promo) para {nombre_suc}...")
    
    lista_productos_sucursal = []
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_PRECIO) as executor:
        # Creamos un future por cada item
        futures = {
            executor.submit(fetch_single_item_data, item, codigo_suc_vtex, codigo_ccx): item 
            for item in master_items_disco
        }
        
        items_procesados = 0
        for future in as_completed(futures):
            resultado = future.result()
            items_procesados += 1
            
            # Actualizar barra de progreso general
            current_step_local = current_step + items_procesados 
            # Note: Si usas el logger de consola, progress_bar.progress es un método dummy.
            if hasattr(progress_bar, 'progress'):
                
                # === CORRECCIÓN CONTRA DIVISION BY ZERO ===
                # Si total_steps es 0 (como en la ejecución automática), evitamos la división.
                progress_value = 0.0
                if total_steps > 0:
                    progress_value = current_step_local / total_steps
                
                progress_bar.progress(progress_value, text=f"Procesando {nombre_suc} ({items_procesados}/{total_items})")
            
            if resultado:
                # Añadir datos de la sucursal
                resultado['sucursal'] = nombre_suc
                resultado['provincia'] = provincia
                resultado['Cadena'] = 'Disco'
                resultado['fecha_exportacion'] = pd.Timestamp.now().strftime("%Y-%m-%d")
                lista_productos_sucursal.append(resultado)
    
    # Actualizamos el contador de pasos global
    current_step += total_items 

    status_box.write(f"→ Finalizado Disco para {nombre_suc}. Se obtuvieron {len(lista_productos_sucursal)} productos con stock.")
    
    if not lista_productos_sucursal:
        return pd.DataFrame(), current_step

    df_sucursal = pd.DataFrame(lista_productos_sucursal)
    
    # Asegurar tipos de datos numéricos
    df_sucursal['precio_anterior'] = pd.to_numeric(df_sucursal['precio_anterior'], errors='coerce').fillna(0.0)
    df_sucursal['precio_promo'] = pd.to_numeric(df_sucursal['precio_promo'], errors='coerce').fillna(0.0)

    # === BLOQUE DE ROBUSTEZ CONTRA DIVISION BY ZERO ===
    # El error 'division by zero' ocurre cuando alguna lógica de precio unitario (que no vemos aquí) 
    # se ejecuta antes de que el script principal lo maneje. Aseguramos la limpieza aquí.
    
    # Columnas comunes que causan división por cero si el peso/volumen es cero
    unit_price_cols = ['precio_x_lt', 'precio_x_kg', 'precio_por_unidad'] 

    for col in unit_price_cols:
        if col in df_sucursal.columns:
            # Reemplazamos los valores infinitos (resultado de X/0) con 0
            df_sucursal[col] = df_sucursal[col].replace([float('inf'), float('-inf')], 0.0)
            # También aseguramos que sean numéricos
            df_sucursal[col] = pd.to_numeric(df_sucursal[col], errors='coerce').fillna(0.0)
    # =================================================

    return df_sucursal, current_step