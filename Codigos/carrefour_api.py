import requests
import pandas as pd
import json
import time
import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONSTANTES DE CARREFOUR ---
URL_BASE_BUSQUEDA = "https://www.carrefour.com.ar/api/catalog_system/pub/products/search/"

# 24 queries de búsqueda que cubren todas las categorías relevantes
BUSQUEDAS_CARREFOUR = [

    # cerveza principal
    *(f"?ft=cerveza&_from={i}&_to={i+49}" for i in range(0, 500, 50)),

    # variantes clave
    *(f"?ft=beer&_from={i}&_to={i+49}" for i in range(0, 200, 50)),
    *(f"?ft=lager&_from={i}&_to={i+49}" for i in range(0, 200, 50)),
    *(f"?ft=ipa&_from={i}&_to={i+49}" for i in range(0, 200, 50)),
    *(f"?ft=stout&_from={i}&_to={i+49}" for i in range(0, 200, 50)),
    *(f"?ft=porter&_from={i}&_to={i+49}" for i in range(0, 200, 50)),
]

HEADERS_CARREFOUR = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Content-Type': 'application/json',
    'Referer': 'https://www.carrefour.com.ar/',
    'Origin': 'https://www.carrefour.com.ar',
}

MAX_WORKERS = 10

def fetch_carrefour_items(status_box):
    """
    DEPRECATED: El catálogo maestro ya no es necesario.
    Se mantiene por compatibilidad con el orquestador principal.
    """
    return []

def calculate_effective_discount_percentage(promo_name):
    """
    Calcula el porcentaje de descuento efectivo basado en el nombre de la promoción.
    """
    match = re.search(r'-Reg-(\d+)-(\d+)-', promo_name)
    if not match:
        return ''

    X = int(match.group(1))
    Y = int(match.group(2))

    if X == 1:
        return f"{Y:.2f}%"

    if X == 2 and Y != 100:
        effective_discount = ((Y / 100) / X) * 100
        return f"{effective_discount:.2f}%"

    if Y == 100 and X > 1:
        effective_discount = (1 / X) * 100
        return f"{effective_discount:.2f}%"

    return ''

def procesar_respuesta_carrefour_json(productos_api, nombre_suc, provincia):
    """
    Procesa el JSON de búsqueda y aplica lógica de fallback para precios.
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
            if not seller: continue

            offer = seller.get('commertialOffer', {})
            list_price = offer.get('ListPrice')
            price = offer.get('Price')
            stock = offer.get('AvailableQuantity', 0)

            if (not list_price or list_price == 0) and (not price or price == 0): continue
            if stock <= 0: continue

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

            descuento_calculado = calculate_effective_discount_percentage(promo_name)
            precio_fleje = float(list_price) if list_price is not None else float(price)
            precio_dinamizado = float(price) if price is not None else 0.0

            # Aplicar descuento manualmente si el API devuelve precios iguales pero hay promo
            if precio_dinamizado == precio_fleje and descuento_calculado:
                try:
                    pct = float(descuento_calculado.replace('%', ''))
                    precio_dinamizado = round(precio_fleje * (1 - pct / 100), 2)
                except:
                    pass

            lista_productos.append({
                'sucursal': nombre_suc,
                'provincia': provincia,
                'codinterno': ean or item_id,
                'descripcion': product_name,
                'marca_desc': brand,
                'precio_anterior': precio_fleje,
                'precio_promo': precio_dinamizado,
                'cantidad_promo': promo_name,
                'descuento_porcentaje_promo': descuento_calculado,
                'Cadena': 'Carrefour',
                'fecha_exportacion': pd.Timestamp.now().strftime("%Y-%m-%d"),
            })

    return lista_productos

def fetch_single_search_with_prices(params, id_sucursal_cookie, nombre_suc, provincia):
    """
    Ejecuta búsqueda de catálogo con cookie de sucursal.
    """
    url = f"{URL_BASE_BUSQUEDA}{params}"
    headers_con_cookie = {**HEADERS_CARREFOUR, 'Cookie': f'vtex_segment={id_sucursal_cookie}'}
    time.sleep(random.uniform(0.5, 1.5))

    try:
        response = requests.get(url, headers=headers_con_cookie, timeout=15, verify=False)
        response.raise_for_status()
        productos_json = response.json()
        return procesar_respuesta_carrefour_json(productos_json, nombre_suc, provincia) if productos_json else []
    except:
        return []

def fetch_and_process_carrefour_prices_parallel(master_items_carrefour, nombre_suc, provincia, id_sucursal_cookie, status_box, progress_bar, current_step, total_steps):
    """
    VERSIÓN OPTIMIZADA: Ejecuta búsquedas de categoría con cookie en paralelo.
    """
    status_box.write(f"→ Iniciando búsquedas optimizadas para Carrefour {nombre_suc}...")
    lista_de_listas = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(fetch_single_search_with_prices, p, id_sucursal_cookie, nombre_suc, provincia): p
            for p in BUSQUEDAS_CARREFOUR
        }
        for future in as_completed(futures):
            res = future.result()
            if res: lista_de_listas.append(res)

    lista_final = [item for sublist in lista_de_listas for item in sublist]

    if not lista_final:
        status_box.write(f"→ Carrefour {nombre_suc}: sin productos.")
        return pd.DataFrame(), current_step

    df_sucursal = pd.DataFrame(lista_final)
    df_sucursal.drop_duplicates(subset=['codinterno'], keep='first', inplace=True)
    
    df_sucursal['precio_anterior'] = pd.to_numeric(df_sucursal['precio_anterior'], errors='coerce').fillna(0.0)
    df_sucursal['precio_promo'] = pd.to_numeric(df_sucursal['precio_promo'], errors='coerce').fillna(0.0)

    status_box.write(f"→ Finalizado Carrefour {nombre_suc}. {len(df_sucursal)} productos únicos.")
    return df_sucursal, current_step