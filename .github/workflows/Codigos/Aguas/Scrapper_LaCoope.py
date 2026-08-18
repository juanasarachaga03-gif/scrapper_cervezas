import pandas as pd
import requests
from datetime import datetime
import time
import io 
import json 
import streamlit as st 

# --- Deshabilitar warnings de SSL ---
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- ID DE BÚSQUEDA PARA AGUAS ---
# Actualizado según tu corrección para la categoría de aguas
IDS_BUSQUEDA_COOP = ["1565"]

def fetch_data_sucursal(codigo_cookie_string, id_busqueda, status_box):
    """
    Hace la llamada POST a la API para una sucursal y el ID de aguas (1565).
    Usa el 'codigo_cookie_string' extraído del Excel.
    """
    
    cache_buster = int(time.time() * 1000)
    url = f"https://api.lacoopeencasa.coop/api/articulos/pagina?cachebust={cache_buster}"
    
    # 1. Limpieza de la cookie
    codigo_cookie_string_limpio = codigo_cookie_string.strip()
    
    # 2. Definición de headers
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Origin": "https://www.lacoopeencasa.coop",
        "Referer": "https://www.lacoopeencasa.coop/",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "close"
    }
    
    # 3. Diccionario de cookies nativo de requests
    cookie_data = {
        "_lcec_linf": codigo_cookie_string_limpio
    }
    
    # Payload ajustado para la categoría solicitada
    payload = {
        "id_busqueda": str(id_busqueda),
        "pagina": 0,
        "filtros": {
            "preciomenor": -1, 
            "preciomayor": 99999, 
            "marca": [], 
            "categoria": [], 
            "tipo_seleccion": "categoria", 
            "modificado": False, 
            "ofertas": False, 
            "filtros_gramaje": [], 
            "primer_filtro": ""
        },
        "cant_articulos": 500
    }
    
    try:
        response = requests.post(
            url, 
            headers=headers, 
            cookies=cookie_data, 
            json=payload, 
            timeout=30, 
            verify=False 
        )
        response.raise_for_status() 
        return response.json()
    except requests.exceptions.RequestException as e:
        status_box.warning(f"   ⚠️ [La Coope] Error en API (Cat: {id_busqueda}): {e}")
        return None

def procesar_respuesta_json(json_data, sucursal, provincia):
    """
    Transforma el JSON de la API en un DataFrame limpio, replicando la lógica de n8n.
    """
    if not json_data or 'datos' not in json_data or 'articulos' not in json_data['datos']:
        return pd.DataFrame() 

    articulos_lista = json_data['datos']['articulos']
    if not articulos_lista:
        return pd.DataFrame()

    df = pd.json_normalize(articulos_lista)
    fecha_exportacion = datetime.now().strftime("%d-%m-%Y")
    
    # Homologación de columnas
    if 'cod_interno' in df.columns:
        df = df.rename(columns={'cod_interno': 'codinterno'})
    
    # Lógica para marca_desc
    if 'marca_desc' in df.columns and 'marca' in df.columns:
        df['marca_desc'] = df['marca_desc'].fillna(df['marca'])
    elif 'marca' in df.columns:
        df = df.rename(columns={'marca': 'marca_desc'})
    
    columnas_api = [
        'codinterno', 'descripcion', 'marca_desc', 
        'precio_anterior', 'precio_promo', 'cantidad_promo',
        'vigencia_promo_desde', 'vigencia_promo', 
        'descuento_porcentaje_promo'
    ]
    columnas_existentes = [col for col in columnas_api if col in df.columns]
    
    # Uso de .copy() para evitar SettingWithCopyWarning
    df_final = df[columnas_existentes].copy()

    df_final['sucursal'] = sucursal
    df_final['provincia'] = provincia
    df_final['fecha_exportacion'] = fecha_exportacion

    # Conversión numérica
    for col in ['precio_anterior', 'precio_promo', 'descuento_porcentaje_promo']:
        if col in df_final.columns:
            df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0.0)

    columnas_finales_ordenadas = [
        'codinterno', 'descripcion', 'precio_anterior', 'precio_promo',
        'marca_desc', 'cantidad_promo', 'vigencia_promo_desde',
        'vigencia_promo', 'sucursal', 'descuento_porcentaje_promo',
        'provincia', 'fecha_exportacion'
    ]
    
    columnas_reales = [col for col in columnas_finales_ordenadas if col in df_final.columns]
    return df_final[columnas_reales]