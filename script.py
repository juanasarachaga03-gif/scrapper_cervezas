import pandas as pd
from datetime import datetime
import os
import io
import time
import json
import requests
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
import sys 
import os
from datetime import datetime
# --- IMPORTACIÓN PARA PARALELISMO ---
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIG LOCAL SIMPLE ---
PROJECT_PATH = os.path.dirname(os.path.abspath(__file__))

SUCURSALES_FILE_PATH = os.path.join(PROJECT_PATH, 'Maestros2.xlsx')
MODULOS_PATH = os.path.join(PROJECT_PATH, 'Codigos')
HISTORY_FILE = os.path.join(PROJECT_PATH, 'scraper_historical_data_NABs_CZA.parquet')
OUTPUT_FOLDER = PROJECT_PATH
# Configuración de Email SMTP (usaremos Gmail)
SMTP_SERVER = None
# CORRECCIÓN: Puerto 465 (SSL) en lugar de 587 (TLS), para evitar bloqueos
SMTP_PORT = None

SMTP_EMAIL = None 
# ¡CONTRASEÑA DE APLICACIÓN ACTUALIZADA!
SMTP_PASSWORD = None
RECIPIENT_EMAIL = None 
# -----------------------------------------------------------------


# --- ADICIÓN DE LA RUTA DE MÓDULOS AL PATH DE PYTHON ---
# Esto permite que Python encuentre los archivos .py dentro de la carpeta 'Codigos'
if MODULOS_PATH not in sys.path:
    sys.path.append(MODULOS_PATH)
CONTROL_FILE = "ultima_ejecucion.txt"

hoy = datetime.now().strftime("%Y-%m-%d")

