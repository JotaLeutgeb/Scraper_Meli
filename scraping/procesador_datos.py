# procesador_datos.py
import pandas as pd
import asyncio
from datetime import datetime, date
import os
import sys
import re
import psycopg2
import psycopg2.extras

from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    'host': os.getenv("DB_HOST"),
    'port': os.getenv("DB_PORT"),
    'dbname': os.getenv("DB_NAME"),
    'user': os.getenv("DB_USER"),
    'password': os.getenv("DB_PASSWORD")
}

#Importamos el scraper
try:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from .scraper_producto_catalogo import extraer_competidores_catalogo
except ImportError:
    print("Error: Asegúrate de que el archivo 'scraper_producto_catalogo.py' se encuentre en el mismo directorio.")
    sys.exit(1)


def extraer_id_producto(url: str) -> str | None:
    match = re.search(r'/p/(MLA\d+)', url)
    if match: return match.group(1)
    print("ADVERTENCIA: No se pudo encontrar un ID de producto en la URL proporcionada.")
    return None

def obtener_cuotas_sin_interes(texto: str) -> int:
    if not isinstance(texto, str) or not texto:
        return 0
    
    # El operador '|' actúa como un "OR". Busca el primer patrón O el segundo.
    # Cada patrón tiene su propio grupo de captura (\d+) para el número.
    patron = r'(?:Mismo precio en\s*(\d+)\s*cuotas)|(?:(\d+)\s*cuotas\s*sin\s*interés)'
    
    match = re.search(patron, texto, re.IGNORECASE)
    
    if match:
        # match.group(1) corresponderá al número del primer patrón.
        # match.group(2) corresponderá al número del segundo patrón.
        # Usamos 'or' para obtener el valor que no sea None.
        numero_cuotas = match.group(1) or match.group(2)
        if numero_cuotas:
            return int(numero_cuotas)
            
    return 0

def producto_ya_scrapeado_hoy(id_producto: str, fecha: date, table_name: str) -> bool:
    """
    Verifica en la base de datos si ya existen registros para un producto en una fecha específica.
    """
    print(f"Verificando si el producto {id_producto} ya fue procesado hoy ({fecha}) en la tabla '{table_name}'...")
    
    # La query ahora usa el nombre de la tabla dinámicamente
    query = f"""
    SELECT EXISTS (
        SELECT 1
        FROM {table_name}
        WHERE id_catalogo = %s AND fecha_extraccion = %s
    );
    """
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute(query, (id_producto, fecha))
                existe = cur.fetchone()[0]
                if existe:
                    print(f"-> SÍ. El producto ya existe. Saltando scraping.")
                else:
                    print(f"-> NO. El producto es nuevo para hoy. Procediendo a scrapear.")
                return existe
    except psycopg2.Error as e:
        print(f"--- ERROR de Base de Datos ---: No se pudo verificar la existencia del producto. Error: {e}")
        return False


def procesar_y_enriquecer_datos(datos_extraidos: list[dict], id_producto: str, cat_principal: str | None, cat_secundaria: str | None, nombre_producto: str | None, table_name: str):

    if not datos_extraidos:
        print("No se extrajeron datos, no hay nada que procesar o almacenar.")
        return

    print(f"\n--- Iniciando Fase de Procesamiento para el producto {id_producto} ---")
    df = pd.DataFrame(datos_extraidos)
    
    # --- Enriquecimiento de datos (ahora con las nuevas categorías) ---
    df['id_catalogo'] = id_producto
    df['item_id'] = df['item_id'].astype(str)
    df['nombre_producto'] = nombre_producto
    df['precio'] = df['precio'].astype(float)
    df['categoria_principal'] = cat_principal
    df['categoria_secundaria'] = cat_secundaria
    reputacion_map = {
        '5_green': 'MercadoLíder Platinum',
        '4_light_green': 'MercadoLíder Gold',
        '3_yellow': 'MercadoLíder'
    }
    df['reputacion_vendedor'] = df['reputacion_vendedor'].map(reputacion_map).fillna('Regular')
    df['tipo_envio_original'] = df['tipo_envio'].fillna('')
    df['envio_gratis'] = df['tipo_envio_original'].str.contains('gratis', case=False)
    df['envio_rapido'] = df['tipo_envio_original'].str.contains('mañana', case=False)
    df['cuotas_sin_interes'] = df['texto_cuotas'].apply(obtener_cuotas_sin_interes)
    df['factura_a'] = df['seller_extra_info'].apply(lambda infos: isinstance(infos, list) and any("factura a" in info.get("subtitle", "").lower() for info in infos))
    df['fecha_extraccion'] = datetime.now().date()
    
    print(f"Paso 5: Conectando a la base de datos '{DB_CONFIG['dbname']}'...")

    # --- MODIFICADO: Consulta de inserción con las nuevas columnas ---
    insert_query = f"""
    INSERT INTO {table_name} (
        fecha_extraccion, id_catalogo, nombre_producto, categoria_principal, categoria_secundaria,
        item_id, nombre_vendedor, precio, condicion_producto, cuotas_sin_interes,
        envio_full, envio_gratis, envio_rapido, factura_a, reputacion_vendedor, link_publicacion
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    registros_insertados = 0
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                for row in df.itertuples(index=False):
                    data_tuple = (
                        row.fecha_extraccion, row.id_catalogo,row.nombre_producto, row.categoria_principal, row.categoria_secundaria, row.item_id, row.nombre_vendedor,
                        row.precio, row.condicion_producto, row.cuotas_sin_interes, row.envio_full,
                        row.envio_gratis, row.envio_rapido, row.factura_a, row.reputacion_vendedor,
                        row.link_publicacion
                    )
                    cur.execute(insert_query, data_tuple)
                registros_insertados = df.shape[0]
                conn.commit()
    except psycopg2.Error as e:
        print(f"--- ERROR de Base de Datos ---: No se pudieron guardar los datos. Error: {e}")
        return

    print("\n--- ¡ÉXITO! ---")
    print(f"Se han insertado/actualizado {registros_insertados} registros en la tabla '{table_name}'.")

def ejecutar_proceso_para_url(url: str, table_name: str):
    """
    Orquesta la verificación, scraping, procesamiento y guardado para una única URL.
    """
    id_producto = extraer_id_producto(url)
    if not id_producto:
        return # Si no hay ID, no podemos continuar

    # --- PASO 1: Verificación de eficiencia ---
    if producto_ya_scrapeado_hoy(id_producto, date.today(), table_name):
        return # Si ya existe, terminamos la ejecución para esta URL

    # --- PASO 2: Scraping (si la verificación pasó) ---
    print(f"Iniciando scraping para el producto: {id_producto}...")
    
    # El scraper devuelve una tupla con 4 elementos: (datos, nombre, cat1, cat2)
    # Los recibimos en variables separadas.
    datos_vendedores,  cat_principal, cat_secundaria, nombre_prod = asyncio.run(extraer_competidores_catalogo(url))
    # --- PASO 3: Procesamiento y guardado ---
    # Pasamos TODOS los datos recolectados a la siguiente función.
    # NOTA: La función procesar_y_enriquecer_datos ya se encarga de guardar en la DB.
    # Por lo tanto, la función separada guardar_en_db ya no es necesaria en este flujo.
    if datos_vendedores:
        procesar_y_enriquecer_datos(
            datos_extraidos=datos_vendedores,
            id_producto=id_producto,
            cat_principal=cat_principal,
            cat_secundaria=cat_secundaria,
            nombre_producto=nombre_prod,
            table_name=table_name
        )
    else:
        print("  -> No se encontraron datos o hubo un error en el scraping.")