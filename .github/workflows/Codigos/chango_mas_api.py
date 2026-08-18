import pandas as pd
import time
import requests
from datetime import datetime

# --- Deshabilitar warnings de SSL ---
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# ------------------------------------

# --- TÉRMINOS DE BÚSQUEDA (Replicado de N8N) ---
IDS_CATEGORIAS_CHANGOMAS = [
    "cervezas",
    "cerveza",
    "beer",
    "ipa",
    "lager"
]
# -------------------------------------------------

def fetch_data_changomas(id_tienda_cookie, termino_busqueda, status_box):
    """
    Realiza el scraping para Chango Mas (MasOnline).
    id_tienda_cookie: Es el 'Codigo Suc' del Excel, para la cookie 'vtex_segment'.
    termino_busqueda: El string de búsqueda (ej: "gaseosas").
    """
    
    # Preparamos la sesión de requests
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        # --- MODIFICACIÓN: URL Base de Chango Mas ---
        "Origin": "https://www.masonline.com.ar",
        "Referer": "https://www.masonline.com.ar/"
    })
    
    # El 'Codigo Suc' es el valor de la cookie vtex_segment
    session.cookies.set("vtex_segment", id_tienda_cookie)
    
    all_products_for_term = []
    
    # --- Lógica de Paginación VTEX (50 items) ---
    from_val = 0
    to_val = 49 
    
    while True:
        # --- MODIFICACIÓN: URL Base de Chango Mas ---
        url = f"https://www.masonline.com.ar/api/catalog_system/pub/products/search/{termino_busqueda}?_from={from_val}&_to={to_val}"
        
        try:
            response = session.get(url, timeout=30, verify=False)
            response.raise_for_status()
            
            response_json = response.json()
            
            if not response_json:
                break
                
            all_products_for_term.extend(response_json)
            
            if len(response_json) < 50:
                break
                
            from_val += 50
            to_val += 50
            
            time.sleep(1) # Pausa

        except requests.exceptions.RequestException as e:
            st.warning(f"   ⚠️ [Chango Mas] Error en API (Término: {termino_busqueda}, Página: {from_val}): {e}")
            break 
            
    return all_products_for_term


def procesar_respuesta_changomas_json(json_data, sucursal, provincia):
    """
    (Función Completa)
    Procesa la LISTA de productos devuelta por fetch_data_changomas.
    Replica la lógica de 'Code1' (Parseo) y 'Code3' (Filtro) de N8N.
    """
    
    if not json_data:
        return pd.DataFrame()

    parsed_items = []
    fecha_exportacion = datetime.now().strftime("%d-%m-%Y")

    # --- 1. Lógica de Parseo (N8N 'Code1') ---
    for p in json_data:
        try:
            item = p.get('items', [{}])[0]
            offer = item.get('sellers', [{}])[0].get('commertialOffer', {})
            
            ean = item.get('ean')
            if not ean and item.get('referenceId'):
                ean = item.get('referenceId', [{}])[0].get('Value')

            listPrice = offer.get('ListPrice')
            price = offer.get('Price')
            # --- MODIFICACIÓN: N8N de Chango Mas no extrae 'AvailableQuantity' ---

            parsed_items.append({
                'EAN': ean,
                'Descripcion': p.get('productName'),
                'Marca': p.get('brand'),
                'ListPrice': listPrice,
                'Price': price,
                # 'AvailableQuantity': No se extrae
                'sucursal': sucursal,
                'provincia': provincia,
                'fecha_exportacion': fecha_exportacion
            })
        except Exception:
            continue
            
    if not parsed_items:
        return pd.DataFrame()

    # --- 2. Lógica de Filtro (N8N 'Code3') ---
    # MODIFICACIÓN: Solo filtra por precio, no por stock.
    filtered_items = [
        item for item in parsed_items 
        if item.get('ListPrice') and item.get('ListPrice') > 0
    ]
    
    # MODIFICACIÓN: N8N de Chango Mas no aplica deduplicación.
    
    if not filtered_items:
        return pd.DataFrame()

    # --- 3. Crear y Renombrar DataFrame ---
    df = pd.DataFrame(filtered_items)
    
    df = df.rename(columns={
        'EAN': 'codinterno',
        'Descripcion': 'descripcion',
        'Marca': 'marca_desc',
        'ListPrice': 'precio_anterior',
        'Price': 'precio_promo'
    })
    
    for col in ['precio_anterior', 'precio_promo']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    columnas_finales_ordenadas = [
        'codinterno', 'descripcion', 'precio_anterior', 'precio_promo',
        'marca_desc', 'sucursal', 'provincia', 'fecha_exportacion'
    ]
    
    columnas_reales = [col for col in columnas_finales_ordenadas if col in df.columns]
    
    return df[columnas_reales]