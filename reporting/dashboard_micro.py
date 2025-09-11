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
# FUNCIONES DE FORMATO Y ESTILO
def format_price(price):
    """Formatea el precio con punto para miles y sin decimales."""
    if pd.isna(price):
        return "$ s/p"  # Sin precio
    try:
        price_int = int(price)
        formatted_with_commas = f"${price_int:,}"
        formatted_with_dots = formatted_with_commas.replace(',', '.')
        return formatted_with_dots
    except (ValueError, TypeError):
        return f"${price}"

def highlight_nuestro_seller(row, seller_name_to_highlight: str):
    """
    Función de estilo para resaltar nuestra fila en el DataFrame.
    Usa un color que funciona bien tanto en modo claro como oscuro.
    """
    if row['nombre_vendedor'] == seller_name_to_highlight:
        return ['color: 2EEC71; font-weight: bold;'] * len(row)
    return [''] * len(row)

# -----------------------------------------------------------------------------
# FUNCIÓN DE ANÁLISIS Y LÓGICA DE NEGOCIO

def calcular_kpis(df_contexto: pd.DataFrame, nuestro_seller: str, nuestro_precio: float):
    """
    Calcula los KPIs clave respetando la prioridad de ordenamiento.
    - sort_priority: 0 = nosotros, 1 = líder, 2 = resto
    - En caso de empate de precio, se aplica sort_priority.
    """
    kpis = {
        "posicion_num": "N/A",
        "posicion_str": "N/A",
        "cant_total": len(df_contexto),
        "nombre_lider": "N/A",
        "precio_lider": 0,
        "link_lider": "#"
    }

    if df_contexto.empty:
        kpis["posicion_str"] = "Fuera de Filtro" if nuestro_precio > 0 else "N/A"
        return kpis

    # Ordenar por precio y sort_priority
    sort_cols = ['precio']
    if 'sort_priority' in df_contexto.columns:
        sort_cols.append('sort_priority')

    df_contexto_sorted = df_contexto.sort_values(by=sort_cols, ascending=True).reset_index(drop=True)

    # Líder
    kpis["nombre_lider"] = df_contexto_sorted.iloc[0]['nombre_vendedor']
    kpis["precio_lider"] = df_contexto_sorted.iloc[0]['precio']
    kpis["link_lider"] = df_contexto_sorted.iloc[0].get('link_publicacion', '#')

    # Nuestra posición
    nuestra_pos_info = df_contexto_sorted[df_contexto_sorted['nombre_vendedor'] == nuestro_seller]

    if not nuestra_pos_info.empty:
        kpis["posicion_num"] = nuestra_pos_info.index[0] + 1
        kpis["posicion_str"] = f"{kpis['posicion_num']}"
    elif nuestro_precio > 0:
        kpis["posicion_str"] = "Fuera de Filtro"

    return kpis