if os.path.exists(CONTROL_FILE):

    with open(
        CONTROL_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        ultima_fecha = f.read().strip()

    if ultima_fecha == hoy:

        print(
            "✅ El scraper ya fue ejecutado hoy."
        )

        raise SystemExit
    
# --- Módulos de Scraping (Importación de tus archivos existentes) ---
try:
    # Python ahora buscará estos archivos dentro de la carpeta 'Codigos'
    import la_cooperativa_api
    import dia_api
    import coto_api 
    import carrefour_api 
    import chango_mas_api 
    import vea_api 
    import toledo_api
    import jumbo_api
    import disco_api
    # --- AÑADIDO: Importar Libertad
    import libertad_api
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError as e:
    # Si falla la importación, el mensaje indica qué carpeta revisar
    print(f"Error fatal de importación. Asegúrate que la carpeta '{MODULOS_PATH}' contenga todos los archivos API. Detalle: {e}")
    sys.exit(1)
# -------------------------------------------------------------------

# --- FUNCIONES DE SOPORTE Y LOGGER DE CONSOLA ---

def log_message(message):
    """Función de logging simple para la ejecución por consola."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

class ConsoleLogger:
    """Clase para simular los métodos de Streamlit (write, warning, etc.) en la consola."""
    def write(self, message):
        log_message(message)
    def warning(self, message):
        log_message(f"⚠️ {message}")
    def error(self, message):
        log_message(f"❌ {message}")
    # Métodos dummy para las funciones que usan las APIs (como progress/update)
    def progress(self, *args, **kwargs):
        # El 'toledo_api' llama a progress con 'text', lo capturamos
        if 'text' in kwargs:
            log_message(f"  ... {kwargs['text']}")
        pass
    def info(self, message):
        # Captura el log .info() de toledo_api
        log_message(f"ℹ️ {message}")
    def success(self, *args, **kwargs):
        pass
    def update(self, *args, **kwargs):
        pass
    def _call_(self, *args, **kwargs):
        pass

console_logger = ConsoleLogger()
# -----------------------------------------------------------------


def cargar_datos_historicos(file_path):
    """Carga el DataFrame histórico desde Parquet, si existe."""
    if os.path.exists(file_path):
        try:
            return pd.read_parquet(file_path)
        except Exception as e:
            log_message(f"Error al cargar el histórico: {e}. Se usará un historial vacío.")
            return pd.DataFrame()
    return pd.DataFrame()

# --- FUNCIÓN MODIFICADA PARA ACUMULAR DATOS ---
def guardar_datos_historicos(df_to_save, file_path):
    """Carga el histórico existente, añade los nuevos datos (df_to_save) y guarda el historial completo."""
    try:
        # 1. Cargar el historial existente
        df_historico_existente = cargar_datos_historicos(file_path) 
        
        # 2. Definir las columnas clave para el historial de precios
        # MODIFICACIÓN: Se añade NODO al historial
        cols_hist = [
            'Cadena', 'Codigo Suc', 'codinterno', 'descripcion', 
            'precio_promo', 'fecha_exportacion', 'precio_anterior', 'cantidad_promo',
            'NODO' 
        ]
        
        # 3. Preparar los datos de HOY (df_to_save)
        # Aseguramos que solo guardamos las columnas clave que definen un registro de precio
        df_hoy = df_to_save[[col for col in cols_hist if col in df_to_save.columns]].copy()
        
        # 4. Concatenar (acumular) los datos de hoy con el historial existente
        df_acumulado = pd.concat([df_historico_existente, df_hoy], ignore_index=True)
        
        # 5. Guardar el DataFrame ACUMULADO en Parquet
        # Opcional: Eliminar duplicados si solo quieres una entrada por día/producto
        df_acumulado.drop_duplicates(
            subset=['Cadena', 'Codigo Suc', 'codinterno', 'fecha_exportacion'], 
            keep='last', 
            inplace=True
        )
        
        df_acumulado.to_parquet(file_path, index=False)
        return True
    except Exception as e:
        log_message(f"Error al guardar el archivo histórico acumulado: {e}")
        return False

def procesar_datos_historicos(df_actual, df_historico):
    """
    Compara el DataFrame actual con el histórico para calcular cambios de precio.
    (Versión robusta que maneja archivos históricos "viejos" sin 'precio_anterior')
    
    IMPORTANTE: Si el histórico contiene múltiples fechas, este merge 
    tomará la PRIMERA coincidencia para la comparación "ayer". 
    Para garantizar que tome la ÚLTIMA fecha, se recomienda pre-procesar df_historico.
    """
    df_result = df_actual.copy()
    
    # 1. Inicializar columnas históricas (crucial para la primera ejecución)
    df_result['precio_promo_ayer'] = 0.0
    df_result['Fecha Anterior'] = 'N/A'
    df_result['Precio Fleje Anterior'] = 0.0
    df_result['Promoción Desc Anterior'] = 'N/A'
    df_result['cambio_precio'] = 0.0

    if df_historico.empty:
        return df_result

    # --- LÓGICA AGREGADA: Filtrar el Histórico a la ÚLTIMA FECHA DISPONIBLE ---
    # Esto garantiza que la comparación sea Hoy vs. el ÚLTIMO día de registro.
    if 'fecha_exportacion' in df_historico.columns:
        df_historico['fecha_exportacion'] = pd.to_datetime(df_historico['fecha_exportacion'], errors='coerce')
        ultima_fecha = df_historico['fecha_exportacion'].max()
        df_historico_ultimo_dia = df_historico[df_historico['fecha_exportacion'] == ultima_fecha].copy()
        log_message(f"Comparando contra la última fecha histórica registrada: {ultima_fecha.strftime('%Y-%m-%d')}.")
    else:
        df_historico_ultimo_dia = df_historico.copy()
    
    # Columnas a usar del histórico (añadimos precio_anterior y cantidad_promo)
    cols_to_keep = [
        'Cadena', 'Codigo Suc', 'codinterno', 'precio_promo', 
        'fecha_exportacion', 'precio_anterior', 'cantidad_promo'
    ]
    
    # Usamos el historial filtrado (df_historico_ultimo_dia) para el merge
    cols_existentes_hist = [col for col in cols_to_keep if col in df_historico_ultimo_dia.columns]
    
    df_ayer = df_historico_ultimo_dia[cols_existentes_hist].rename(columns={
        'precio_promo': 'precio_promo_ayer_temp',
        'fecha_exportacion': 'fecha_ayer_temp',
        'precio_anterior': 'precio_anterior_ayer_temp',
        'cantidad_promo': 'promo_desc_ayer_temp'
    })

    # Usar el identificador compuesto para el merge
    df_result['id_producto_sucursal'] = df_result['Cadena'].astype(str) + '' + df_result['Codigo Suc'].astype(str) + '' + df_result['codinterno'].astype(str)
    df_ayer['id_producto_sucursal'] = df_ayer['Cadena'].astype(str) + '' + df_ayer['Codigo Suc'].astype(str) + '' + df_ayer['codinterno'].astype(str)

    # Definir las columnas a mergear (SOLO las que df_ayer realmente tiene)
    cols_to_merge = [col for col in [
        'id_producto_sucursal', 'precio_promo_ayer_temp', 'fecha_ayer_temp',
        'precio_anterior_ayer_temp', 'promo_desc_ayer_temp'
    ] if col in df_ayer.columns]
    
    df_unificado = pd.merge(
        df_result, 
        df_ayer[cols_to_merge], 
        on='id_producto_sucursal', 
        how='left'
    )
    
    # 2. Calcular el cambio y rellenar NAs
    # Esta columna siempre existirá gracias al merge
    if 'precio_promo_ayer_temp' in df_unificado.columns:
        df_unificado['precio_promo_ayer'] = df_unificado['precio_promo_ayer_temp'].fillna(0.0)
    
    df_unificado['precio_promo'] = pd.to_numeric(df_unificado['precio_promo'], errors='coerce').fillna(0.0)
    df_unificado['cambio_precio'] = df_unificado['precio_promo'] - df_unificado['precio_promo_ayer']
    df_unificado['cambio_precio_anterior'] = 0.0 # Se mantiene por compatibilidad
    
    # Rellenar las nuevas columnas históricas, validando si existen
    if 'fecha_ayer_temp' in df_unificado.columns:
        # Aseguramos que la fecha se muestre como string en el reporte final
        df_unificado['Fecha Anterior'] = df_unificado['fecha_ayer_temp'].dt.strftime('%Y-%m-%d').fillna('N/A')
    
    if 'precio_anterior_ayer_temp' in df_unificado.columns:
        df_unificado['Precio Fleje Anterior'] = df_unificado['precio_anterior_ayer_temp'].fillna(0.0)
        
    if 'promo_desc_ayer_temp' in df_unificado.columns:
        df_unificado['Promoción Desc Anterior'] = df_unificado['promo_desc_ayer_temp'].fillna('N/A')
    
    
    # 3. Limpiar columnas temporales
    cols_to_drop = [
        'id_producto_sucursal', 'precio_promo_ayer_temp', 'fecha_ayer_temp',
        'precio_anterior_ayer_temp', 'promo_desc_ayer_temp'
    ]
    df_unificado.drop(columns=[col for col in cols_to_drop if col in df_unificado.columns], inplace=True, errors='ignore')
    
    return df_unificado


def to_excel_bytes(df):
    """Convierte un DataFrame a bytes de Excel."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Resultados')
    processed_data = output.getvalue()
    return processed_data

# -----------------------------------------------------------------

def send_email_report(df_results, excel_bytes):
    log_message("📩 Envío de email desactivado")
    return

    # Aseguramos que las columnas existan (para el cálculo de KPIs)
    if 'precio_promo_ayer' not in df_results.columns:
        df_results['precio_promo_ayer'] = 0.0
    if 'cambio_precio' not in df_results.columns:
        df_results['cambio_precio'] = 0.0

    msg = MIMEMultipart()
    msg['From'] = SMTP_EMAIL
    msg['To'] = RECIPIENT_EMAIL
    
    date_str = datetime.now().strftime("%d/%m/%Y")
    
    # Calcular KPIs básicos para el cuerpo del correo
    df_con_historial = df_results[df_results['precio_promo_ayer'] > 0].copy() 
    total_cambios = len(df_con_historial[(df_con_historial['cambio_precio'] != 0)])
    total_subidas = len(df_con_historial[df_con_historial['cambio_precio'] > 0])
    total_bajadas = len(df_con_historial[df_con_historial['cambio_precio'] < 0])
    
    # Definir Asunto y Cuerpo del correo (MODIFICADO)
    msg['Subject'] = f"Reporte Diario de Scraper Multi-Cadena NABs + CZA ({date_str})"
    
    body = f"""
    ¡Hola!
    
    Adjunto encontrarás el reporte diario de precios de las categorías *NABs + Cervezas* de las cadenas de supermercados al {date_str}.
    
    --- Resumen de Movimientos (comparado con el último día de registro) ---
    - Total de productos con historial: {len(df_con_historial):,}
    - Productos con cambio de precio: {total_cambios:,}
    - De los cuales, Subidas: {total_subidas:,}
    - De los cuales, Bajadas: {total_bajadas:,}
    
    El archivo adjunto 'Reporte_{datetime.now().strftime('%Y%m%d')}.xlsx' contiene todos los detalles.
    
    ¡Saludos!
    """
    msg.attach(MIMEText(body, 'plain'))
    
    # Adjuntar el archivo Excel
    excel_attachment = MIMEApplication(excel_bytes, _subtype="xlsx")
    excel_attachment.add_header('Content-Disposition', 'attachment', filename=f"Reporte_{datetime.now().strftime('%Y%m%d')}.xlsx")
    msg.attach(excel_attachment)
    
    # Enviar el correo
    try:
        # Usamos SMTP_SSL y puerto 465
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, RECIPIENT_EMAIL, msg.as_string())
        log_message("✅ Correo enviado con éxito (Puerto 465/SSL).")
    except Exception as e:
        log_message(f"❌ Error al enviar el correo: {e}")

