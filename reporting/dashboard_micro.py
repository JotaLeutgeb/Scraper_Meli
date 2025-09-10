# dashboard_micro.py
# Autor: Joaquin Leutgeb.
# Descripción: Una herramienta de análisis táctico que permite a los usuarios
# visualizar su posición en el mercado, recibir insights de una IA estratégica
# y simular escenarios de precios en tiempo real para ver su impacto inmediato.

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from urllib.parse import quote_plus
import google.generativeai as genai
import altair as alt
import datetime

# -----------------------------------------------------------------------------
# FUNCIONES DE CONEXIÓN Y CARGA DE DATOS

@st.cache_resource
def get_engine():
    """Crea y cachea la conexión a la base de datos."""
    try:
        db_user = st.secrets["db_user"]
        db_password_raw = st.secrets["db_password"]
        db_host = st.secrets["db_host"]
        db_port = st.secrets["db_port"]
        db_name = st.secrets["db_name"]
        db_password_encoded = quote_plus(db_password_raw)
        conn_string = f"postgresql+psycopg://{db_user}:{db_password_encoded}@{db_host}:{db_port}/{db_name}"
        return create_engine(conn_string)
    except Exception as e:
        st.error(f"Error al configurar la conexión con la base de datos: {e}")
        st.stop()

@st.cache_data
def get_product_list(tabla_crudos: str):
    """Obtiene solo la lista de productos únicos de los últimos 30 días."""
    engine = get_engine()
    query = f"SELECT DISTINCT nombre_producto FROM {tabla_crudos} WHERE fecha_extraccion >= CURRENT_DATE - INTERVAL '30 days';"
    df_products = pd.read_sql(query, engine)
    if df_products.empty:
        return []
    return sorted(df_products['nombre_producto'].unique())

@st.cache_data
def get_product_data(tabla_crudos: str, producto: str):
    """Carga los datos de los últimos 30 días SOLO para el producto seleccionado."""
    engine = get_engine()
    query = f"SELECT * FROM {tabla_crudos} WHERE nombre_producto = %(producto)s AND fecha_extraccion >= CURRENT_DATE - INTERVAL '30 days' ORDER BY fecha_extraccion DESC"
    df = pd.read_sql(query, engine, params={'producto': producto})
    df['fecha_extraccion'] = pd.to_datetime(df['fecha_extraccion']).dt.date
    return df

# -----------------------------------------------------------------------------
# FUNCIÓN DE ANÁLISIS Y LÓGICA DE NEGOCIO

def calcular_kpis(df_contexto: pd.DataFrame, nuestro_seller: str, nuestro_precio: float):
    """
    Calcula los KPIs clave de forma segura, manejando casos borde donde
    nuestra empresa o competidores son excluidos por los filtros.
    """
    kpis = {
        "posicion_num": "N/A",
        "posicion_str": "N/A",
        "cant_total": len(df_contexto),
        "nombre_lider": "N/A",
        "precio_lider": 0,
        "link_lider": "#"
    }

    # Si no hay datos en el contexto, determinar si es porque no competimos o por los filtros.
    if df_contexto.empty:
        kpis["posicion_str"] = "Fuera de Filtro" if nuestro_precio > 0 else "N/A"
        return kpis

    # Extraer información del líder del mercado de forma segura.
    kpis["nombre_lider"] = df_contexto.iloc[0]['nombre_vendedor']
    kpis["precio_lider"] = df_contexto.iloc[0]['precio']
    kpis["link_lider"] = df_contexto.iloc[0].get('link_publicacion', '#')

    # Buscar nuestra posición en el contexto actual.
    nuestra_pos_info = df_contexto[df_contexto['nombre_vendedor'] == nuestro_seller]

    if not nuestra_pos_info.empty:
        # Si nos encontramos, calcular la posición numérica.
        kpis["posicion_num"] = nuestra_pos_info.index[0] + 1
        kpis["posicion_str"] = f"#{kpis['posicion_num']}"
    elif nuestro_precio > 0:
        # Si no nos encontramos pero tenemos un precio, es que fuimos filtrados.
        kpis["posicion_str"] = "Fuera de Filtro"

    return kpis

