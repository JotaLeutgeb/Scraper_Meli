import time
from datetime import date
import yaml # Para leer el archivo de configuración
from scraping.procesador_datos import ejecutar_proceso_para_url
from analysis.generador_kpis import ejecutar_generacion_kpis
import random

def cargar_configuracion(file_path="config.yml"):
    """Carga el archivo de configuración YAML."""
    try:
        with open(file_path, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: Archivo de configuración '{file_path}' no encontrado.")
        return None
    except Exception as e:
        print(f"Error al leer el archivo de configuración: {e}")
        return None

def main():
    """
    Función principal que orquesta el pipeline para una empresa específica.
    """
    # Cargar toda la configuración
    config = cargar_configuracion()
    if not config:
        return
    
    fecha_ejecucion = date.today()


    # Seleccionar la configuración para nuestra empresa target
    if len(config) != 1:
        print(f"Error: El archivo config.yml debe contener la configuración de una sola empresa.")
        print(f"Empresas encontradas: {list(config.keys())}")
        return
        
    empresa_target = list(config.keys())[0]
    config_empresa = config[empresa_target]
    
    print("======================================================")
    print(f"==  INICIO PIPELINE PARA: {empresa_target.upper()}  ==")
    print(f"==  FECHA DE EJECUCIÓN: {fecha_ejecucion}           ==")
    print("======================================================")

    start_time = time.time()

    # Leemos los parámetros de la configuración extraída
    seller_name = config_empresa.get('seller_name')
    urls = config_empresa.get('urls', [])
    tabla_crudos = config_empresa.get('tabla_crudos')
    tabla_kpis = config_empresa.get('tabla_kpis')
    
    print("-> Aleatorizando el orden de las URLs para evitar patrones predecibles...")
    random.shuffle(urls)
    
    if not all([urls, tabla_crudos, tabla_kpis, seller_name]):
        print(f"Error: Configuración incompleta para '{empresa_target}' en config.yml.")
        print("Asegúrate de tener: urls, tabla_crudos, tabla_kpis, nuestro_seller_name.")
        return

    # --- FASE 1: EXTRACCIÓN Y PROCESAMIENTO DE DATOS CRUDOS ---
    print(f"\n[FASE 1] Guardando datos en la tabla: '{tabla_crudos}'")
    for i, url in enumerate(urls):
        print(f"\n--- Procesando URL {i+1}/{len(urls)} ---")
        try:
            # Pasamos el nombre de la tabla como parámetro
            ejecutar_proceso_para_url(url, tabla_crudos)
        except Exception as e:
            print(f"!! ERROR INESPERADO al procesar la URL {url}: {e}")

    # --- FASE 2: GENERACIÓN DE KPIS AGREGADOS ---
    print(f"\n[FASE 2] Generando KPIs desde '{tabla_crudos}' hacia '{tabla_kpis}'")
    try:
        # Pasamos los nombres de las tablas y el seller_name como parámetros
        ejecutar_generacion_kpis(tabla_crudos, tabla_kpis, seller_name, fecha_ejecucion)
    except Exception as e:
        print(f"!! ERROR INESPERADO en la generación de KPIs: {e}")

    end_time = time.time()
    duracion_total = end_time - start_time
    
    print("\n======================================================")
    print("==      PIPELINE FINALIZADO CON ÉXITO             ==")
    print(f"==      Duración total: {duracion_total:.2f} segundos      ==")
    print("======================================================")


if __name__ == '__main__':
    main()