#generador kpis
import pandas as pd
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from io import StringIO
from urllib.parse import quote_plus

def ejecutar_generacion_kpis(source_table: str, kpi_table: str, nuestro_seller_name: str):
    """
    Lee los datos crudos del día, calcula la "foto" de KPIs,
    y la inserta/actualiza en la tabla de KPIs.
    """
    load_dotenv()
    print("\nIniciando la generación de la foto diaria de KPIs...")
    
    # Usamos SQLAlchemy para una mejor integración con Pandas
    db_password_encoded = quote_plus(os.getenv('DB_PASSWORD'))

    # 3. Construimos la cadena con la contraseña ya codificada
    conn_string = f"postgresql://{os.getenv('DB_USER')}:{db_password_encoded}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    
    # --- FIN DE LA CORRECCIÓN ---

    engine = create_engine(conn_string)

    # ==============================================================================
    # ======================= INICIO: QUERY FOTO-DIARIA DE KPIS ======================
    # ==============================================================================
    query_kpis = f"""
    WITH DatosConRango AS (
        -- Preparamos los datos del día, identificando a nuestro vendedor y rankeando a todos por precio
        SELECT
            *,
            -- Identificamos nuestra propia fila para cálculos especiales
            (nombre_vendedor = '{nuestro_seller_name}') AS es_nuestro,
            -- Asignamos un valor numérico a la reputación para el promedio
            CASE reputacion_vendedor
                WHEN 'MercadoLíder Platinum' THEN 5.0 WHEN 'MercadoLíder Gold' THEN 4.0
                WHEN 'MercadoLíder' THEN 3.0 ELSE 2.0
            END AS reputacion_valor,
            -- Rankeamos a todos los competidores por precio para saber la posición
            ROW_NUMBER() OVER(PARTITION BY id_catalogo ORDER BY precio ASC, item_id ASC) as posicion_precio_actual
        FROM {source_table}
        WHERE fecha_extraccion = CURRENT_DATE
    )
    -- Agrupamos todo por producto para generar la única fila de KPIs del día
    SELECT
        MAX(fecha_extraccion) AS fecha,
        id_catalogo,
        MAX(nombre_producto) AS nombre_producto,
        MAX(categoria_principal) AS categoria_principal,
        MAX(categoria_secundaria) AS categoria_secundaria,
        COUNT(*) AS n_competidores,
        MIN(precio) AS precio_minimo,
        AVG(precio) AS precio_promedio,
        MAX(precio) AS precio_maximo,
        -- Obtenemos nuestro precio usando la bandera 'es_nuestro'
        MAX(CASE WHEN es_nuestro THEN precio END) AS nuestro_precio,
        -- Obtenemos nuestra posición de la misma forma
        MAX(CASE WHEN es_nuestro THEN posicion_precio_actual END) AS posicion_precio,
        -- Usamos AVG(CAST(col_booleana AS INT)) para calcular porcentajes de forma eficiente
        AVG(CAST(envio_rapido AS INT)) * 100 AS pct_con_envio_rapido,
        AVG(CAST(envio_full AS INT)) * 100 AS pct_con_full,
        AVG(CAST(envio_gratis AS INT)) * 100 AS pct_con_envio_gratis,
        AVG(CAST(factura_a AS INT)) * 100 AS pct_con_factura_a,
        -- Obtenemos los datos del líder (el que tiene posicion_precio_actual = 1)
        MAX(CASE WHEN posicion_precio_actual = 1 THEN item_id END) AS competidor_lider_precio_id,
        MAX(CASE WHEN posicion_precio_actual = 1 THEN nombre_vendedor END) AS competidor_lider_precio_nombre,
        -- Calculamos la diferencia de nuestro precio contra el mínimo del mercado
        (MAX(CASE WHEN es_nuestro THEN precio END) - MIN(precio)) AS diferencia_vs_lider,
        AVG(reputacion_valor) AS reputacion_promedio_valor
    FROM DatosConRango
    GROUP BY id_catalogo;
    """
    
    try:
        with engine.connect() as connection:
            df_kpis = pd.read_sql(query_kpis, connection)

            if df_kpis.empty:
                print("-> No se encontraron datos de hoy para generar KPIs.")
                return

            print(f"-> Foto de KPIs generada para {len(df_kpis)} producto(s).")
            
            # --- Inserción Robusta (UPSERT) ---
            # Esto inserta los nuevos KPIs y, si ya existen para esa fecha y producto (PRIMARY KEY), los actualiza.
            # Es la forma más segura de manejar los datos diarios.
            output = StringIO()
            df_kpis.to_csv(output, sep='\t', header=False, index=False)
            output.seek(0)
            
            db_connection = connection.connection
            cursor = db_connection.cursor()
            
            # Creamos una tabla temporal para cargar los datos
            cursor.execute(f"CREATE TEMP TABLE temp_kpis (LIKE {kpi_table}) ON COMMIT PRESERVE ROWS;")
            cursor.copy_expert(f"COPY temp_kpis FROM STDIN", output)
            
            # Hacemos el UPSERT desde la tabla temporal a la tabla final
            cols = [f'"{c}"' for c in df_kpis.columns]
            update_cols = ", ".join([f"{c} = EXCLUDED.{c}" for c in cols])
            
            upsert_sql = f"""
            INSERT INTO {kpi_table} ({', '.join(cols)})
            SELECT * FROM temp_kpis
            ON CONFLICT (fecha, id_catalogo) DO UPDATE SET {update_cols};
            """
            cursor.execute(upsert_sql)
            db_connection.commit()
            
            print(f"-> {len(df_kpis)} registros de KPIs insertados/actualizados en '{kpi_table}'.")

    except Exception as e:
        print(f"--- ERROR durante la generación de KPIs: {e}")

if __name__ == '__main__':
    # Esto es solo para pruebas directas del script
    ejecutar_generacion_kpis(
        source_table='dinamo_registros_precios', 
        kpi_table='kpis_diarios_producto',
        nuestro_seller_name='Dinamo Materiales Electricos'
    )