def preparar_datos_tendencia(df_hist: pd.DataFrame, nuestro_seller: str):
    """
    Prepara el DataFrame para el gráfico de tendencias de forma robusta.

    Esta función aísla la lógica para identificar las series de datos más
    relevantes para el análisis histórico y garantiza que se muestre el
    historial completo de cualquier competidor relevante.

    Vendedores Relevantes son:
    1. Nuestra propia empresa.
    2. Cualquier vendedor que fue líder de precio en cualquier día del período.
    3. Cualquier vendedor cuyo precio en el día más reciente es inferior al nuestro.

    Args:
        df_hist (pd.DataFrame): DataFrame con los datos históricos de los últimos 15 días.
        nuestro_seller (str): El nombre de nuestra empresa/vendedor.

    Returns:
        tuple[pd.DataFrame | None, list[str] | None]:
            - Un DataFrame pivotado listo para ser usado con Altair/Streamlit.
            - Una lista de colores correspondiente a las columnas del DataFrame.
    """
    if df_hist.empty:
        return None, None

    # --- 1. Identificar a todos los vendedores relevantes en una lista única ---

    vendedores_relevantes = set()

    # Añadir siempre a nuestra empresa
    vendedores_relevantes.add(nuestro_seller)

    # todos los que fueron líderes de precio en algún momento
    lideres_diarios = df_hist.loc[df_hist.groupby('fecha_extraccion')['precio'].idxmin()]
    vendedores_relevantes.update(lideres_diarios['nombre_vendedor'].unique())

    #  competidores que HOY son más baratos que nosotros
    fecha_maxima = df_hist['fecha_extraccion'].max()
    df_hoy = df_hist[df_hist['fecha_extraccion'] == fecha_maxima]
    
    nuestra_oferta_hoy = df_hoy[df_hoy['nombre_vendedor'] == nuestro_seller]
    if not nuestra_oferta_hoy.empty:
        nuestro_precio_hoy = nuestra_oferta_hoy['precio'].iloc[0]
        competidores_mas_baratos_hoy = df_hoy[df_hoy['precio'] < nuestro_precio_hoy]
        vendedores_relevantes.update(competidores_mas_baratos_hoy['nombre_vendedor'].unique())

    # --- 2. Construir el DataFrame final con el historial completo ---

    # Filtrar el dataframe histórico para incluir solo a los vendedores relevantes
    df_largo = df_hist[df_hist['nombre_vendedor'].isin(list(vendedores_relevantes))].copy()

    if df_largo.empty:
        return None, None

    # Pivotar la tabla para tener fechas como índice y vendedores como columnas
    df_para_grafico = df_largo.pivot_table(
        index='fecha_extraccion',
        columns='nombre_vendedor',
        values='precio'
    )

    # --- 3. Lógica de colores dinámica y robusta ---

    cols = df_para_grafico.columns.tolist()

    # Asegurarnos de que nuestra empresa esté en la lista y ponerla al principio
    if nuestro_seller in cols:
        cols.insert(0, cols.pop(cols.index(nuestro_seller)))
        df_para_grafico = df_para_grafico[cols]
    
    # Generar la paleta de colores, asignando siempre verde a nuestra empresa
    paleta_competidores = ['#FF4B4B', '#3498DB', '#9B59B6', '#E67E22', '#F1C40F']
    colores = []
    
    for vendedor in cols:
        if vendedor == nuestro_seller:
            colores.append('#2ECC71')
        else:
            # Asignar colores de la paleta al resto, ciclando si es necesario
            # Usamos un hash simple para que un mismo competidor tienda a tener el mismo color
            color_index = abs(hash(vendedor)) % len(paleta_competidores)
            colores.append(paleta_competidores[color_index])
    
    # Si nuestra empresa no estaba, no podemos asegurar el color verde.
    # Esto es un fallback, pero no debería ocurrir con la lógica actual.
    if not colores:
        num_competidores = len(cols)
        for i in range(num_competidores):
            colores.append(paleta_competidores[i % len(paleta_competidores)])

    return df_para_grafico, colores
    
    # --- 2. PREPARACIÓN DEL DATAFRAME PARA GRAFICAR ---
    
    # Asignar una columna 'serie' para la pivotación, que será el nombre en la leyenda
    df_nuestro['serie'] = f"{nuestro_seller}"
    df_lider_diario['serie'] = df_lider_diario['nombre_vendedor']
    df_competidores = df_hist[df_hist['nombre_vendedor'].isin(vendedores_relevantes)].copy()
    df_competidores['serie'] = df_competidores['nombre_vendedor']

    # Concatenar todas las series relevantes y eliminar duplicados (ej. si el líder es también un competidor relevante)
    df_largo = pd.concat([df_nuestro, df_lider_diario, df_competidores]).drop_duplicates(
        subset=['fecha_extraccion', 'precio', 'serie']).reset_index(drop=True)

    if df_largo.empty:
        return pd.DataFrame(), None

    # Pivotar la tabla para tener fechas como índice y series como columnas
    df_para_grafico = df_largo.pivot_table(
        index='fecha_extraccion',
        columns='serie',
        values='precio'
    )

    # --- 3. LÓGICA DE COLORES DINÁMICA Y ROBUSTA ---
    colores = None
    cols = df_para_grafico.columns.tolist()

    if f"{nuestro_seller}" in cols:
        # Reordenar para que nuestra empresa esté siempre primera en la leyenda
        cols.insert(0, cols.pop(cols.index(f"{nuestro_seller}")))
        df_para_grafico = df_para_grafico[cols]

        # Generar la lista de colores dinámicamente
        paleta_competidores = ['#FF4B4B', '#3498DB', '#9B59B6', '#E67E22', '#F1C40F']
        colores = ['#2ECC71'] # El primer color es siempre verde para nosotros

        # Añadir colores para el resto de las columnas, ciclando la paleta
        num_competidores = len(cols) - 1
        for i in range(num_competidores):
            colores.append(paleta_competidores[i % len(paleta_competidores)])

    return df_para_grafico, colores