def preparar_datos_tendencia(df_hist: pd.DataFrame, nuestro_seller: str):
    """
    Prepara el DataFrame para el gráfico de tendencias con saneamiento de datos
    y un método de agregación explícito (mínimo).
    
    Reglas de Visualización Estrictas:
    1. SIEMPRE se muestra la serie de precios de nuestra empresa.
    2. SE MUESTRA el historial del precio MÍNIMO de cualquier competidor cuyo 
       precio MÍNIMO en el día más reciente es ESTRICTAMENTE INFERIOR al nuestro.
    3. SE EXCLUYE a cualquier competidor cuyo precio MÍNIMO en el día más 
       reciente es superior o igual al nuestro.
    """
    if df_hist.empty:
        return None, None

    # PASO 0: Saneamiento de Datos
    df_hist_clean = df_hist.copy()
    df_hist_clean['precio'] = pd.to_numeric(df_hist_clean['precio'], errors='coerce')
    df_hist_clean.dropna(subset=['precio'], inplace=True)

    # PASO 1: Determinar el contexto de "hoy"
    if df_hist_clean.empty: return None, None
    fecha_maxima = df_hist_clean['fecha_extraccion'].max()
    df_hoy = df_hist_clean[df_hist_clean['fecha_extraccion'] == fecha_maxima]
    nuestra_oferta_hoy = df_hoy[df_hoy['nombre_vendedor'] == nuestro_seller]

    if nuestra_oferta_hoy.empty:
        df_solo_nosotros = df_hist_clean[df_hist_clean['nombre_vendedor'] == nuestro_seller]
        if df_solo_nosotros.empty: return None, None
        df_para_grafico = df_solo_nosotros.pivot_table(index='fecha_extraccion', columns='nombre_vendedor', values='precio', aggfunc='min')
        return df_para_grafico, ['#2ECC71']

    nuestro_precio_hoy = nuestra_oferta_hoy['precio'].min() # Usamos el mínimo por si también tenemos duplicados

    # PASO 2: Crear la lista definitiva de vendedores a mostrar
    vendedores_a_mostrar = set()
    vendedores_a_mostrar.add(nuestro_seller)
    
    # Agrupar por vendedor para obtener su precio MÍNIMO de hoy
    precios_minimos_hoy = df_hoy.groupby('nombre_vendedor')['precio'].min()
    competidores_amenaza_hoy = precios_minimos_hoy[precios_minimos_hoy < nuestro_precio_hoy]
    
    vendedores_a_mostrar.update(competidores_amenaza_hoy.index)

    # PASO 3: Construir el DataFrame final
    df_largo = df_hist_clean[df_hist_clean['nombre_vendedor'].isin(list(vendedores_a_mostrar))].copy()

    if df_largo.empty: return None, None

    # Si un vendedor tiene varios precios en un día, graficamos el más bajo.
    df_para_grafico = df_largo.pivot_table(
        index='fecha_extraccion',
        columns='nombre_vendedor',
        values='precio',
        aggfunc='min' 
    )

    # Lógica de colores (sin cambios)
    cols = df_para_grafico.columns.tolist()
    if nuestro_seller in cols:
        cols.insert(0, cols.pop(cols.index(nuestro_seller)))
        df_para_grafico = df_para_grafico[cols]
    
    paleta_competidores = ['#FF4B4B', '#3498DB', '#9B59B6', '#E67E22', '#F1C40F']
    colores = []
    
    for vendedor in cols:
        if vendedor == nuestro_seller:
            colores.append('#2ECC71')
        else:
            color_index = abs(hash(vendedor)) % len(paleta_competidores)
            colores.append(paleta_competidores[color_index])

    return df_para_grafico, colores

# -----------------------------------------------------------------------------
# FUNCIÓN DE INTELIGENCIA ARTIFICIAL

@st.cache_data
def obtener_sugerencia_ia(contexto: dict):
    """Genera un análisis y sugerencias CONCISAS utilizando la IA Generativa de Google."""
    try:
        genai.configure(api_key=st.secrets.google_ai["api_key"])
        model = genai.GenerativeModel('gemini-2.5-flash')
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
    """
    Resalta el texto de las columnas de texto clave en verde y negrita,
    ignorando las columnas con checkboxes para evitar errores de renderizado.
    """
    styles = [''] * len(row)  # Por defecto, sin estilo
    if row['nombre_vendedor'] == seller_name_to_highlight:
        
        style = 'color: #2ECC71; font-weight: bold;'
        
        # Itera sobre todas las columnas de la fila para aplicar estilo
        for i, col_name in enumerate(row.index):
            # No aplicar estilo a las columnas que renderizan como checkboxes
            if col_name not in ['envio_full', 'envio_gratis', 'factura_a']:
                styles[i] = style
                
    return styles