# ---
# --- INICIO DE LA LÓGICA DE OPTIMIZACIÓN (NIVEL 1 + 2)
# ---

def process_single_branch(row, master_items_carrefour, master_items_vea, master_items_jumbo, master_items_disco, status_proxy):
    """
    Función que procesa UNA SOLA SUCURSAL (una fila del Excel).
    Esta función está diseñada para ser llamada en paralelo.
    """
    cadena = row['Cadena']
    nombre_suc = row['Nombre Suc']
    codigo_suc = str(row['Codigo Suc'])
    provincia = row['Provincia']
    # --- Capturar NODO ---
    nodo = row.get('NODO', 'N/A')
    
    log_message(f"  → Iniciando Hilo para: {nombre_suc} ({cadena})...")
    df_sucursal = pd.DataFrame()
    lista_dfs_parciales = [] # Lista para recolectar DFs de categorías
    
    try:
        if cadena == 'La Cooperativa':
            with ThreadPoolExecutor(max_workers=len(la_cooperativa_api.IDS_BUSQUEDA_COOP)) as executor:
                futures = {
                    executor.submit(la_cooperativa_api.fetch_data_sucursal, codigo_suc, id_b, status_proxy): id_b
                    for id_b in la_cooperativa_api.IDS_BUSQUEDA_COOP
                }
                for future in as_completed(futures):
                    json_data = future.result()
                    if json_data:
                        df_temp = la_cooperativa_api.procesar_respuesta_json(json_data, nombre_suc, provincia)
                        lista_dfs_parciales.append(df_temp)
       
        elif cadena == 'Dia':
            with ThreadPoolExecutor(max_workers=len(dia_api.IDS_CATEGORIAS_DIA)) as executor:
                futures = {
                    executor.submit(dia_api.fetch_data_dia, codigo_suc, termino, status_proxy): termino
                    for termino in dia_api.IDS_CATEGORIAS_DIA
                }
                for future in as_completed(futures):
                    json_data = future.result()
                    if json_data:
                        df_temp = dia_api.procesar_respuesta_dia_json(json_data, nombre_suc, provincia)
                        lista_dfs_parciales.append(df_temp)
        
        elif cadena == 'Coto':
            with ThreadPoolExecutor(max_workers=len(coto_api.IDS_CATEGORIAS_COTO)) as executor:
                futures = {
                    executor.submit(coto_api.fetch_data_coto, codigo_suc, cat_id, status_proxy): cat_id
                    for cat_id in coto_api.IDS_CATEGORIAS_COTO
                }
                for future in as_completed(futures):
                    json_data = future.result()
                    if json_data:
                        df_temp = coto_api.procesar_respuesta_coto_json(json_data, nombre_suc, provincia)
                        lista_dfs_parciales.append(df_temp)
         
        elif cadena == 'Chango Mas':
            with ThreadPoolExecutor(max_workers=len(chango_mas_api.IDS_CATEGORIAS_CHANGOMAS)) as executor:
                futures = {
                    executor.submit(chango_mas_api.fetch_data_changomas, codigo_suc, termino, status_proxy): termino
                    for termino in chango_mas_api.IDS_CATEGORIAS_CHANGOMAS
                }
                for future in as_completed(futures):
                    json_data = future.result()
                    if json_data:
                        df_temp = chango_mas_api.procesar_respuesta_changomas_json(json_data, nombre_suc, provincia)
                        lista_dfs_parciales.append(df_temp)
        
        elif cadena == 'Toledo':
            # Tu 'toledo_api.py' maneja su propio bucle de categorías internamente.
            df_sucursal = toledo_api.fetch_and_process_toledo_prices(
                nombre_suc, 
                nodo, 
                provincia, 
                status_proxy, # Simula status_box
                status_proxy  # Simula progress_bar
            )
           
        elif cadena == 'Libertad':
            # Se asume que usa una función similar a Toledo/Vea que devuelve el DF de una vez.
            df_sucursal = libertad_api.fetch_and_process_libertad_prices(
                nombre_suc, 
                nodo, 
                provincia, 
                status_proxy, # Simula status_box
                status_proxy  # Simula progress_bar
            )
        
        elif cadena == 'Carrefour':
            # Carrefour ya es paralelo por diseño (usa el catálogo maestro)
            total_items_carrefour = len(master_items_carrefour)
            df_sucursal, _ = carrefour_api.fetch_and_process_carrefour_prices_parallel(
                master_items_carrefour, nombre_suc, provincia, codigo_suc, 
                status_proxy, status_proxy, 0, total_items_carrefour
            )
    
        elif cadena == 'Vea':
            # Vea ya es paralelo por diseño (usa el catálogo maestro)
            codigo_ccx = str(row.get('Codigo CCX', '')).strip()
            print("SUCURSAL:", nombre_suc)
            print("CODIGO_CCX:", codigo_ccx)
            if not codigo_ccx or codigo_ccx.lower() in ['none', 'nan', '']:
                log_message(f"  → Omitiendo Vea ({nombre_suc}): Falta el 'Codigo CCX'.")
                return pd.DataFrame() # Retornamos un DF vacío
                
            total_items_vea = len(master_items_vea)
            df_sucursal, _ = vea_api.fetch_and_process_vea_prices_parallel(
                master_items_vea, nombre_suc, provincia, codigo_suc, codigo_ccx, 
                status_proxy, status_proxy, 0, total_items_vea
            )
            
        elif cadena == 'Jumbo':
            # Jumbo ya es paralelo por diseño (usa el catálogo maestro)
            codigo_ccx = str(row.get('Codigo CCX', '')).strip()
            if not codigo_ccx or codigo_ccx == 'None' or codigo_ccx == '':
                log_message(f"  → Omitiendo Jumbo ({nombre_suc}): Falta el 'Codigo CCX'.")
                return pd.DataFrame() # Retornamos un DF vacío
                
            total_items_jumbo = len(master_items_jumbo)
            df_sucursal, _ = jumbo_api.fetch_and_process_jumbo_prices_parallel(
                master_items_jumbo, nombre_suc, provincia, codigo_suc, codigo_ccx, 
                status_proxy, status_proxy, 0, total_items_jumbo
            )
        elif cadena == 'Disco':
            # Disco ya es paralelo por diseño (usa el catálogo maestro)
            codigo_ccx = str(row.get('Codigo CCX', '')).strip()
            if not codigo_ccx or codigo_ccx == 'None' or codigo_ccx == '':
                log_message(f"  → Omitiendo Disco ({nombre_suc}): Falta el 'Codigo CCX'.")
                return pd.DataFrame() # Retornamos un DF vacío
                
            total_items_disco = len(master_items_disco)
            df_sucursal, _ = disco_api.fetch_and_process_disco_prices_parallel(
                master_items_disco, nombre_suc, provincia, codigo_suc, codigo_ccx, 
                status_proxy, status_proxy, 0, total_items_disco
            )
        
        # Si usamos los hilos de categorías (Coto, Dia, etc.), concatenamos ahora
        if lista_dfs_parciales:
            df_sucursal = pd.concat(lista_dfs_parciales, ignore_index=True)
        if df_sucursal is None or df_sucursal.empty:
            log_message(f"❌ Falló: {cadena} - {nombre_suc}")    
        if not df_sucursal.empty:
            # Limpiar valores infinitos
            for col in ['precio_x_lt', 'precio_x_kg']:
                if col in df_sucursal.columns:
                    df_sucursal[col] = df_sucursal[col].replace([float('inf'), float('-inf')], 0)
            
            # --- NORMALIZACIÓN DE COLUMNAS (POST-SCRAPING) ---
            
            # 1. Definir mapeo de columnas (Interna -> Final)
            column_rename_map_pre = {
                'fecha_exportacion': 'Fecha extracción',
                'sucursal': 'Sucursal',
                'codinterno': 'EAN',
                'descripcion': 'Descripcion',
                'marca_desc': 'Marca',
                'precio_anterior': 'Precio Fleje',
                'precio_promo': 'Precio Dinamizado',
                'cantidad_promo': 'Promocion Desc',
                'vigencia_promo_desde': 'Inicio Promo',
                'vigencia_promo': 'Fin Promo'
            }
            df_sucursal.rename(columns=column_rename_map_pre, inplace=True)

            # 2. Asegurar columnas de metadatos (que los APIs no siempre ponen)
            df_sucursal['Codigo Suc'] = codigo_suc
            df_sucursal['Cadena'] = cadena
            df_sucursal['NODO'] = nodo
            
            # Si el API no puso 'Sucursal' (ej. usó 'nombre_suc'), la forzamos
            if 'Sucursal' not in df_sucursal.columns:
                df_sucursal['Sucursal'] = nombre_suc
            
            if 'Fecha extracción' not in df_sucursal.columns:
                df_sucursal['Fecha extracción'] = datetime.now().strftime("%Y-%m-%d")

            # 3. Guardar las columnas internas que necesitamos para el histórico
            if 'EAN' in df_sucursal.columns:
                df_sucursal['codinterno'] = df_sucursal['EAN']
            if 'Descripcion' in df_sucursal.columns:
                df_sucursal['descripcion'] = df_sucursal['Descripcion']
            if 'Precio Dinamizado' in df_sucursal.columns:
                df_sucursal['precio_promo'] = df_sucursal['Precio Dinamizado']
            if 'Precio Fleje' in df_sucursal.columns:
                df_sucursal['precio_anterior'] = df_sucursal['Precio Fleje']
            if 'Promocion Desc' in df_sucursal.columns:
                df_sucursal['cantidad_promo'] = df_sucursal['Promocion Desc']
            if 'Fecha extracción' in df_sucursal.columns:
                df_sucursal['fecha_exportacion'] = df_sucursal['Fecha extracción']

            
            log_message(f"  → Hilo FINALIZADO para: {nombre_suc} ({cadena}). {len(df_sucursal)} productos encontrados.")
            return df_sucursal
        
    except Exception as e:
        log_message(f"  → ❌ Error crítico en Hilo {nombre_suc} ({cadena}): {e}")
        
    log_message(f"  → Hilo FINALIZADO para: {nombre_suc} ({cadena}). Sin productos.")
    return pd.DataFrame() # Retornar un DF vacío en caso de error