# -----------------------------------------------------------------------------
# FUNCIÓN DE INTELIGENCIA ARTIFICIAL

@st.cache_data
def obtener_sugerencia_ia(contexto: dict):
    """Genera un análisis y sugerencias CONCISAS utilizando la IA Generativa de Google."""
    try:
        genai.configure(api_key=st.secrets.google_ai["api_key"])
        model = genai.GenerativeModel('gemini-2.5-pro')
    except Exception as e:
        return f"Error al configurar la API de IA: {e}."

    # Determinar si estamos compitiendo activamente o estamos fuera del contexto
    if isinstance(contexto.get('posicion'), int):
        # Escenario 1: Estamos compitiendo en el contexto actual
        prompt = f"""
        **Rol:** Eres un estratega senior de e-commerce para Mercado Libre, enfocado 100% en maximizar la RENTABILIDAD. Analizas datos para proponer acciones tácticas con un claro costo-beneficio.

        **Principios de Análisis (Obligatorios):**
        - **Rentabilidad Sobre Posición:** Tu objetivo no es ser el #1 a cualquier costo, sino maximizar el margen de ganancia.
        - **Análisis de Trade-Offs:** Cada recomendación debe explicar qué se gana y qué se sacrifica.
        - **Precisión Cuantitativa:** Evita sugerencias vagas. Si recomiendas un cambio de precio, especifica el nuevo precio exacto.
        - **Uso Inteligente de Atributos:** Envío FULL, Gratis y Cuotas son costos. Solo recomiéndalos si el análisis de la competencia lo justifica como una inversión necesaria para competir.

        **Proceso de Razonamiento Interno (Paso a Paso):**
        Antes de generar la respuesta final, realiza un análisis silencioso dentro de un bloque <pensamiento>. Sigue estos pasos:
        1.  Evalúa la brecha de precios con el líder. ¿Es agresiva?
        2.  Analiza el dominio de FULL. ¿Es un estándar de facto (>70%) o un diferenciador?
        3.  Considera nuestra posición actual. ¿Estamos cerca de liderar o muy lejos?
        4.  Basado en esto, formula dos hipótesis de acción distintas (ej. una agresiva, una conservadora).

        **Contexto del Análisis:**
        - Producto: "{contexto['producto']}"
        - Nuestra Empresa: "{contexto['nuestro_seller']}"
        - Nuestro Precio: ${contexto['nuestro_precio']:,.2f}
        - Nuestra Posición: #{contexto['posicion']}
        - Líder Actual: "{contexto['nombre_lider']}" a ${contexto['precio_lider']:,.2f}
        - Brecha con el líder: ${contexto['nuestro_precio'] - contexto['precio_lider']:,.2f}
        - Competidores en el contexto: {contexto['competidores_contexto']} de {contexto['total_competidores']} en total.
        - Dominio de FULL en el contexto: {contexto['pct_full']:.0f}%
        
        **Tarea:**
        1.  Completa tu Proceso de Razonamiento Interno en un bloque <pensamiento>.
        2.  Luego, basándote en tu razonamiento, genera la respuesta para el usuario siguiendo el formato obligatorio. NO MUESTRES EL BLOQUE <pensamiento> en la respuesta final.

        **Formato de Respuesta (Obligatorio y conciso):**
        1.  **Diagnóstico:** Un resumen ejecutivo de la situación actual en una sola frase.
        2.  **Opción 1 (Ej. "Estrategia de Conquista"):**
            * **Acción:** Una recomendación clara y CUANTIFICADA (ej. "Ajustar precio a $XX.XX").
            * **Justificación y Trade-Off:** El porqué de esta acción, mencionando explícitamente el costo/beneficio (ej. "Busca ganar la Buy Box sacrificando un 5% de margen.").
        3.  **Opción 2 (Ej. "Estrategia de Rentabilidad"):**
            * **Acción:** Una recomendación alternativa y CUANTIFICADA.
            * **Justificación y Trade-Off:** El porqué de esta segunda opción, explicando un enfoque diferente.

        **Restricciones:** No uses saludos ni introducciones. Sé directo, táctico y usa Markdown. La respuesta final para el usuario solo debe contener el Diagnóstico y las 2 Opciones.
        """
    else:
        # Escenario 2: No estamos compitiendo (Fuera de Filtro)
        # MEJORADO: Se mantiene la estructura y principios para consistencia
        prompt = f"""
        **Rol:** Eres "El Oráculo", un estratega senior de e-commerce para Mercado Libre, enfocado en identificar barreras de mercado y oportunidades de rentabilidad.

        **Principios de Análisis (Obligatorios):**
        - **Análisis de Barreras:** Identifica la razón más probable por la que no calificamos (Precio, FULL, Cuotas, etc.).
        - **Costo de Entrada:** Evalúa si el costo de superar esa barrera (ej. implementar FULL, bajar drásticamente el precio) se justifica con el potencial de venta.

        **NUEVO: Proceso de Razonamiento Interno (Paso a Paso):**
        Antes de la respuesta final, razona en un bloque <pensamiento>:
        1.  Compara el dominio de FULL con el hecho de que no estamos en el contexto. ¿Es esta la barrera principal?
        2.  Evalúa al líder. ¿Su precio es muy bajo? ¿Qué atributos tiene?
        3.  Determina el "costo" para entrar al contexto filtrado.
        4.  Concluye si la inversión parece rentable o si es mejor ceder este segmento.

        **Contexto del Mercado:**
        - Producto: "{contexto['producto']}"
        - Nuestra Empresa: "{contexto['nuestro_seller']}"
        - Líder Actual: "{contexto['nombre_lider']}" a ${contexto['precio_lider']:,.2f}
        - Competidores en este contexto: {contexto['competidores_contexto']} de {contexto['total_competidores']} en total.
        - Dominio de FULL en el contexto: {contexto['pct_full']:.0f}%

        **Tarea:**
        1.  Completa tu Proceso de Razonamiento Interno en un bloque <pensamiento>.
        2.  Luego, genera la respuesta para el usuario siguiendo el formato obligatorio. NO MUESTRES EL BLOQUE <pensamiento> en la respuesta final.

        **Formato de Respuesta (Obligatorio y conciso):**
        1.  **Diagnóstico:** Un análisis de la barrera de entrada principal en una sola frase.
        2.  **Recomendación Estratégica:**
            * **Acción:** Recomendar una acción clara: "Ignorar este segmento" o "Penetrar el segmento mediante...".
            * **Justificación y Trade-Off:** Explicar el costo/beneficio de la recomendación (ej. "Ignorar evita una guerra de precios costosa, cediendo potencial volumen" o "Implementar FULL requiere una inversión logística inicial para capturar X% del mercado.").

        **Restricciones:** No uses saludos. Sé directo y táctico. La respuesta final solo debe contener el Diagnóstico y la Recomendación.
        """

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error al generar la sugerencia de la IA: {e}"

