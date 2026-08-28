import os
import pandas as pd

from APIs.depot_api import scrape_depot
from APIs.cordiez_api import scrape_cordiez
from APIs.atomo_api import scrape_atomo
from APIs.lagallega_api import scrape_lagallega
from APIs.supermami_api import scrape_supermami
from APIs.lareina_api import scrape_lareina
from APIs.top_api import scrape_top
# --- EJECUCIÓN DE SCRAPERS CON MANEJO DE ERRORES ---

# 1. Depot
try:
    df_depot = scrape_depot()
except Exception as e:
    print(f"⚠️ Error/Timeout en Depot: {e}")
    df_depot = pd.DataFrame()

# 2. Cordiez
try:
    df_cordiez = scrape_cordiez()
except Exception as e:
    print(f"⚠️ Error/Timeout en Cordiez: {e}")
    df_cordiez = pd.DataFrame()

# 3. Atomo
try:
    df_atomo = scrape_atomo()
except Exception as e:
    print(f"⚠️ Error/Timeout en Atomo: {e}")
    df_atomo = pd.DataFrame()

# 4. La Gallega
try:
    df_lagallega = scrape_lagallega()
except Exception as e:
    print(f"⚠️ Error/Timeout en La Gallega: {e}")
    df_lagallega = pd.DataFrame()

# 5. Super Mami
try:
    df_supermami = scrape_supermami()
except Exception as e:
    print(f"⚠️ Error/Timeout en Super Mami: {e}")
    df_supermami = pd.DataFrame()

# 6. La Reina
try:
    df_lareina = scrape_lareina()
except Exception as e:
    print(f"⚠️ Error/Timeout en La Reina: {e}")
    df_lareina = pd.DataFrame()

# 7. Top
try:
    df_top = scrape_top()
except Exception as e:
    print(f"⚠️ Error/Timeout en Top: {e}")
    df_top = pd.DataFrame()

# Normalizar precios

if "precio" in df_depot.columns:
    df_depot["precio_oferta"] = df_depot["precio"]

if "precio" in df_atomo.columns:
    df_atomo["precio_oferta"] = df_atomo["precio"]

if "precio" in df_lagallega.columns:
    df_lagallega["precio_oferta"] = df_lagallega["precio"]

df_depot = df_depot[df_depot["stock"] == True]
df_cordiez = df_cordiez[df_cordiez["stock"] == True]
# Normalizar precios

if "precio" in df_depot.columns:
    df_depot["precio_oferta"] = df_depot["precio"]

if "precio" in df_atomo.columns:
    df_atomo["precio_oferta"] = df_atomo["precio"]

if "precio" in df_lagallega.columns:
    df_lagallega["precio_oferta"] = df_lagallega["precio"]
df_final = pd.concat(
    [
        df_depot,
        df_cordiez,
        df_atomo,
        df_lagallega,
        df_supermami,
        df_lareina,
        df_top
    ],
    ignore_index=True
)
output_dir = os.path.dirname(__file__)

os.makedirs(output_dir, exist_ok=True)

from datetime import datetime
fecha_archivo = datetime.now().strftime("%Y-%m-%d")
archivo = os.path.join(
    output_dir,
    f"Reporte_Cervezas_Interior_{fecha_archivo}.xlsx"
)
columnas = [
    "fecha_scraping",
    "cadena",
    "sucursal",
    "NODO",
    "ean",
    "nombre",
    "marca",
    "precio_lista",
    "precio_oferta",
    "descuento_pct",
    "Inicio Promo",
    "Fin Promo",
    "Fecha Ant",
    "Precio Fleje Ant",
    "Promoción Desc Anterior" 
]

columnas_existentes = [
    c for c in columnas
    if c in df_final.columns
]

otras = [
    c for c in df_final.columns
    if c not in columnas_existentes
]

df_final = df_final[
    columnas_existentes + otras
]

# Crear estructura final
df_export = pd.DataFrame()
df_export["Tipo de Cadena"] = ["Cadena Interior"] * len(df_final)
df_export["Fecha extracción"] = df_final["fecha_scraping"]
df_export["Cadena"] = df_final["cadena"]
sucursal = {
"Depot": "Depot",
"Cordiez": "Cordiez",
"Atomo": "Atomo",
"La Gallega": "La Gallega",
"La Reina": "La Reina",
"Super Mami": "Super Mami",
"TOP": "TOP"
}
df_export["Sucursal"] = df_export["Cadena"].map(sucursal)

nodos = {
"Depot": "CZA - SMK - 13 - DI NEA",
"Cordiez": "CZA - SMK - 10 - SGO - CAT - CENTRAL",
"Atomo": "CZA - SMK - 10 - SGO - CAT - CENTRAL",
"La Gallega": "CZA - SMK - 11 - ROSARIO",
"La Reina": "CZA - SMK - 11 - ROSARIO",
"Super Mami": "CZA - SMK - 10 - SGO - CAT - CENTRAL",
"TOP": "CZA - SMK - 10 - SGO - CAT - CENTRAL"
}
df_export["NODO"] = df_export["Cadena"].map(nodos)
df_export["EAN"] = df_final["ean"]
df_export["Descripcion"] = df_final["nombre"]
df_export["Marca"] = df_final["marca"]
df_export["Precio Fleje"] = df_final["precio_lista"]
df_export["Precio Dinamizado"] = df_final["precio_oferta"]
df_export["Promocion Desc"] = ""
df_export["Inicio Promo"] = ""
df_export["Fin Promo"] = ""
df_export["Fecha Ant"] = ""
df_export["Precio Fleje Ant"] = ""
df_export["Promoción Desc Anterior"] = ""

# EXPORTAR ESTE DATAFRAME

df_export.to_excel(
    archivo,
    sheet_name="Resultados",
    index=False
)

print(f"📦 Depot: {len(df_depot)}")
print(f"📦 Cordiez: {len(df_cordiez)}")
print(f"📦 Atomo: {len(df_atomo)}")
print(f"📦 La Gallega: {len(df_lagallega)}")
print(f"📦 Super Mami: {len(df_supermami)}")
print(f"📦 La Reina: {len(df_lareina)}")
print(f"📦 Top: {len(df_top)}")
print(f"\n📦 TOTAL CONSOLIDADO: {len(df_final)}")
print(f"✅ Excel generado: {archivo}")
