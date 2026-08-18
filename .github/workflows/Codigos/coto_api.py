import requests
import pandas as pd
import json
import time

# --- CONSTANTES DE COTO ---
# Obtenidas de los nodos 'Skus 0 a N' del JSON de n8n
URL_BASE_COTO = "https://www.cotodigital.com.ar/sitios/cdigi/categoria/"
# IDs de las categorías de bebidas que escanea el flujo de n8n:
# 1. Gaseosas (N-n4l4r5)
# 2. Aguas saborizadas (N-rtdaup)
# 3. Bebidas isotónicas (N-pz126)
# 4. Energizantes (N-1js4wik)
# 5. Cervezas (N-137sk0z)
IDS_CATEGORIAS_COTO = [
    "catalogo-bebidas-bebidas-con-alcohol-cervezas/_/N-137sk0z"
]
# Parámetros comunes de la URL (Nrpp=153 para cantidad de ítems)
URL_PARAMS = "?format=json&Nrpp=1000&idSucursal="

# Headers que se envían en el flujo de n8n
HEADERS_COTO = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*'
}
# -------------------------

def fetch_data_coto(id_sucursal, categoria_id, status_box):
    """
    Performs the HTTP request to the Coto API for a specific store and category.
    
    id_sucursal: The Coto store ID (e.g., '204').
    categoria_id: The category URL segment.
    status_box: Streamlit status object for progress display.
    """
    
    url_completa = f"{URL_BASE_COTO}{categoria_id}{URL_PARAMS}{id_sucursal}"
    
    status_box.write(f"  -> Llamando a Coto API para Sucursal {id_sucursal}, Categoría {categoria_id.split('/_')[0]}...")
    
    try:
        # Se realiza una solicitud GET, simulando el nodo httpRequest
        # AÑADIDO: verify=False para ignorar el error de verificación SSL
        response = requests.get(url_completa, headers=HEADERS_COTO, timeout=10, verify=False)
        response.raise_for_status() 
        
        json_data = response.json()
        return json_data
        
    except requests.exceptions.RequestException as e:
        status_box.error(f"  ❌ Error al llamar a Coto API para Suc. {id_sucursal}: {e}")
        return None
    
    finally:
        # Good practice: add a small delay
        time.sleep(1) 


def procesar_respuesta_coto_json(json_data, nombre_suc, provincia):
    """
    Processes the Coto JSON response into a clean DataFrame.
    
    Implementa lógica de fallback: primero intenta el índice [2] de 'Main', 
    luego el índice [1] si no encuentra productos (para categorías como Cervezas).
    """
    
    productos_json = []

    def _extraer_productos_de_indice(data, index):
        """Helper para extraer productos de un índice específico de 'Main'."""
        try:
            # RUTA: json_data.contents[0].Main[index].contents[0].records
            # El path al arreglo de productos se busca en el índice dado (index)
            return data.get('contents', [None])[0] \
                       .get('Main', [None, None, None, None])[index] \
                       .get('contents', [None])[0] \
                       .get('records', [])
        except (AttributeError, IndexError):
            return []

    # 1. Intentar el índice [2] (Ruta estándar para la mayoría de categorías)
    productos_json = _extraer_productos_de_indice(json_data, 2)
    
    # 2. Si no hay productos, intentar el índice [1] (Fallback, probable para Cervezas)
    if not productos_json:
        productos_json = _extraer_productos_de_indice(json_data, 1)
        
    # Si después de ambos intentos no hay productos, devolver un DataFrame vacío.
    if not productos_json:
        return pd.DataFrame()
    
    lista_productos = []

    for prod in productos_json:
        # General product attributes
        prod_attrs = prod.get('attributes', {})
        # SKU attributes (first record)
        first_record = prod.get('records', [{}])[0]
        sku_attrs = first_record.get('attributes', {})
        
        # Discount extraction logic (from n8n's Code node)
        dto_json_str = sku_attrs.get('product.dtoDescuentos', ['[]'])[0]
        try:
            descuento = json.loads(dto_json_str)[0] if json.loads(dto_json_str) else {}
        except (json.JSONDecodeError, IndexError):
            descuento = {}

        # Safely convert price fields to float, defaulting to 0.0
        try:
            precio_anterior = float(sku_attrs.get('sku.activePrice', ['0.0'])[0])
        except ValueError:
            precio_anterior = 0.0
            
        try:
            precio_promo = float(descuento.get('precioDescuento', 0.0))
        except ValueError:
            precio_promo = 0.0
            
        # Mapeo de campos a los nombres estandarizados (similar a la Cooperativa)
        registro = {
            'sucursal': nombre_suc,
            'provincia': provincia,
            
            # Data fields from Coto's API
            'codinterno': sku_attrs.get('product.eanPrincipal', ['N/D'])[0], 
            'descripcion': prod_attrs.get('product.displayName', ['N/D'])[0],
            'marca_desc': sku_attrs.get('product.brand', ['N/D'])[0],
            
            'precio_anterior': precio_anterior,
            'precio_promo': precio_promo,
            
            # Promo details
            'cantidad_promo': descuento.get('textoDescuento', ''), 
            # Note: n8n flow maps sku.quantity to descuento_porcentaje_promo, replicating that here
            'descuento_porcentaje_promo': sku_attrs.get('sku.quantity', [None])[0] or '', 
            'precio_x_lt': sku_attrs.get('sku.referencePrice', [None])[0], 
            
            # Required fields for the multi-scraper framework
            'Cadena': 'Coto', 
            'fecha_exportacion': pd.Timestamp.now().strftime("%Y-%m-%d"),
        }
        
        lista_productos.append(registro)
        
    df = pd.DataFrame(lista_productos)
    return df