def highlight_nuestro_seller(row, seller_name_to_highlight: str):
    """Función de estilo para resaltar nuestra fila en el DataFrame."""
    if row['nombre_vendedor'] == seller_name_to_highlight:
        return ['background-color: #1a3a2a; color: #2ECC71; font-weight: bold;'] * len(row)
    return [''] * len(row)

# -----------------------------------------------------------------------------
# CONFIGURACIÓN E INTERFAZ DEL DASHBOARD
def run_dashboard():
    # --- Toda la lógica y la interfaz de Streamlit deben estar DENTRO de esta función ---
    
    st.set_page_config(layout="wide", page_title="Análisis Táctico con IA")

    # Inicializar la variable de estado para la sugerencia de IA
    if 'sugerencia_ia' not in st.session_state:
        st.session_state.sugerencia_ia = None
    
    st.title("Análisis Táctico con Asistente IA")

    try:
        config_cliente = st.secrets["client_config"]
        TABLA_CRUDOS = config_cliente['tabla_crudos']
        NUESTRO_SELLER_NAME = config_cliente['seller_name']
    except Exception as e:
        st.error(f"Error: No se encontró la 'client_config' en los secretos. Detalles: {e}")
        st.stop()

    st.markdown(f"Análisis para **{NUESTRO_SELLER_NAME}**. Use los filtros para explorar el mercado.")


    productos_disponibles = get_product_list(TABLA_CRUDOS)

    if productos_disponibles:
        # --- LÓGICA PRINCIPAL DEL DASHBOARD (SI HAY DATOS) ---
        st.sidebar.header("Filtros Principales")
        producto_seleccionado = st.sidebar.selectbox("Seleccione un Producto", productos_disponibles)
        df_producto = get_product_data(TABLA_CRUDOS, producto_seleccionado)
        
        fecha_maxima = df_producto['fecha_extraccion'].max() if not df_producto.empty else datetime.date.today()
        fecha_minima = df_producto['fecha_extraccion'].min() if not df_producto.empty else fecha_maxima
        
        fecha_seleccionada = st.sidebar.date_input("Seleccione una Fecha", value=fecha_maxima, min_value=fecha_minima, max_value=fecha_maxima, format="DD/MM/YYYY")
        
        st.sidebar.header("Filtros de Contexto de Mercado")
        filtro_full = st.sidebar.checkbox("Solo con Envío FULL", value=False)
        filtro_gratis = st.sidebar.checkbox("Solo con Envío Gratis", value=False)
        filtro_factura_a = st.sidebar.checkbox("Solo con Factura A", value=False)
        filtro_cuotas = st.sidebar.slider("Mínimo de cuotas sin interés", 0, 12, 0)

        # --- Filtrado y Creación del Estado de Datos "Real" ---
        df_dia = df_producto[df_producto['fecha_extraccion'] == fecha_seleccionada].copy()
        nuestra_oferta_real = df_dia[df_dia['nombre_vendedor'] == NUESTRO_SELLER_NAME].copy()
        
        df_contexto_real = df_dia.copy()
        if filtro_full: df_contexto_real = df_contexto_real[df_contexto_real['envio_full'] == True]
        if filtro_gratis: df_contexto_real = df_contexto_real[df_contexto_real['envio_gratis'] == True]
        if filtro_factura_a: df_contexto_real = df_contexto_real[df_contexto_real['factura_a'] == True]
        if filtro_cuotas > 0: df_contexto_real = df_contexto_real[df_contexto_real['cuotas_sin_interes'] >= filtro_cuotas]
        
        df_contexto_sorted_real = df_contexto_real.sort_values(by='precio', ascending=True).reset_index(drop=True)
        nuestro_precio_real = nuestra_oferta_real['precio'].iloc[0] if not nuestra_oferta_real.empty else 0

        # --- Simulador de Escenarios ---
        st.sidebar.header("🧪 Simulador de Escenarios")
        nuevo_precio_simulado = st.sidebar.number_input("Probar un nuevo precio para mi producto", value=None, placeholder=f"Actual: ${nuestro_precio_real:,.2f}")

        # --- Lógica de Estado de Visualización ---
        df_contexto_display = df_contexto_sorted_real.copy()
        nuestro_precio_display = nuestro_precio_real
        modo_simulacion = False

        if nuevo_precio_simulado and nuevo_precio_simulado > 0:
            modo_simulacion = True
            df_simulacion = df_contexto_sorted_real.copy()
            if NUESTRO_SELLER_NAME in df_simulacion['nombre_vendedor'].values:
                df_simulacion.loc[df_simulacion['nombre_vendedor'] == NUESTRO_SELLER_NAME, 'precio'] = nuevo_precio_simulado
            elif not nuestra_oferta_real.empty:
                nuestra_fila = nuestra_oferta_real.iloc[[0]].copy()
                nuestra_fila.loc[:, 'precio'] = nuevo_precio_simulado
                df_simulacion = pd.concat([df_simulacion, nuestra_fila], ignore_index=True)
            
            df_contexto_display = df_simulacion.sort_values(by='precio').reset_index(drop=True)
            nuestro_precio_display = nuevo_precio_simulado

        if modo_simulacion:
            st.warning("**MODO SIMULACIÓN ACTIVADO** - Los datos mostrados reflejan el precio simulado.", icon="🧪")

        # --- **NUEVO** Cálculo centralizado y robusto de KPIs ---
        kpis = calcular_kpis(df_contexto_display, NUESTRO_SELLER_NAME, nuestro_precio_display)

        # --- Visualización de Título y Métricas ---
        st.header(f"[{producto_seleccionado}]({kpis['link_lider']})")
        st.caption(f"Fecha de análisis: {fecha_seleccionada.strftime('%d/%m/%Y')}")
        st.markdown("---")

        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric(label="🏆 Nuestra Posición (contexto)", value=f"{kpis['posicion_num']} de {kpis['cant_total']}" if kpis['posicion_num'] != 'N/A' else kpis['posicion_str'])
        with col2: st.metric(label="💲 Nuestro Precio", value=f"${nuestro_precio_display:,.2f}" if nuestro_precio_display > 0 else "N/A")
        with col3: st.metric(label="🥇 Precio Líder (contexto)", value=f"${kpis['precio_lider']:,.2f}" if kpis['precio_lider'] > 0 else "N/A")
        with col4:
            if nuestro_precio_display > 0 and kpis['precio_lider'] > 0:
                dif_vs_lider = nuestro_precio_display - kpis['precio_lider']
                delta_text = f"${(nuestro_precio_display - nuestro_precio_real):,.2f} vs. real" if modo_simulacion else None
                st.metric(label="💰 Diferencia vs. Líder", value=f"${dif_vs_lider:,.2f}", delta=delta_text, delta_color="off")
            else:
                st.metric(label="💰 Diferencia vs. Líder", value="N/A")

        st.markdown("---")

        # --- Gráfico Panorama de Precios ---
        st.subheader("Panorama de Precios")
        if not df_contexto_display.empty:
            df_plot = df_contexto_display[['nombre_vendedor', 'precio']].copy()
            
            df_plot['tipo'] = 'Competidor'
            df_plot['orden_render'] = 1
            
            # Usa el nombre del líder desde los KPIs ya calculados
            lider_vendedor_nombre = kpis['nombre_lider']
            
            if NUESTRO_SELLER_NAME in df_plot['nombre_vendedor'].values:
                nuestra_empresa_mask = df_plot['nombre_vendedor'] == NUESTRO_SELLER_NAME
                df_plot.loc[nuestra_empresa_mask, 'tipo'] = 'Nuestra Empresa'
                df_plot.loc[nuestra_empresa_mask, 'orden_render'] = 3
            
            if lider_vendedor_nombre != NUESTRO_SELLER_NAME:
                lider_mask = df_plot['nombre_vendedor'] == lider_vendedor_nombre
                df_plot.loc[lider_mask, 'tipo'] = 'Líder'
                df_plot.loc[lider_mask, 'orden_render'] = 2
            
            min_precio = df_plot['precio'].min()
            max_precio = df_plot['precio'].max()
            padding = (max_precio - min_precio) * 0.05
            if padding == 0: padding = min_precio * 0.05
            dominio_min = min_precio - padding
            dominio_max = max_precio + padding

            chart = alt.Chart(df_plot).mark_circle(size=120).encode(
                x=alt.X('precio:Q', title='Precio ($)', axis=alt.Axis(format='$,.0f'), scale=alt.Scale(domain=[dominio_min, dominio_max])),
                y=alt.Y('nombre_vendedor:N', title=None, sort='-x'),
                color=alt.Color('tipo:N', scale=alt.Scale(domain=['Líder', 'Nuestra Empresa', 'Competidor'], range=['#FF4B4B', '#2ECC71', '#3498DB']), legend=alt.Legend(title="Leyenda")),
                order=alt.Order('orden_render:Q', sort='ascending'),
                tooltip=['nombre_vendedor', alt.Tooltip('precio', format='$,.2f')]
            ).properties(height=300).interactive()
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No hay datos para mostrar en el gráfico de panorama de precios para el contexto seleccionado.")

        st.markdown("---")
        
        # --- Gráfico de Tendencia ---
        st.subheader("Evolución de Precios (Últimos 15 días)")
        df_tendencia = df_producto[df_producto['fecha_extraccion'] >= (fecha_maxima - datetime.timedelta(days=15))]

        if not df_tendencia.empty:
            df_grafico_tendencia, colores_tendencia = preparar_datos_tendencia(df_tendencia, NUESTRO_SELLER_NAME)

            if df_grafico_tendencia is not None and not df_grafico_tendencia.empty:
                st.info("Mostrando su empresa, el líder del día y los competidores con precio inferior al suyo. Puede hacer zoom vertical en el gráfico.")

                # 1. Reformatear datos para Altair (formato "largo")
                df_altair = df_grafico_tendencia.reset_index().melt('fecha_extraccion', var_name='serie', value_name='precio').dropna()

                # 2. Construir el gráfico base con líneas y puntos
                base = alt.Chart(df_altair).mark_line(point=True).encode(
                    x=alt.X('fecha_extraccion:T', axis=alt.Axis(format='%d/%m', title='Fecha', labelAngle=0), title='Fecha'),
                    y=alt.Y('precio:Q', axis=alt.Axis(format='$,.0f'), title='Precio'),
                    color=alt.Color('serie:N',
                                    scale=alt.Scale(domain=df_grafico_tendencia.columns.tolist(), range=colores_tendencia),
                                    legend=alt.Legend(title="Vendedor")),
                    tooltip=[
                        alt.Tooltip('serie', title='Vendedor'),
                        alt.Tooltip('fecha_extraccion', title='Fecha', format='%d/%m/%Y'),
                        alt.Tooltip('precio', title='Precio', format='$,.2f')
                    ]
                )

                # 3. Configurar interactividad para zoom SOLO en el eje Y
                zoom = alt.selection_interval(bind='scales', encodings=['y'])

                # 4. Crear el gráfico final y añadir la selección
                chart = base.add_params(
                    zoom
                ).properties(
                    height=400
                ).interactive()

                st.altair_chart(chart, use_container_width=True)
            else:
                st.info("No se encontraron competidores relevantes para mostrar en la tendencia histórica.")
        else:
            st.info("No hay suficientes datos históricos para mostrar una tendencia.")



        # --- ANÁLISIS CON IA ---
        st.subheader("Recomendaciones Estratégicas con IA")
        if not df_contexto_display.empty or kpis['posicion_str'] in ["Fuera de Filtro", "N/A"]:
            if st.button("🧠 Analizar Escenario con IA Pro"):
                with st.spinner("Contactando al estratega IA Pro... Este análisis puede tardar unos segundos..."):
                    pct_full_contexto = (df_contexto_display['envio_full'].sum() / len(df_contexto_display)) * 100 if len(df_contexto_display) > 0 else 0

                    # Crear el diccionario de contexto para la IA
                    contexto_ia = {
                        "producto": producto_seleccionado,
                        "nuestro_seller": NUESTRO_SELLER_NAME,
                        "nuestro_precio": nuestro_precio_display,
                        "posicion": kpis['posicion_num'] if kpis['posicion_num'] != 'N/A' else kpis['posicion_str'],
                        "nombre_lider": kpis['nombre_lider'],
                        "precio_lider": kpis['precio_lider'],
                        "competidores_contexto": kpis['cant_total'],
                        "total_competidores": len(df_dia),
                        "pct_full": pct_full_contexto
                    }
                    
                    sugerencia = obtener_sugerencia_ia(contexto_ia)
                    st.markdown(sugerencia)
        else:
            st.info("No hay competidores en el contexto seleccionado para realizar un análisis de IA.")

        st.markdown("---")

        # --- TABLA DE DATOS DETALLADA ---
        with st.expander("Ver tabla de competidores en el contexto filtrado", expanded=False):
            if not df_contexto_display.empty:
                columnas_tabla = ['nombre_vendedor', 'precio', 'cuotas_sin_interes', 'envio_full', 'envio_gratis', 'factura_a', 'reputacion_vendedor', 'link_publicacion']
                columnas_existentes_tabla = [col for col in columnas_tabla if col in df_contexto_display.columns]
                st.dataframe(
                    df_contexto_display[columnas_existentes_tabla].style.apply(highlight_nuestro_seller, seller_name_to_highlight=NUESTRO_SELLER_NAME, axis=1),
                    use_container_width=True, hide_index=True)
            else:
                st.write("Tabla vacía para el contexto actual.")

    else:
        # --- MENSAJE DE ADVERTENCIA (SI NO HAY DATOS) ---
        st.warning(f"No se encontraron datos en la tabla '{TABLA_CRUDOS}' en los últimos 30 días.")
        st.info(f"Verifique que el pipeline para '{NUESTRO_SELLER_NAME}' se haya ejecutado correctamente.")