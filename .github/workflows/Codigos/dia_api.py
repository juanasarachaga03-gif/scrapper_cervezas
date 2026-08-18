import pandas as pd
import time
import requests
from datetime import datetime

# --- Deshabilitar warnings de SSL ---
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# ------------------------------------

# --- CORRECCIÓN: Definir los TÉRMINOS DE BÚSQUEDA ---
# Replicamos la lista de la API de N8N. El orquestador
# iterará sobre esta lista.
IDS_CATEGORIAS_DIA = [
    "cerveza",
    "cervezas",
    "beer",
    "ipa",
    "lager",
    "stout",
    "porter",
    "birra"
]
# -------------------------------------------------

def fetch_data_dia(id_tienda_cookie, termino_busqueda, status_box):
    """
    Realiza el scraping para un término de búsqueda y una sucursal (cookie) específicos,
    manejando la paginación.
    
    id_tienda_cookie: Es el 'Codigo Suc' del Excel, que se usa para la cookie 'vtex_segment'.
    termino_busqueda: El string de búsqueda (ej: "gaseosa").
    """
    
    # Preparamos la sesión de requests
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Origin": "https://diaonline.supermercadosdia.com.ar",
        "Referer": "https://diaonline.supermercadosdia.com.ar/"
    })
    
    # El 'Codigo Suc' es el valor de la cookie vtex_segment
    session.cookies.set("vtex_segment", id_tienda_cookie)
    
    all_products_for_term = []
    
    # --- Lógica de Paginación (Replicada de N8N) ---
    # VTEX usa 'from' (inicio) y 'to' (fin). Pedimos de a 50 (máx permitido)
    from_val = 0
    to_val = 49 # Los índices de VTEX son inclusivos (0-49 son 50 items)
    
    while True:
        url = f"https://diaonline.supermercadosdia.com.ar/api/catalog_system/pub/products/search/{termino_busqueda}?_from={from_val}&_to={to_val}"
        
        try:
            response = session.get(url, timeout=30, verify=False)
            response.raise_for_status()
            
            response_json = response.json()
            
            # Si la respuesta está vacía, significa que no hay más páginas
            if not response_json:
                break
                
            all_products_for_term.extend(response_json)
            
            # Si trae menos de 50 items, es la última página
            if len(response_json) < 50:
                break
                
            # Avanzamos a la siguiente página
            from_val += 50
            to_val += 50
            
            time.sleep(1) # Pausa para no saturar la API

        except requests.exceptions.RequestException as e:
            st.warning(f"   ⚠️ [DIA] Error en API (Término: {termino_busqueda}, Página: {from_val}): {e}")
            break # Salimos del bucle de paginación si hay un error
            
    return all_products_for_term


def procesar_respuesta_dia_json(json_data, sucursal, provincia):
    """
    (Función Completa)
    Procesa la LISTA de productos devuelta por fetch_data_dia.
    Replica la lógica de 'Code1' (Parseo) y 'Code3' (Filtro y Deduplicación) de N8N.
    """
    
    if not json_data:
        return pd.DataFrame()

    parsed_items = []
    fecha_exportacion = datetime.now().strftime("%d-%m-%Y")

    # --- 1. Lógica de Parseo (Replicada de N8N 'Code1') ---
    for p in json_data:
        try:
            # Navegación segura por el JSON
            item = p.get('items', [{}])[0]
            offer = item.get('sellers', [{}])[0].get('commertialOffer', {})
            
            # Extraer EAN (con fallback a referenceId)
            ean = item.get('ean')
            if not ean and item.get('referenceId'):
                ean = item.get('referenceId', [{}])[0].get('Value')

            listPrice = offer.get('ListPrice')
            price = offer.get('Price')
            availableQuantity = offer.get('AvailableQuantity')

            parsed_items.append({
                'EAN': ean,
                'Descripcion': p.get('productName'),
                'Marca': p.get('brand'),
                'ListPrice': listPrice,
                'Price': price,
                'AvailableQuantity': availableQuantity,
                'sucursal': sucursal,
                'provincia': provincia,
                'fecha_exportacion': fecha_exportacion
            })
        except Exception:
            # Si un producto tiene una estructura JSON rara, lo saltamos
            continue
            
    if not parsed_items:
        return pd.DataFrame()

    # --- 2. Lógica de Filtro y Deduplicación (Replicada de N8N 'Code3') ---
    
    # Filtro: Descartar si no tiene precio o stock
    filtered_items = [
        item for item in parsed_items 
        if item.get('ListPrice') and item.get('AvailableQuantity') and item.get('AvailableQuantity') > 0
    ]
    
    # Deduplicación: Por EAN (o Desc) + Sucursal
    seen = set()
    deduped_items = []
    for item in filtered_items:
        # Usamos EAN, pero si no existe, usamos Descripción como fallback
        key_part_1 = item.get('EAN') if item.get('EAN') else item.get('Descripcion')
        key = f"{key_part_1}|{item.get('sucursal')}"
        
        if key not in seen:
            seen.add(key)
            deduped_items.append(item)

    if not deduped_items:
        return pd.DataFrame()

    # --- 3. Crear y Renombrar DataFrame (Replicado de N8N Google Sheets) ---
    df = pd.DataFrame(deduped_items)
    
    # Renombramos columnas para que coincidan con el formato estándar
    df = df.rename(columns={
        'EAN': 'codinterno',
        'Descripcion': 'descripcion',
        'Marca': 'marca_desc',
        'ListPrice': 'precio_anterior',
        'Price': 'precio_promo'
    })
    
    # Aseguramos que los precios sean numéricos
    for col in ['precio_anterior', 'precio_promo']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    # Definimos el orden final de las columnas
    columnas_finales_ordenadas = [
        'codinterno', 'descripcion', 'precio_anterior', 'precio_promo',
        'marca_desc', 'sucursal', 'provincia', 'fecha_exportacion'
    ]
    
    # Filtramos solo las columnas que realmente existen (por si alguna falla)
    columnas_reales = [col for col in columnas_finales_ordenadas if col in df.columns]
    
    return df[columnas_reales]