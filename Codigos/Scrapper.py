import streamlit as st
import pandas as pd
from datetime import datetime
import io 

# Importar las APIs
# Nota: Ahora solo se requiere la API de Vea (asumiendo que es vea_api_app.py)
import vea_api_app as vea_api   

# Configuración de la página
st.set_page_config(page_title="Scrapper Supermercados - Vea", page_icon="🛒", layout="wide")

st.title("🛒 Scrapper Multicadena: Solo Vea")
st.markdown("Este sistema consulta precios y promociones de **Vea** basándose en el archivo **Maestro_regiones.xlsx**.")

# Carga del archivo maestro
# SOLUCIÓN DEL ERROR StreamlitDuplicateElementId: Se añade el argumento 'key'.
uploaded_file = st.file_uploader(
    "Cargar Maestro de Sucursales (Excel)", 
    type=["xlsx"],
    key="maestro_file_uploader" # Clave única añadida
)

if uploaded_file is not None:
    try:
        df_sucursales = pd.read_excel(uploaded_file, engine='openpyxl')
        st.success("✅ Maestro cargado correctamente.")
        
        # Filtrar solo Vea
        df_sucursales_vea = df_sucursales[df_sucursales['Cadena'] == 'Vea'].copy()
        
        if df_sucursales_vea.empty:
            st.warning("⚠️ El archivo maestro no contiene sucursales con la cadena 'Vea'.")
        else:
            st.info(f"Sucursales Vea encontradas para procesar: {len(df_sucursales_vea)}")
            st.dataframe(df_sucursales_vea.head())

            if st.button("🚀 Ejecutar Scrapper (Solo Vea)"):
                
                status_box = st.empty()
                progress_bar = st.progress(0, text="Iniciando...")
                
                dfs_consolidados = []
                error_logs = {} 
                total_filas = len(df_sucursales_vea)
                
                # --- PRE-PROCESO: VEA CATALOGO MAESTRO ---
                status_box.info("Obteniendo catálogo maestro de Vea...")
                master_items_vea = vea_api.fetch_vea_items(status_box)
                
                if not master_items_vea:
                    status_box.error("❌ No se pudo obtener el catálogo maestro de Vea. Proceso cancelado.")
                    progress_bar.progress(1.0, text="Proceso Completado con Errores.")
                else:
                    # --- BUCLE PRINCIPAL POR SUCURSAL (SOLO VEA) ---
                    for index, row in df_sucursales_vea.iterrows():
                        
                        sucursal = row['Sucursal'] if not pd.isna(row['Sucursal']) else 'Sucursal Desconocida'
                        provincia = row['Provincia'] if not pd.isna(row['Provincia']) else ''
                        
                        # Para Vea: Usamos 'Codigo Suc' (cookie vtex_segment) y 'Codigo CCX' (seller ID)
                        id_sucursal_vtex = row['Codigo Suc'] if not pd.isna(row['Codigo Suc']) else 'CODIGO_SUC_DESCONOCIDO'
                        codigo_ccx = row['Codigo CCX'] if not pd.isna(row['Codigo CCX']) else 'CCX_DESCONOCIDO' 
                        
                        # --- Lógica de Progreso Global ---
                        # Usamos la posición del contador de filas para el progreso
                        fila_actual = df_sucursales_vea.index.get_loc(index)
                        progreso_global = (fila_actual / total_filas)
                        progress_bar.progress(progreso_global, text=f"Procesando Vea - {sucursal} ({fila_actual+1}/{total_filas})")
                        
                        df_resultado_sucursal = pd.DataFrame()

                        # ==========================================
                        # LÓGICA VEA
                        # ==========================================
                        # La función ya no espera argumentos de progreso global (index/total_filas)
                        df_resultado_sucursal, vea_errors = vea_api.fetch_and_process_vea_prices_parallel(
                            master_items_vea,
                            sucursal,
                            provincia,
                            id_sucursal_vtex, 
                            codigo_ccx,       
                            status_box,
                            progress_bar
                        )
                        
                        if vea_errors:
                            error_logs[f'Vea - {sucursal}'] = vea_errors
                        
                        
                        # --- ACUMULAR RESULTADOS ---
                        if not df_resultado_sucursal.empty:
                            dfs_consolidados.append(df_resultado_sucursal)
                        else:
                            if f'Vea - {sucursal}' in error_logs:
                                error_detail = error_logs[f'Vea - {sucursal}']
                                report = ", ".join([f"{code}: {count}" for code, count in error_detail.items()])
                                st.warning(f"⚠️ No se obtuvieron datos para Vea - {sucursal}. Motivos: {report}")
                            else:
                                st.warning(f"⚠️ No se obtuvieron datos para Vea - {sucursal}")


                    # Finalización del proceso
                    progress_bar.progress(1.0, text="Proceso Completado.")
                    
                    # --- EXPORTACIÓN FINAL ---
                    if dfs_consolidados:
                        df_final = pd.concat(dfs_consolidados, ignore_index=True)
                        
                        st.success(f"✅ Extracción finalizada con éxito. Total productos: {len(df_final)}")
                        st.dataframe(df_final)
                        
                        fecha_str = datetime.now().strftime("%Y%m%d_%H%M")
                        nombre_archivo = f"Relevamiento_Precios_Vea_{fecha_str}.xlsx"
                        
                        buffer = io.BytesIO()
                        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                            df_final.to_excel(writer, index=False, sheet_name='Precios')
                            
                        st.download_button(
                            label="📥 Descargar Excel Consolidado",
                            data=buffer.getvalue(),
                            file_name=nombre_archivo,
                            mime="application/vnd.ms-excel"
                        )
                    else:
                        st.error("❌ No se generaron datos de Vea. Revisa la conexión o los códigos.")
                
    except Exception as e:
        st.error(f"Ocurrió un error al procesar el archivo maestro: {e}")