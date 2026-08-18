import requests
import pandas as pd
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Constantes de VEA ---
BUSQUEDAS_VEA = [
    # Gaseosas (Búsqueda genérica)
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/gaseosa?_from=0&_to=39",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/gaseosa?_from=40&_to=79",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/gaseosa?_from=80&_to=129",
    
    # Gaseosas (Búsqueda por marca)
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/Pepsi?_from=0&_to=30",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/Coca-Cola?_from=0&_to=30",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/7up?_from=0&_to=30",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/Sprite?_from=0&_to=30",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/Mirinda?_from=0&_to=15",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/Cunnington?_from=0&_to=15",

    # Gaseosas (SKUs específicos)
    "https://www.vea.com.ar/api/catalog_system/pub/products/search?fq=productId:21831", # Coca Zero 1.5
    "https://www.vea.com.ar/api/catalog_system/pub/products/search?fq=productId:30578", # Sprite Reg 1.5
    "https://www.vea.com.ar/api/catalog_system/pub/products/search?fq=productId:12665", # Coca reg 1,5
    "https://www.vea.com.ar/api/catalog_system/pub/products/search?fq=productId:12575", # Sprite SA 1.5
    "https://www.vea.com.ar/api/catalog_system/pub/products/search?fq=productId:5660",  # PEPSI 2L
    "https://www.vea.com.ar/api/catalog_system/pub/products/search?fq=skuId:238570",  # Mirinda Manzana
    "https://www.vea.com.ar/api/catalog_system/pub/products/search?fq=skuId:34509",    # Mirinda 3l2
    "https://www.vea.com.ar/api/catalog_system/pub/products/search?fq=skuId:247757",  # Mirinda 3l
    "https://www.vea.com.ar/api/catalog_system/pub/products/search?fq=skuId:310897",  # Mirinda 3l1
    
    # Energizantes
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/MONSTER?_from=0&_to=3",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search?fq=skuId:47003",    # Monster1
    "https://www.vea.com.ar/api/catalog_system/pub/products/search?fq=skuId:19714",    # Monster2
    "https://www.vea.com.ar/api/catalog_system/pub/products/search?fq=skuId:258978",  # SPEED
    "https://www.vea.com.ar/api/catalog_system/pub/products/search?fq=skuId:24313",    # Red bull
    "https://www.vea.com.ar/api/catalog_system/pub/products/search?fq=skuId:300483",  # red bull
    
    # Aguas Saborizadas
    "https://www.vea.com.ar/api/catalog_system/pub/products/search?fq=skuId:411797",  # H2O 1,5 STILL
    "https://www.vea.com.ar/api/catalog_system/pub/products/search?fq=skuId:277557",  # AQ500
    "https://www.vea.com.ar/api/catalog_system/pub/products/search?fq=skuId:277480",  # AQ500 - 2
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/levite?_from=0&_to=12",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/h2oh?_from=0&_to=12",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/levite?_from=13&_to=26",
    
    # Isotónicas
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/gatorade?_from=0&_to=30",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/powerade?_from=0&_to=30",
    
    # Cervezas
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/cerveza?_from=0&_to=39",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/cerveza?_from=40&_to=79",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/cerveza?_from=80&_to=119",
    "https://www.vea.com.ar/api/catalog_system/pub/products/search/cerveza?_from=120&_to=150",
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
MAX_WORKERS_CATALOGO = 10 
MAX_WORKERS_PRECIO = 10  

# --- 1. Lógica de Catálogo (fetch_vea_items) ---

def fetch_single_item_catalog(url, status_box):
    """Obtiene el catálogo para una única URL de búsqueda."""
    try:
        # Añadir verify=False para manejar posibles problemas de SSL
        response = requests.get(url, headers=HEADERS_CATALOGO, timeout=10, verify=False) 
        response.raise_for_status()
        products = response.json()
        
        items_encontrados = []
        if not products:
            return []
            
        for product in products:
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
                    'full_json': product 
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
    
    return list(master_items_dict.values())


# --- 2. Lógica de Precios y Promociones (fetch_and_process_vea_prices_parallel) ---

def fetch_single_item_data(item, codigo_suc_vtex, codigo_ccx):
    """
    Función que se ejecuta en un hilo. Obtiene el precio (GET) y la promoción (POST).
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
            
            product_data = data_precio[0] if isinstance(data_precio, list) else data_precio
            offer = product_data.get('items', [{}])[0].get('sellers', [{}])[0].get('commertialOffer', {})
            
        except (json.JSONDecodeError, IndexError, AttributeError) as e:
            return None

        stock = offer.get('AvailableQuantity', 0)
        
        if stock > 0:
            
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
                    promo_info = promo_data[first_promo_key]
                    
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
                    'vigencia_promo': promo_fin,        # Fecha Fin
                    'vigencia_promo_desde': promo_inicio, # Fecha Inicio
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

def fetch_and_process_vea_prices_parallel(master_items_vea, nombre_suc, provincia, codigo_suc_vtex, codigo_ccx, status_box, progress_bar):
    """
    Paso 2: Obtiene precios y promos para todos los items de la lista maestra, en paralelo.
    """
    
    total_items = len(master_items_vea)
    status_box.write(f"→ Iniciando {total_items} tareas paralelas (Precio y Promo) para {nombre_suc}...")
    
    lista_productos_sucursal = []
    vea_errors = None # Usado para consistencia, aunque el log de errores podría ser más detallado
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_PRECIO) as executor:
        futures = {
            executor.submit(fetch_single_item_data, item, codigo_suc_vtex, codigo_ccx): item 
            for item in master_items_vea
        }
        
        items_procesados = 0
        for future in as_completed(futures):
            resultado = future.result()
            items_procesados += 1
            
            # --- Actualizar TEXTO de progreso local (no el valor de la barra) ---
            if hasattr(progress_bar, 'progress'):
                progress_bar.text(f"Procesando Vea - {nombre_suc} ({items_procesados}/{total_items})")
            
            if resultado:
                # Añadir datos de la sucursal
                resultado['sucursal'] = nombre_suc
                resultado['provincia'] = provincia
                resultado['Cadena'] = 'Vea'
                resultado['fecha_exportacion'] = pd.Timestamp.now().strftime("%Y-%m-%d")
                lista_productos_sucursal.append(resultado)
    
    status_box.write(f"→ Finalizado Vea para {nombre_suc}. Se obtuvieron {len(lista_productos_sucursal)} productos con stock.")
    
    if not lista_productos_sucursal:
        return pd.DataFrame(), vea_errors

    df_sucursal = pd.DataFrame(lista_productos_sucursal)
    
    # Asegurar tipos de datos numéricos
    df_sucursal['precio_anterior'] = pd.to_numeric(df_sucursal['precio_anterior'], errors='coerce').fillna(0.0)
    df_sucursal['precio_promo'] = pd.to_numeric(df_sucursal['precio_promo'], errors='coerce').fillna(0.0)

    # Bloque de robustez contra división por cero
    unit_price_cols = ['precio_x_lt', 'precio_x_kg', 'precio_por_unidad'] 

    for col in unit_price_cols:
        if col in df_sucursal.columns:
            df_sucursal[col] = df_sucursal[col].replace([float('inf'), float('-inf')], 0.0)
            df_sucursal[col] = pd.to_numeric(df_sucursal[col], errors='coerce').fillna(0.0)

    # Retorna DataFrame y el estado de errores
    return df_sucursal, vea_errors