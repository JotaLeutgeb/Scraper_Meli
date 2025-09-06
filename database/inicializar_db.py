# inicializar_db.py
import os
import sys
import psycopg2
from dotenv import load_dotenv

# Carga de variables de entorno
load_dotenv()

# Configuración de la Base de Datos desde .env
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD")
}

def inicializar_base_de_datos():
    """
    Se conecta a PostgreSQL y crea la tabla 'registros_precios' si no existe.
    Este script se ejecuta una sola vez al inicio del proyecto.
    """
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                print("Conectado a PostgreSQL. Verificando si la tabla 'registros_precios' existe...")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS registros_precios (
                        id SERIAL PRIMARY KEY,
                        id_catalogo VARCHAR(20) NOT NULL,
                        item_id VARCHAR(20) NOT NULL,
                        nombre_producto TEXT,
                        categoria_principal VARCHAR(100),
                        categoria_secundaria VARCHAR(100),
                        precio NUMERIC(12, 2) NOT NULL,
                        condicion_producto VARCHAR(50),
                        nombre_vendedor TEXT,
                        cuotas_sin_interes INTEGER,
                        envio_full BOOLEAN,
                        envio_gratis BOOLEAN,
                        envio_rapido BOOLEAN,
                        factura_a BOOLEAN,
                        reputacion_vendedor VARCHAR(100),
                        link_publicacion TEXT,
                        fecha_extraccion DATE NOT NULL,
                        UNIQUE(fecha_extraccion, item_id)
                        
                    );
                """)
                conn.commit()
                print("¡Éxito! La tabla 'registros_precios' está lista y configurada.")
    except psycopg2.OperationalError as e:
        print("--- ERROR DE CONEXIÓN A POSTGRESQL ---")
        print(f"No se pudo conectar a la base de datos: {e}")
        print("Verifica que PostgreSQL esté corriendo y que los datos en tu archivo .env son correctos.")
        sys.exit(1)
    except Exception as e:
        print(f"Ocurrió un error inesperado: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("--- INICIANDO CONFIGURACIÓN DE LA BASE DE DATOS PARA PROYECTO MELI ---")
    inicializar_base_de_datos()