# ---
# --- FIN DE LA LÓGICA DE OPTIMIZACIÓN
# ---

def run_full_scraper_automation():
    """Ejecuta el proceso completo de scraping, análisis histórico y envío de email."""
    log_message("--- INICIO DE EJECUCIÓN DIARIA (NABs + CZA) ---")
    start_time = time.time()

    # 1. Cargar sucursales
    try:
        if not os.path.exists(SUCURSALES_FILE_PATH):
            raise FileNotFoundError(f"Archivo de sucursales no encontrado: {SUCURSALES_FILE_PATH}")
            
        if SUCURSALES_FILE_PATH.endswith('.csv'):
            df_sucursales = pd.read_csv(SUCURSALES_FILE_PATH)
        else:
            df_sucursales = pd.read_excel(SUCURSALES_FILE_PATH) 

        # --- Lógica robusta para renombrar y validar columnas ---
        if 'Sucursal 2' in df_sucursales.columns:
            df_sucursales.rename(columns={'Sucursal 2': 'Nombre Suc'}, inplace=True)
        elif 'Sucursal' in df_sucursales.columns and 'Nombre Suc' not in df_sucursales.columns:
            log_message("Advertencia: No se encontró 'Sucursal 2', usando 'Sucursal' como fallback.")
            df_sucursales.rename(columns={'Sucursal': 'Nombre Suc'}, inplace=True)
        
        # Validar columnas requeridas
        required_cols = ['Cadena', 'Nombre Suc', 'Codigo Suc', 'Provincia']
        if not all(col in df_sucursales.columns for col in required_cols):
             raise ValueError(f"El archivo debe contener las siguientes columnas: {', '.join(required_cols)}")
        
        # Validar NODO
        if 'NODO' not in df_sucursales.columns:
            log_message("Advertencia: Columna 'NODO' no encontrada en el maestro. Se rellenará con 'N/A'.")
            df_sucursales['NODO'] = 'N/A'
        else:
            df_sucursales['NODO'] = df_sucursales['NODO'].fillna('N/A')

        
        df_sucursales.dropna(subset=required_cols, inplace=True)
        log_message(f"Se cargaron {len(df_sucursales)} sucursales para escanear.")
        
    except Exception as e:
        if isinstance(e, ValueError) or isinstance(e, FileNotFoundError):
             log_message(f"❌ Error al cargar archivo de sucursales: {e}")
             return
        else:
            log_message(f"❌ Error inesperado al cargar archivo de sucursales: {e}")
            return
    
    # Normalización de Cadena
    if 'Cadena' in df_sucursales.columns:
        df_sucursales['Cadena'] = df_sucursales['Cadena'].astype(str).str.strip().str.title()

    # Lista de cadenas soportadas
    supported_cadenas = ['La Cooperativa', 'Dia', 'Coto', 'Carrefour', 'Vea', 'Chango Mas', 'Toledo', 'Libertad','Jumbo','Disco']
    df_sucursales_filtered = df_sucursales[df_sucursales['Cadena'].isin(supported_cadenas)].copy()
    
    if df_sucursales_filtered.empty:
        log_message("Advertencia: No hay sucursales válidas o soportadas en el archivo.")
        return
        
    # 2. Cargar histórico y preparar listas
    # NOTA: Usamos el archivo histórico específico 'scraper_historical_data_NABs_CZA.parquet'
    df_historico_para_comparacion = cargar_datos_historicos(HISTORY_FILE) 
    lista_dfs_actual = [] # Lista para recolectar DFs de sucursales

    status_proxy = console_logger
    
    # 3. Pre-procesamiento (Catálogo Maestro) - Esto debe ser SECUENCIAL
    master_items_carrefour = []
    master_items_vea = []
    master_items_jumbo = []
    master_items_disco = []
    
    if 'Carrefour' in df_sucursales_filtered['Cadena'].values:
        log_message("Obteniendo catálogo maestro de Carrefour...")
        master_items_carrefour = carrefour_api.fetch_carrefour_items(status_proxy)
        log_message(f"→ Encontrados {len(master_items_carrefour)} items de Carrefour.")
    
    if 'Vea' in df_sucursales_filtered['Cadena'].values:
        log_message("Obteniendo catálogo maestro de Vea...")
        master_items_vea = vea_api.fetch_vea_items(status_proxy)
        log_message(f"→ Encontrados {len(master_items_vea)} items de Vea.")
   
    if 'Jumbo' in df_sucursales_filtered['Cadena'].values:
        log_message("Obteniendo catalogo maestro de Jumbo...")
        master_items_jumbo = jumbo_api.fetch_jumbo_items(status_proxy)
        log_message(f"→Encontrados {len(master_items_vea)} items de Jumbo.")

    if 'Disco' in df_sucursales_filtered['Cadena'].values:
        log_message("Obteniendo catalogo maestro de Disco...")
        master_items_disco = disco_api.fetch_disco_items(status_proxy)
        log_message(f"→Encontrados {len(master_items_vea)} items de Disco.")

 
    # 4. ITERAR Y SCRAPEAR (MODO PARALELO)
    
    MAX_WORKERS_BRANCHES = 20 # Tu configuración
    log_message(f"Iniciando scraping en paralelo para {len(df_sucursales_filtered)} sucursales (Max Hilos: {MAX_WORKERS_BRANCHES})...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS_BRANCHES) as executor:
        # Creamos una tarea para cada FILA (sucursal) en el DataFrame
        futures = {
            executor.submit(
                process_single_branch,  # La función a ejecutar
                row,                    # La fila completa (argumento 1)
                master_items_carrefour, # El catálogo (argumento 2)
                master_items_vea,       # El catálogo (argumento 3)  
                master_items_jumbo,
                master_items_disco,       
                status_proxy            # El logger (argumento 4)
            ): index 
            for index, row in df_sucursales_filtered.iterrows()
        }
        
        # A medida que las sucursales completan, recolectamos sus DataFrames
        for future in as_completed(futures):
            df_sucursal_resultado = future.result()
            if df_sucursal_resultado is not None and not df_sucursal_resultado.empty:
                lista_dfs_actual.append(df_sucursal_resultado)
    # --- FIN DEL BUCLE PARALELO ---


    # 5. UNIFICAR Y PROCESAR
    if not lista_dfs_actual:
        log_message("❌ Proceso terminado sin obtener ningún dato.")
        return
        
    df_actual_unificado = pd.concat(lista_dfs_actual, ignore_index=True)
    
    # 6. COMPARAR CONTRA EL HISTÓRICO (ÚLTIMA FECHA)
    df_final_unificado = procesar_datos_historicos(df_actual_unificado, df_historico_para_comparacion)
    
    # 7. GUARDAR NUEVO HISTÓRICO (ACUMULA)
    guardar_datos_historicos(df_actual_unificado, HISTORY_FILE)
    log_message("✅ Datos históricos acumulados y guardados para la próxima ejecución.")
    
    with open(
    CONTROL_FILE,
    "w",
    encoding="utf-8"
    ) as f:

        f.write(
            datetime.now().strftime(
                "%Y-%m-%d"
            )
        )
    # 8. PREPARAR Y ENVIAR EMAIL
    
    # 2. Orden final de columnas deseado
    final_column_order = [
        'Fecha extracción',
        'Cadena',
        'Sucursal',
        'NODO',
        'EAN',
        'Descripcion',
        'Marca',
        'Precio Fleje',
        'Precio Dinamizado',
        'Promocion Desc',
        'Inicio Promo',
        'Fin Promo',
        'Fecha Anterior',
        'Precio Fleje Anterior',
        'Precio Dinamizado Anterior',
        'Promoción Desc Anterior'

    ]

    # 3. Crear el DataFrame para Excel
    columnas_disponibles_en_excel = [col for col in final_column_order if col in df_final_unificado.columns]
    df_excel_final = df_final_unificado[columnas_disponibles_en_excel]
    
    # Generamos los bytes del Excel a partir del DataFrame recién formateado
    excel_bytes = to_excel_bytes(df_excel_final)
    # --- GUARDAR ARCHIVO LOCAL ---
    output_file = os.path.join(OUTPUT_FOLDER, f"Reporte_cervezas_{datetime.now().strftime('%d-%m-%Y')}.xlsx")
    with open(output_file, "wb") as f:
        f.write(excel_bytes)
    log_message(f"📁 Archivo guardado en: {output_file}")
    # send_email_report(df_final_unificado, excel_bytes)
    log_message("📩 Email omitido")
    end_time = time.time()
    elapsed_time = end_time - start_time
    log_message(f"--- FIN DE EJECUCIÓN DIARIA. Duración: {elapsed_time:.2f} segundos. ---")

if __name__ == "__main__":
    run_full_scraper_automation()