# -----------------------------------------------------------------------------
# CONFIGURACIÓN E INTERFAZ DEL DASHBOARD
def run_dashboard():
    
    st.set_page_config(layout="wide", page_title="Análisis Táctico con IA")

    st.markdown("""
        <style>
            div[data-testid="stSidebar"] div[data-testid="stWidgetLabel"] label {
                font-size: 0.9rem !important;
            }
        </style>
    """, unsafe_allow_html=True)
    
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

    productos_disponibles = get_product_list(TABLA_CRUDOS)

    if productos_disponibles:
        st.sidebar.title(f"{NUESTRO_SELLER_NAME}")

        st.sidebar.header("Filtros Principales")
        producto_seleccionado = st.sidebar.selectbox("Seleccione un Producto", productos_disponibles)
        df_producto = get_product_data(TABLA_CRUDOS, producto_seleccionado)
        
        fecha_maxima = df_producto['fecha_extraccion'].max() if not df_producto.empty else datetime.date.today()
        fecha_minima = df_producto['fecha_extraccion'].min() if not df_producto.empty else fecha_maxima
        
        fecha_seleccionada = st.sidebar.date_input("Seleccione una Fecha", value=fecha_maxima, min_value=fecha_minima, max_value=fecha_maxima, format="DD/MM/YYYY")
        
        st.sidebar.header("Filtros de Contexto")
        filtro_full = st.sidebar.checkbox("Solo con Envío FULL", value=False)
        filtro_gratis = st.sidebar.checkbox("Solo con Envío Gratis", value=False)
        filtro_factura_a = st.sidebar.checkbox("Solo con Factura A", value=False)
        filtro_cuotas = st.sidebar.slider("Mínimo de cuotas sin interés", 0, 12, 0)

        df_dia = df_producto[df_producto['fecha_extraccion'] == fecha_seleccionada].copy()
        nuestra_oferta_real = df_dia[df_dia['nombre_vendedor'] == NUESTRO_SELLER_NAME].copy()
        
        df_contexto_real = df_dia.copy()
        if filtro_full: df_contexto_real = df_contexto_real[df_contexto_real['envio_full'] == True]
        if filtro_gratis: df_contexto_real = df_contexto_real[df_contexto_real['envio_gratis'] == True]
        if filtro_factura_a: df_contexto_real = df_contexto_real[df_contexto_real['factura_a'] == True]
        if filtro_cuotas > 0: df_contexto_real = df_contexto_real[df_contexto_real['cuotas_sin_interes'] >= filtro_cuotas]
        
        nuestro_precio_real = nuestra_oferta_real['precio'].min() if not nuestra_oferta_real.empty else 0
        precio_lider_hoy = df_contexto_real['precio'].min() if not df_contexto_real.empty else 0


        st.sidebar.header("🧪 Simulador de Escenarios")
        nuevo_precio_simulado = st.sidebar.number_input(
            f"Probar nuevo precio (Actual: {format_price(nuestro_precio_real)})", 
            value=None, placeholder="Ingresa un valor..."
        )

        df_contexto_display = df_contexto_real.copy()
        nuestro_precio_display = nuestro_precio_real
        modo_simulacion = bool(nuevo_precio_simulado and nuevo_precio_simulado > 0)

        if modo_simulacion:
            st.warning("**MODO SIMULACIÓN ACTIVADO** - Los datos mostrados reflejan el precio simulado.", icon="🧪")
            df_simulacion = df_contexto_real.copy()
            if NUESTRO_SELLER_NAME in df_simulacion['nombre_vendedor'].values:
                df_simulacion.loc[df_simulacion['nombre_vendedor'] == NUESTRO_SELLER_NAME, 'precio'] = nuevo_precio_simulado
            elif not nuestra_oferta_real.empty:
                nuestra_fila = nuestra_oferta_real.iloc[[0]].copy()
                nuestra_fila.loc[:, 'precio'] = nuevo_precio_simulado
                df_simulacion = pd.concat([df_simulacion, nuestra_fila], ignore_index=True)
            
            df_contexto_display = df_simulacion.copy()
            nuestro_precio_display = nuevo_precio_simulado

        # --- Asignar sort_priority global ---
        df_contexto_display['sort_priority'] = 2
        df_contexto_display.loc[df_contexto_display['nombre_vendedor'] == NUESTRO_SELLER_NAME, 'sort_priority'] = 0

        # Identificar líder según precio + prioridad
        df_contexto_sorted = df_contexto_display.sort_values(by=['precio', 'sort_priority']).reset_index(drop=True)
        if not df_contexto_sorted.empty:
            lider_row = df_contexto_sorted.iloc[0]
            if lider_row['nombre_vendedor'] != NUESTRO_SELLER_NAME:
                df_contexto_display.loc[df_contexto_display['nombre_vendedor'] == lider_row['nombre_vendedor'], 'sort_priority'] = 1

        # KPIs usan df_contexto_sorted ya con prioridad
        kpis = calcular_kpis(df_contexto_sorted, NUESTRO_SELLER_NAME, nuestro_precio_display)

        posicion_num_hoy = kpis['posicion_num']
        posicion_num_ayer = "N/A"
        nuestro_precio_ayer = 0
        fecha_ayer = fecha_seleccionada - datetime.timedelta(days=1)
        df_ayer = df_producto[df_producto['fecha_extraccion'] == fecha_ayer].copy()

        if not df_ayer.empty:
            df_contexto_ayer = df_ayer.copy()
            if filtro_full: df_contexto_ayer = df_contexto_ayer[df_contexto_ayer['envio_full'] == True]
            if filtro_gratis: df_contexto_ayer = df_contexto_ayer[df_contexto_ayer['envio_gratis'] == True]
            if filtro_factura_a: df_contexto_ayer = df_contexto_ayer[df_contexto_ayer['factura_a'] == True]
            if filtro_cuotas > 0: df_contexto_ayer = df_contexto_ayer[df_contexto_ayer['cuotas_sin_interes'] >= filtro_cuotas]
            
            nuestra_oferta_ayer = df_ayer[df_ayer['nombre_vendedor'] == NUESTRO_SELLER_NAME].copy()
            nuestro_precio_ayer = nuestra_oferta_ayer['precio'].min() if not nuestra_oferta_ayer.empty else 0
            
            kpis_ayer = calcular_kpis(df_contexto_ayer, NUESTRO_SELLER_NAME, nuestro_precio_ayer)
            posicion_num_ayer = kpis_ayer['posicion_num']

        st.header(f"[{producto_seleccionado}]({kpis['link_lider']})")
        st.markdown("---")

        # --- Métricas con Escalador Integrado ---
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            if isinstance(posicion_num_hoy, int) and isinstance(posicion_num_ayer, int):
                cambio_puestos = posicion_num_hoy - posicion_num_ayer
                if cambio_puestos < 0:
                    flecha, color, texto = "⬇️", "green", f"{abs(cambio_puestos)} puestos"
                elif cambio_puestos > 0:
                    flecha, color, texto = "⬆️", "red", f"{abs(cambio_puestos)} puestos"
                else:
                    flecha, color, texto = "", "gray", "Sin cambios"
            else:
                flecha, color, texto = "", "gray", "Sin cambios"

            st.markdown(f"""
            <div style="text-align:center; font-size:1.2em;">
                <b>🏆 Nuestra Posición</b><br>
                <span style="font-size:1.5em;">{kpis['posicion_str']} de {kpis['cant_total']}</span><br>
                <span style="color:{color};">{flecha} {texto}</span>
            </div>
            """, unsafe_allow_html=True)

        # --- Columna 2: Nuestro Precio ---
        with col2:
            if nuestro_precio_display > 0 and nuestro_precio_ayer > 0:
                cambio_precio = nuestro_precio_display - nuestro_precio_ayer
                if cambio_precio < 0:
                    flecha, color = "⬇️", "green"
                elif cambio_precio > 0:
                    flecha, color = "⬆️", "red"
                else:
                    flecha, color = "", "gray"
                texto = f"{format_price(cambio_precio)} vs ayer" if cambio_precio != 0 else "Sin cambios"
            else:
                flecha, texto, color = "", "Sin cambios", "gray"

            st.markdown(f"""
            <div style="text-align:center; font-size:1.2em;">
                <b>💲 Nuestro Precio</b><br>
                <span style="font-size:1.5em;">{format_price(nuestro_precio_display) if nuestro_precio_display > 0 else "N/A"}</span><br>
                <span style="color:{color};">{flecha} {texto}</span>
            </div>
            """, unsafe_allow_html=True)

        # --- Columna 3: Precio Líder (Simplificado) ---
        with col3:
            st.markdown(f"""
            <div style="text-align:center; font-size:1.2em;">
                <b>🥇 Precio Líder</b><br>
                <span style="font-size:1.5em;">{format_price(kpis['precio_lider']) if kpis['precio_lider'] > 0 else 'N/A'}</span><br>
                <span style="color:transparent;">.</span> <!-- Placeholder para alinear verticalmente -->
            </div>
            """, unsafe_allow_html=True)

        # --- Columna 4: Diferencia vs. Líder (Simplificado) ---
        with col4:
            if nuestro_precio_display > 0 and kpis['precio_lider'] > 0:
                valor_dif = format_price(nuestro_precio_display - kpis['precio_lider'])
            else:
                valor_dif = "N/A"
            st.markdown(f"""
            <div style="text-align:center; font-size:1.2em;">
                <b>💰 Dif vs. Líder</b><br>
                <span style="font-size:1.5em;">{valor_dif}</span><br>
                <span style="color:transparent;">.</span> <!-- Placeholder para alinear verticalmente -->
            </div>
            """, unsafe_allow_html=True)

        st.markdown("---")
        
        graph_col1, graph_col2 = st.columns(2)

        graph_col1, graph_col2 = st.columns(2)

        with graph_col1:
            st.subheader("Panorama de Precios")
            # Usamos el df_contexto_display COMPLETO, sin filtrar filas.
            if not df_contexto_display.empty:
                df_plot = df_contexto_display[['nombre_vendedor', 'precio', 'sort_priority']].copy()
                df_plot['tipo'] = 'Competidor'

                somos_lider = (NUESTRO_SELLER_NAME == kpis['nombre_lider'])
                if somos_lider:
                    df_plot.loc[df_plot['nombre_vendedor'] == NUESTRO_SELLER_NAME, 'tipo'] = 'Nuestra Empresa (Líder)'
                    domain = ['Nuestra Empresa (Líder)', 'Competidor']
                    range_ = ['#2ECC71', '#3498DB']
                else:
                    df_plot.loc[df_plot['nombre_vendedor'] == kpis['nombre_lider'], 'tipo'] = 'Líder'
                    df_plot.loc[df_plot['nombre_vendedor'] == NUESTRO_SELLER_NAME, 'tipo'] = 'Nuestra Empresa'
                    domain = ['Líder', 'Nuestra Empresa', 'Competidor']
                    range_ = ['#FF4B4B', '#2ECC71', '#3498DB']

                df_plot['precio_formateado'] = df_plot['precio'].apply(format_price)

                # 1. Creamos un df temporal para determinar el orden basado en el PRECIO MÍNIMO de cada vendedor.
                df_sort_logic = df_plot.groupby('nombre_vendedor').agg(
                    min_precio=('precio', 'min'),
                    priority=('sort_priority', 'min') # La prioridad es la misma para todas sus publicaciones
                ).reset_index()

                # 2. Ordenamos este df temporal para obtener la secuencia correcta de vendedores.
                df_sort_logic_sorted = df_sort_logic.sort_values(by=['min_precio', 'priority'])
                
                # 3. Extraemos la lista de nombres de vendedores en el orden correcto.
                sort_order = df_sort_logic_sorted['nombre_vendedor'].tolist()

                chart_dot = alt.Chart(df_plot).mark_circle(size=120, opacity=0.8).encode(
                    x=alt.X('precio:Q', title='Precio',
                            axis=alt.Axis(labelExpr="'$' + replace(format(datum.value, ',.0f'), ',', '.')")),
                    # 4. Usamos la lista de orden INVERTIDA para el eje Y, para que el más barato quede abajo.
                    y=alt.Y('nombre_vendedor:N', sort=sort_order[::-1], title=None),
                    color=alt.Color('tipo:N', scale=alt.Scale(domain=domain, range=range_),
                                    legend=alt.Legend(title="Leyenda", orient="top")),
                    tooltip=['nombre_vendedor', alt.Tooltip('precio_formateado', title='Precio')]
                ).properties(height=350).interactive()
                st.altair_chart(chart_dot, use_container_width=True)
            else:
                st.info("No hay datos para mostrar en el panorama de precios para el contexto seleccionado.")

        with graph_col2:
            st.subheader("Evolución de Precios")
            df_tendencia = df_producto[df_producto['fecha_extraccion'] >= (fecha_maxima - datetime.timedelta(days=15))]
            if not df_tendencia.empty:
                df_grafico_tendencia, colores_tendencia = preparar_datos_tendencia(df_tendencia, NUESTRO_SELLER_NAME)
                if df_grafico_tendencia is not None and not df_grafico_tendencia.empty:
                    df_altair = df_grafico_tendencia.reset_index().melt('fecha_extraccion', var_name='serie', value_name='precio').dropna()
                    
                    df_altair['precio_formateado'] = df_altair['precio'].apply(format_price)

                    base = alt.Chart(df_altair).mark_line(point=True).encode(
                        x=alt.X('fecha_extraccion:T', axis=alt.Axis(format='%d/%m', title='Fecha', labelAngle=0)),
                        y=alt.Y('precio:Q', title='Precio',
                                axis=alt.Axis(labelExpr="'$' + replace(format(datum.value, ',.0f'), ',', '.')")),
                        color=alt.Color('serie:N', scale=alt.Scale(domain=df_grafico_tendencia.columns.tolist(), range=colores_tendencia), legend=alt.Legend(title="Vendedor", orient="top")),
                        tooltip=[alt.Tooltip('serie', title='Vendedor'), alt.Tooltip('fecha_extraccion:T', title='Fecha', format='%d/%m/%Y'), alt.Tooltip('precio_formateado', title='Precio')]
                    )
                    chart = base.add_params(alt.selection_interval(bind='scales', encodings=['y'])).properties(height=350).interactive()
                    st.altair_chart(chart, use_container_width=True)
                else:
                    st.info("No se encontraron competidores relevantes para mostrar en la tendencia histórica.")
            else:
                st.info("No hay suficientes datos históricos para mostrar una tendencia.")
        
        st.markdown("---")
        st.subheader("Asistente Estratégico IA")
        
        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if st.button("🧠 Analizar Escenario con IA", use_container_width=True):
                with st.spinner("Contactando al estratega IA..."):
                    pct_full_contexto = (df_contexto_display['envio_full'].sum() / len(df_contexto_display)) * 100 if not df_contexto_display.empty else 0
                    contexto_ia = {
                        "producto": producto_seleccionado, "nuestro_seller": NUESTRO_SELLER_NAME,
                        "nuestro_precio": nuestro_precio_display, "posicion": kpis['posicion_num'] if kpis['posicion_num'] != 'N/A' else kpis['posicion_str'],
                        "nombre_lider": kpis['nombre_lider'], "precio_lider": kpis['precio_lider'],
                        "competidores_contexto": kpis['cant_total'], "total_competidores": len(df_dia),
                        "pct_full": pct_full_contexto
                    }
                    st.session_state.sugerencia_ia = obtener_sugerencia_ia(contexto_ia)

        with btn_col2:
            st.button("⚡ Crear alerta (Próximamente)", disabled=True, use_container_width=True)

        if st.session_state.sugerencia_ia:
            st.markdown(st.session_state.sugerencia_ia)
        
        st.markdown("---")

        with st.expander("Ver tabla de competidores en el contexto filtrado", expanded=False):
            if not df_contexto_display.empty:
                # 1. Ordena el DataFrame original que SÍ contiene 'sort_priority'.
                df_sorted = df_contexto_display.sort_values(by=['precio', 'sort_priority']).reset_index(drop=True)

                # 2. Define las columnas que quieres mostrar al final.
                columnas_a_mostrar = ['nombre_vendedor', 'precio', 'cuotas_sin_interes', 'envio_full', 'envio_gratis', 'factura_a', 'reputacion_vendedor', 'link_publicacion']
                columnas_existentes = [col for col in columnas_a_mostrar if col in df_sorted.columns]
                
                # 3. Crea el DataFrame final para mostrar, seleccionando las columnas del DataFrame YA ordenado.
                df_tabla_display = df_sorted[columnas_existentes].copy()
                
                # 4. Aplica el formato de precio.
                if 'precio' in df_tabla_display.columns:
                    df_tabla_display['precio'] = df_tabla_display['precio'].apply(format_price)

                st.dataframe(
                    df_tabla_display.style.apply(highlight_nuestro_seller, seller_name_to_highlight=NUESTRO_SELLER_NAME, axis=1),
                    use_container_width=True, hide_index=True)
            else:
                st.write("Tabla vacía para el contexto actual.")

    else:
        st.warning(f"No se encontraron datos en la tabla '{TABLA_CRUDOS}' en los últimos 30 días.")
        st.info(f"Verifique que el pipeline para '{NUESTRO_SELLER_NAME}' se haya ejecutado correctamente.")

if __name__ == "__main__":
    run_dashboard()
