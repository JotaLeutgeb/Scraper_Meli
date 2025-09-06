# dashboard.py (Versión 2.0 - Conectado a Base de Datos Real)
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import psycopg2
import os
from dotenv import load_dotenv

# Cargar las variables de entorno desde el archivo .env
load_dotenv()

# --- FUNCIÓN PARA CARGAR DATOS REALES DESDE POSTGRESQL ---
# @st.cache_data es un decorador de Streamlit que optimiza el rendimiento.
# Guarda el resultado de la función en memoria. Si se vuelve a llamar a la función
# con los mismos parámetros, Streamlit devuelve el resultado guardado en lugar de
# volver a ejecutar el código y consultar la base de datos.
# ttl (Time To Live) especifica que el caché expira después de 600 segundos (10 minutos),
# forzando una actualización de los datos desde la BD.
@st.cache_data(ttl=600)

# def cargar_datos_reales(dias: int = 30) -> pd.DataFrame:
#     """
#     Se conecta a la base de datos PostgreSQL y carga los KPIs de los últimos 'dias'.
#     """
#     try:
#         conn = psycopg2.connect(
#             host=os.getenv("DB_HOST"),
#             port=os.getenv("DB_PORT"),
#             dbname=os.getenv("DB_NAME"),
#             user=os.getenv("DB_USER"),
#             password=os.getenv("DB_PASSWORD")
#         )
#         query = f"SELECT * FROM kpis_diarios_producto WHERE fecha >= CURRENT_DATE - INTERVAL '{dias} days';"
#         df = pd.read_sql(query, conn)
#         return df
#     except Exception as e:
#         st.error(f"Error al conectar con la base de datos: {e}")
#         return pd.DataFrame()
#     finally:
#         if 'conn' in locals() and conn is not None:
#             conn.close()


# --- MOCK DATA PARA TESTING ---
def generar_datos_mock(dias=30) -> pd.DataFrame:
    # ... (el código de esta función no cambia, lo omito por brevedad pero puedes dejarlo en tu script)
    data = []
    productos = {
        "MLA12345678": "Taladro Percutor Inalámbrico 18V Brushless",
        "MLA87654321": "Set 110 Piezas Puntas y Tubos para Atornillar",
        "MLA55566677": "Amoladora Angular 4-1/2 Pulgadas 820W"
    }
    fecha_hoy = datetime.now().date()
    for id_catalogo, nombre in productos.items():
        precio_base_nuestro = np.random.uniform(28000, 55000)
        precio_base_mercado = precio_base_nuestro * np.random.uniform(0.95, 1.08)
        for i in range(dias):
            fecha = fecha_hoy - timedelta(days=i)
            nuestro_precio_dia = precio_base_nuestro * np.random.uniform(0.98, 1.20)
            precio_minimo_dia = precio_base_mercado * np.random.uniform(0.97, 1.8)
            n_competidores = np.random.randint(8, 15)
            posicion = np.random.randint(1, 5) if nuestro_precio_dia > precio_minimo_dia else 1
            data.append({
                "fecha": fecha, "id_catalogo": id_catalogo, "nombre_producto": nombre,
                "nuestro_precio": round(nuestro_precio_dia, 2), "precio_minimo": round(precio_minimo_dia, 2),
                "precio_promedio": round((nuestro_precio_dia + precio_minimo_dia * 1.1) / 2, 2),
                "posicion_precio": posicion, "n_competidores": n_competidores,
                "pct_con_full": round(np.random.uniform(30, 85), 2),
                "diferencia_vs_lider": round(nuestro_precio_dia - precio_minimo_dia, 2)
            })
    return pd.DataFrame(data).sort_values(by="fecha").reset_index(drop=True)


# --- CONSTRUCCIÓN DEL DASHBOARD ---

st.set_page_config(layout="wide", page_title="Radar de Competencia")

st.title("📡 Radar de Competencia - PROYECTO MELI")
st.markdown("Dashboard para el análisis de precios y posicionamiento de nuestros productos en Mercado Libre.")

# --- AQUÍ OCURRE LA MAGIA: CAMBIAMOS LA FUENTE DE DATOS ---
df_kpis = generar_datos_mock(dias=30) # Cargamos los últimos 60 días de datos reales

# Manejo del caso en que no haya datos en la base de datos
if df_kpis.empty:
    st.warning("No se encontraron datos en la base de datos. Verifique que el pipeline de datos se haya ejecutado.")
    
    # df_kpis = generar_datos_mock() 
else:
    st.sidebar.header("Filtros")
    # Convertir la fecha a tipo fecha para asegurar el orden correcto
    df_kpis['fecha'] = pd.to_datetime(df_kpis['fecha']).dt.date
    df_kpis = df_kpis.sort_values(by="fecha")
    
    productos_disponibles = df_kpis['nombre_producto'].unique()
    producto_seleccionado = st.sidebar.selectbox("Seleccione un Producto", productos_disponibles)

    df_filtrado = df_kpis[df_kpis['nombre_producto'] == producto_seleccionado].copy()

    st.subheader(f"{producto_seleccionado}")

    if not df_filtrado.empty:
        # Usamos .iloc[-1] para obtener siempre el último registro (el más reciente)
        df_hoy = df_filtrado.iloc[-1]

        col1, col2, col3, col4 = st.columns(4)
        col1.metric(
            label="Nuestro Precio Hoy", value=f"${df_hoy['nuestro_precio']:,.2f}",
            delta=f"${df_hoy['diferencia_vs_lider']:,.2f} vs. Líder", delta_color="inverse"
        )
        col2.metric(
            label="Nuestra Posición Hoy", value=f"#{int(df_hoy['posicion_precio'])}",
            help=f"Nuestra posición en precio entre {df_hoy['n_competidores']} vendedores."
        )
        col3.metric(label="Precio Mínimo del Mercado", value=f"${df_hoy['precio_minimo']:,.2f}")
        col4.metric(label="N° de Competidores", value=df_hoy['n_competidores'])

        st.markdown("---")
        st.subheader("Evolución de Precios")
        df_grafico_precios = df_filtrado.set_index('fecha')[['nuestro_precio', 'precio_minimo']]
        st.line_chart(df_grafico_precios)

        st.subheader("Evolución de la Competencia")
        df_grafico_competencia = df_filtrado.set_index('fecha')[['n_competidores']]
        st.bar_chart(df_grafico_competencia)

        with st.expander("Ver tabla de datos completos para el producto seleccionado"):
            st.dataframe(df_filtrado.sort_values(by="fecha", ascending=False))
    else:
        st.warning(f"No hay datos para el producto seleccionado: {producto_seleccionado}")
