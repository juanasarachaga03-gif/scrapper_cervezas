"""
last_millers.py — Orquestador de las plataformas "Last Millers"
(PedidosYa Market y Rappi Turbo, tienda Nuñez).

Independiente de script.py (Cadenas Nacionales) y main.py (Cadena
Interior): no modifica nada de esos dos. Genera su propio
Reporte_LastMillers_{fecha}.xlsx con las mismas columnas finales que el
resto de los reportes, así el workflow lo levanta con el mismo
`cp Reporte_*.xlsx` que ya usa para los otros dos.

Uso:
    python last_millers.py
"""

import os
import sys
from datetime import datetime

import pandas as pd

PROJECT_PATH = os.path.dirname(os.path.abspath(__file__))
MODULOS_PATH = os.path.join(PROJECT_PATH, "Codigos")
if MODULOS_PATH not in sys.path:
    sys.path.append(MODULOS_PATH)

import pedidosya_api  # noqa: E402
import rappi_api  # noqa: E402


def log_message(message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")


class ConsoleLogger:
    def write(self, message):
        log_message(message)
    def info(self, message):
        log_message(f"ℹ️ {message}")
    def warning(self, message):
        log_message(f"⚠️ {message}")
    def error(self, message):
        log_message(f"❌ {message}")
    def progress(self, *args, **kwargs):
        if "text" in kwargs:
            log_message(f"  ... {kwargs['text']}")
    def success(self, *args, **kwargs):
        pass


def main():
    log_message("--- INICIO Last Millers (PedidosYa + Rappi) ---")
    logger = ConsoleLogger()

    dfs = []

    df_pya = pedidosya_api.fetch_and_process_pedidosya_prices(
        nombre_suc="Market Nuñez",
        nodo="N/A",
        provincia="CABA",
        status_box=logger,
        progress_bar=logger,
    )
    if not df_pya.empty:
        dfs.append(df_pya)

    df_rappi = rappi_api.fetch_and_process_rappi_prices(
        nombre_suc="Turbo Nuñez",
        nodo="N/A",
        provincia="CABA",
        status_box=logger,
        progress_bar=logger,
    )
    if not df_rappi.empty:
        dfs.append(df_rappi)

    if not dfs:
        log_message("❌ Sin datos de PedidosYa ni Rappi. No se genera archivo.")
        return

    df_final = pd.concat(dfs, ignore_index=True)

    output_file = os.path.join(
        PROJECT_PATH, f"Reporte_LastMillers_{datetime.now().strftime('%d-%m-%Y')}.xlsx"
    )
    df_final.to_excel(output_file, index=False, sheet_name="Resultados")
    log_message(f"📁 Archivo guardado en: {output_file} ({len(df_final)} filas)")


if __name__ == "__main__":
    main()
