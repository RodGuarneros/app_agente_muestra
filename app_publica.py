from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import List, Tuple
import re
import pandas as pd
import streamlit as st
from streamlit_lottie import st_lottie
import requests
import time


@st.cache_data
def load_lottie(url: str):
    r = requests.get(url, timeout=10)
    if r.status_code != 200:
        return None
    return r.json()

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "retail_mobile.db"
DOCS_DIR = BASE_DIR / "docs"

st.set_page_config(page_title="Retail Mobile Commerce Assistant", layout="wide")

st.markdown("""
<style>
/* Fondo general */
html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
    background: #F7FAF8 !important;
    color: #0E1B16 !important;
}

/* Header superior */
[data-testid="stHeader"] {
    background: #F7FAF8 !important;
}

/* Toolbar superior derecha */
[data-testid="stToolbar"] {
    background: #F7FAF8 !important;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: #EAF6EF !important;
}

/* Zona principal */
[data-testid="stMain"] {
    background: #F7FAF8 !important;
}

[data-testid="stMainBlockContainer"] {
    background: #F7FAF8 !important;
}

/* Contenedor general de bloques */
.block-container {
    background: #F7FAF8 !important;
    padding-bottom: 2rem !important;
}

/* Evita bandas negras en columnas / contenedores */
[data-testid="column"] {
    background: transparent !important;
}

[data-testid="stVerticalBlock"] {
    background: transparent !important;
}

/* Zona del chat input fija abajo */
[data-testid="stChatInput"] {
    background: #F7FAF8 !important;
}

[data-testid="stChatInput"] > div {
    background: #F7FAF8 !important;
}

/* Banda inferior donde a veces Streamlit deja oscuro */
[data-testid="ScrollToBottomContainer"] {
    background: #F7FAF8 !important;
}

/* Formularios y contenedores cercanos al input */
[data-testid="stForm"] {
    background: transparent !important;
}

/* Inputs normales */
input, textarea {
    background: #FFFFFF !important;
    color: #0E1B16 !important;
}

/* Si algún iframe o elemento embebido arrastra fondo oscuro */
iframe {
    background: transparent !important;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>
html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
    background-color: #FFFFFF !important;
    color: #111111 !important;
}

[data-testid="stHeader"] {
    background: #FFFFFF !important;
}

[data-testid="stToolbar"] {
    background: #FFFFFF !important;
}

[data-testid="stSidebar"] {
    background-color: #EEF8F1 !important;
}

[data-testid="stMainBlockContainer"] {
    background-color: #FFFFFF !important;
}

section.main > div {
    background-color: #FFFFFF !important;
}

div.block-container {
    background-color: #FFFFFF !important;
}
</style>
""", unsafe_allow_html=True)

MAX_TURNS = 8

if "chats" not in st.session_state:
    st.session_state.chats = {"Nuevo chat": []}

if "current_chat" not in st.session_state:
    st.session_state.current_chat = "Nuevo chat"

if "new_chat_counter" not in st.session_state:
    st.session_state.new_chat_counter = 1

if "scatter_mode" not in st.session_state:
    st.session_state.scatter_mode = False

if "scatter_step" not in st.session_state:
    st.session_state.scatter_step = None

if "scatter_df" not in st.session_state:
    st.session_state.scatter_df = None

if "scatter_x" not in st.session_state:
    st.session_state.scatter_x = None

if "scatter_numeric_cols" not in st.session_state:
    st.session_state.scatter_numeric_cols = []

if "welcome_shown" not in st.session_state:
    st.session_state.welcome_shown = {}

if "pending_welcome_for_chat" not in st.session_state:
    st.session_state.pending_welcome_for_chat = None

# -----------------------------
# Helpers
# -----------------------------

def write_typing_effect(text: str, placeholder, speed: float = 0.018):
    rendered = ""
    for ch in text:
        rendered += ch
        placeholder.markdown(rendered + "▌")
        time.sleep(speed)
    placeholder.markdown(rendered)


def get_welcome_message() -> str:
    return (
        "Hola, soy tu asistente de retail commerce. "
        "Fui creado para ayudarte a consultar productos, precios, inventario, "
        "estadísticas, comparaciones y algunas políticas del demo. "
        "También puedo ayudarte a explorar datos con tablas y gráficas."
    )


def get_farewell_response(question: str) -> str | None:
    q = normalize_text(question)

    farewell_patterns = [
        "gracias",
        "muchas gracias",
        "adios",
        "adiós",
        "bye",
        "nos vemos",
        "hasta luego",
        "hasta pronto",
        "perfecto gracias",
        "ok gracias",
    ]

    if any(p in q for p in farewell_patterns):
        return (
            "Gracias a ti.\n\n"
            "Fue un gusto ayudarte. Vuelve pronto; estaré aquí para apoyarte con "
            "productos, precios, inventario y análisis del catálogo. Quedo a tus órdenes."
        )

    return None

def get_connection() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)

def load_docs() -> List[str]:
    docs = []
    if DOCS_DIR.exists():
        for fp in DOCS_DIR.glob("*.txt"):
            docs.append(fp.read_text(encoding="utf-8"))
    return docs

def keyword_retriever(question: str, docs: List[str], top_k: int = 2) -> List[str]:
    q_words = [w.strip("¿?.,:;!").lower() for w in question.split() if len(w) > 2]
    scored = []
    for doc in docs:
        score = sum(1 for w in q_words if w in doc.lower())
        scored.append((score, doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [doc for score, doc in scored[:top_k] if score > 0]

def classify_question(question: str) -> str:
    q = normalize_text(question)

    docs_keywords = [
        "politica", "política",
        "devolucion", "devolución", "devoluciones",
        "entrega",
        "envio", "envío",
        "soporte",
        "funciones",
        "app",
        "reembolso",
        "policy", "policies",
        "refund", "returns", "support",
    ]

    sql_keywords = [
        "precio", "precios", "price", "prices",
        "stock", "inventario", "inventory",
        "pedido", "pedidos", "order", "orders",
        "orden", "ordenes", "órdenes",
        "ventas", "sale", "sales", "revenue", "ingresos",
        "store", "stores", "tienda", "tiendas",
        "producto", "productos", "product", "products",
        "rating", "ratings",
        "promedio", "media", "average", "mean",
        "minimo", "mínimo", "minimum", "min",
        "maximo", "máximo", "maximum", "max",
        "estadistico", "estadísticos", "estadisticos",
        "estadistica", "estadísticas", "estadisticas",
        "statistics", "stats", "summary", "resumen",
        "diagnostico", "diagnóstico", "diagnostic",
        "caro", "caros", "expensive",
        "barato", "baratos", "cheap", "cheapest",
        "costoso", "costosos",
        "economico", "económico",
        "mayor", "menor", "alto", "bajo",
        "highest", "lowest",
        "top", "categoria", "categoría", "category", "categories",
        "scatter", "dispersion", "dispersión",
        "correlacion", "correlación",
        "relacion", "relación", "relationship", "correlation",
        "dato", "datos", "detail", "details",
        "informacion", "información", "information",
    ]

    if any(k in q for k in docs_keywords):
        return "docs"

    if extract_products_from_question(q):
        return "sql"

    if any(k in q for k in sql_keywords):
        return "sql"

    return "docs"

def run_sql_router(question: str) -> Tuple[str, pd.DataFrame | None]:
    q = normalize_text(question)
    conn = get_connection()

    # -----------------------------
    # Scatter
    # -----------------------------
    if wants_scatter_request(q):
        sql = """
        SELECT product_name, category, price, stock, rating
        FROM products
        WHERE price IS NOT NULL
          AND stock IS NOT NULL
        """
        df = pd.read_sql_query(sql, conn)
        conn.close()
        return "Encontré datos con variables numéricas para construir un scatter.", df

    # -----------------------------
    # Estadísticas generales
    # -----------------------------
    if wants_any_stats(q) and not wants_price_stats(q) and not wants_stock_stats(q):
        sql = """
        SELECT 'count_products' AS metric, COUNT(*) AS value FROM products
        UNION ALL
        SELECT 'avg_price' AS metric, ROUND(AVG(price), 2) AS value FROM products
        UNION ALL
        SELECT 'min_price' AS metric, ROUND(MIN(price), 2) AS value FROM products
        UNION ALL
        SELECT 'max_price' AS metric, ROUND(MAX(price), 2) AS value FROM products
        UNION ALL
        SELECT 'sum_stock' AS metric, ROUND(SUM(stock), 2) AS value FROM products
        UNION ALL
        SELECT 'avg_stock' AS metric, ROUND(AVG(stock), 2) AS value FROM products
        UNION ALL
        SELECT 'min_stock' AS metric, ROUND(MIN(stock), 2) AS value FROM products
        UNION ALL
        SELECT 'max_stock' AS metric, ROUND(MAX(stock), 2) AS value FROM products
        """
        df = pd.read_sql_query(sql, conn)
        conn.close()
        return "Calculé un resumen estadístico general del catálogo.", df

    # -----------------------------
    # Estadísticas de precios
    # -----------------------------
    if (wants_average(q) and wants_price_stats(q)) or (is_basic_stats_request(q) and wants_price_stats(q)):
        sql = """
        SELECT 'count_products' AS metric, COUNT(*) AS value FROM products
        UNION ALL
        SELECT 'avg_price' AS metric, ROUND(AVG(price), 2) AS value FROM products
        UNION ALL
        SELECT 'min_price' AS metric, ROUND(MIN(price), 2) AS value FROM products
        UNION ALL
        SELECT 'max_price' AS metric, ROUND(MAX(price), 2) AS value FROM products
        """
        df = pd.read_sql_query(sql, conn)
        conn.close()
        return "Calculé los estadísticos básicos de precios del catálogo.", df

    # -----------------------------
    # Estadísticas de stock
    # -----------------------------
    if (wants_average(q) and wants_stock_stats(q)) or (is_basic_stats_request(q) and wants_stock_stats(q)):
        sql = """
        SELECT 'count_products' AS metric, COUNT(*) AS value FROM products
        UNION ALL
        SELECT 'sum_stock' AS metric, ROUND(SUM(stock), 2) AS value FROM products
        UNION ALL
        SELECT 'avg_stock' AS metric, ROUND(AVG(stock), 2) AS value FROM products
        UNION ALL
        SELECT 'min_stock' AS metric, ROUND(MIN(stock), 2) AS value FROM products
        UNION ALL
        SELECT 'max_stock' AS metric, ROUND(MAX(stock), 2) AS value FROM products
        """
        df = pd.read_sql_query(sql, conn)
        conn.close()
        return "Calculé los estadísticos básicos de inventario del catálogo.", df

    # -----------------------------
    # Promedios por categoría
    # -----------------------------
    if wants_category_average(q):
        if wants_price_stats(q) and not wants_stock_stats(q):
            sql = """
            SELECT
                category,
                ROUND(AVG(price), 2) AS avg_price
            FROM products
            GROUP BY category
            ORDER BY avg_price DESC
            """
            df = pd.read_sql_query(sql, conn)
            conn.close()
            return "Este es el precio promedio por categoría:", df

        if wants_stock_stats(q) and not wants_price_stats(q):
            sql = """
            SELECT
                category,
                ROUND(AVG(stock), 2) AS avg_stock
            FROM products
            GROUP BY category
            ORDER BY avg_stock DESC
            """
            df = pd.read_sql_query(sql, conn)
            conn.close()
            return "Este es el stock promedio por categoría:", df

        sql = """
        SELECT
            category,
            ROUND(AVG(price), 2) AS avg_price,
            ROUND(AVG(stock), 2) AS avg_stock
        FROM products
        GROUP BY category
        ORDER BY avg_price DESC
        """
        df = pd.read_sql_query(sql, conn)
        conn.close()
        return "Este es el resumen promedio por categoría:", df

    # -----------------------------
    # Vista general de precios
    # -----------------------------
    if (
        q in ["precio", "precios", "price", "prices"]
        or "dame los precios" in q
        or "muestrame los precios" in q
        or "muéstrame los precios" in question.lower()
        or "lista de precios" in q
        or "catalogo de precios" in q
        or "catálogo de precios" in question.lower()
    ):
        sql = """
        SELECT product_name, category, price, stock, promo
        FROM products
        ORDER BY price DESC
        """
        df = pd.read_sql_query(sql, conn)
        conn.close()

        if df.empty:
            return "No encontré precios en el catálogo.", None

        return "Esta es una vista general de precios del catálogo:", df

    # -----------------------------
    # Lista de productos más baratos
    # -----------------------------
    if (
        (
            "precios mas baratos" in q
            or "precios más baratos" in question.lower()
            or "productos mas baratos" in q
            or "productos más baratos" in question.lower()
            or "los mas baratos" in q
            or "los más baratos" in question.lower()
            or "baratos" in q
        )
    ):
        top_n = extract_top_n(q, default=5)

        sql = f"""
        SELECT product_name, category, price, stock, promo
        FROM products
        ORDER BY price ASC
        LIMIT {top_n}
        """
        df = pd.read_sql_query(sql, conn)
        conn.close()

        if df.empty:
            return "No encontré productos baratos en el catálogo.", None

        return f"Estos son los {top_n} productos más baratos:", df
    # -----------------------------
    # Top N más caros
    # -----------------------------
    if (
        wants_top_query(q)
        and (
            "caros" in q
            or "mas caros" in q
            or "más caros" in question.lower()
            or "costosos" in q
            or "más costosos" in question.lower()
        )
    ):
        top_n = extract_top_n(q, default=5)
        sql = f"""
        SELECT product_name, category, price, stock, promo
        FROM products
        ORDER BY price DESC
        LIMIT {top_n}
        """
        df = pd.read_sql_query(sql, conn)
        conn.close()
        return f"Estos son los {top_n} productos más caros:", df
    
    # -----------------------------
    # Top N con mayor stock
    # -----------------------------
    if (
        wants_top_query(q)
        and ("stock" in q or "inventario" in q)
        and ("mayor" in q or "mas" in q or "más" in question.lower() or "alto" in q)
    ):
        top_n = extract_top_n(q, default=5)
        sql = f"""
        SELECT product_name, category, price, stock, promo
        FROM products
        ORDER BY stock DESC
        LIMIT {top_n}
        """
        df = pd.read_sql_query(sql, conn)
        conn.close()
        return f"Estos son los {top_n} productos con mayor stock:", df
 
    # -----------------------------
    # Top N con menor stock
    # -----------------------------
    if (
        wants_top_query(q)
        and ("stock" in q or "inventario" in q)
        and ("menor" in q or "menos" in q or "bajo" in q)
    ):
        top_n = extract_top_n(q, default=5)
        sql = f"""
        SELECT product_name, category, price, stock, promo
        FROM products
        ORDER BY stock ASC
        LIMIT {top_n}
        """
        df = pd.read_sql_query(sql, conn)
        conn.close()
        return f"Estos son los {top_n} productos con menor stock:", df
    
    # -----------------------------
    # Bajo inventario = por debajo del promedio
    # -----------------------------
    if (
        "bajo inventario" in q
        or "bajo stock" in q
        or "inventario bajo" in q
        or "stock bajo" in q
        or "inventario critico" in q
        or "inventario crítico" in question.lower()
        or "inventario mas critico" in q
        or "inventario más crítico" in question.lower()
    ):
        sql = """
        SELECT
            product_name,
            category,
            stock,
            price,
            promo,
            ROUND((SELECT AVG(stock) FROM products), 2) AS avg_stock
        FROM products
        WHERE stock < (SELECT AVG(stock) FROM products)
        ORDER BY stock ASC
        """
        df = pd.read_sql_query(sql, conn)
        conn.close()

        if df.empty:
            return "No encontré productos con inventario por debajo del promedio.", None

        avg_stock = float(df["avg_stock"].iloc[0])
        df = df.drop(columns=["avg_stock"])

        return f"Estos son los productos con inventario por debajo del promedio ({avg_stock:,.2f}):", df

    # -----------------------------
    # Mayor stock
    # -----------------------------
    if (
        "mayor stock" in q
        or "mas stock" in q
        or "más stock" in question.lower()
        or "con mayor stock" in q
        or "con mas stock" in q
        or "mayor inventario" in q
        or "más inventario" in question.lower()
    ):
        sql = """
        SELECT product_name, category, price, stock, promo
        FROM products
        WHERE stock = (SELECT MAX(stock) FROM products)
        """
        df = pd.read_sql_query(sql, conn)
        conn.close()
        return "Estos son los productos con mayor stock del catálogo:", df

    # -----------------------------
    # Menor stock
    # -----------------------------
    if (
        "menor stock" in q
        or "menos stock" in q
        or "con menor stock" in q
        or "con menos stock" in q
        or "menor inventario" in q
        or "menos inventario" in q
    ):
        sql = """
        SELECT product_name, category, price, stock, promo
        FROM products
        WHERE stock = (SELECT MIN(stock) FROM products)
        """
        df = pd.read_sql_query(sql, conn)
        conn.close()
        return "Estos son los productos con menor stock del catálogo:", df

    # -----------------------------
    # Más caro
    # -----------------------------
    if (
        "mas caro" in q
        or "más caro" in question.lower()
        or "mayor precio" in q
        or "mas costoso" in q
        or "más costoso" in question.lower()
    ):
        sql = """
        SELECT product_name, category, price, stock, promo
        FROM products
        WHERE price = (SELECT MAX(price) FROM products)
        """
        df = pd.read_sql_query(sql, conn)
        conn.close()
        return "Estos son los productos más caros del catálogo:", df

    # -----------------------------
    # Más barato (singular)
    # -----------------------------
    if (
        (
            "mas barato" in q
            or "más barato" in question.lower()
            or "menor precio" in q
            or "mas economico" in q
            or "más economico" in question.lower()
            or "mas económico" in question.lower()
            or "más económico" in question.lower()
        )
        and "baratos" not in q
        and "precios" not in q
        and "productos" not in q
    ):
        sql = """
        SELECT product_name, category, price, stock, promo
        FROM products
        WHERE price = (SELECT MIN(price) FROM products)
        """
        df = pd.read_sql_query(sql, conn)
        conn.close()
        return "Este es el producto más barato del catálogo:", df
    
    # -----------------------------
    # Búsqueda de uno o varios productos específicos
    # -----------------------------
    products = extract_products_from_question(q)

    if products:
        like_clauses = " OR ".join(
            [f"LOWER(product_name) LIKE '%{p}%'" for p in products]
        )

        sql = f"""
        SELECT product_name, category, price, stock, promo
        FROM products
        WHERE {like_clauses}
        ORDER BY price DESC
        """
        df = pd.read_sql_query(sql, conn)
        conn.close()

        if df.empty:
            return f"No encontré productos específicos para: {', '.join(products)}.", None

        return f"Encontré información para: {', '.join(products)}", df



    # -----------------------------
    # Ingresos máximos por tienda
    # -----------------------------
    if (
        "mayores ingresos" in q
        or "mas ingresos" in q
        or "más ingresos" in question.lower()
        or "tienda con mayores ingresos" in q
        or "store con mayores ingresos" in q
        or "store mas rentable" in q
        or "store más rentable" in question.lower()
    ):
        sql = """
        WITH revenue_by_store AS (
            SELECT
                store_id,
                ROUND(SUM(total), 2) AS revenue
            FROM orders
            WHERE status IN ('confirmed', 'shipped', 'delivered')
            GROUP BY store_id
        )
        SELECT store_id, revenue
        FROM revenue_by_store
        WHERE revenue = (SELECT MAX(revenue) FROM revenue_by_store)
        """
        df = pd.read_sql_query(sql, conn)
        conn.close()
        return "Estas son las tiendas con mayores ingresos:", df

    # -----------------------------
    # Precio por producto detectado
    # -----------------------------
    if "precio" in q:
        products = extract_products_from_question(q)

        if len(products) >= 1:
            like_clauses = " OR ".join(
                [f"LOWER(product_name) LIKE '%{p}%'" for p in products]
            )

            sql = f"""
            SELECT product_name, category, price, stock, promo
            FROM products
            WHERE {like_clauses}
            """
            df = pd.read_sql_query(sql, conn)
            conn.close()

            if df.empty:
                return "No encontré productos relacionados en el catálogo.", None

            return f"Encontré información para: {', '.join(products)}", df
        
    # -----------------------------
    # Cancelaciones / estatus
    # -----------------------------
    if "cancel" in q or "cancelado" in q or "cancelados" in q:
        sql = """
        SELECT status, COUNT(*) AS total_orders
        FROM orders
        GROUP BY status
        """
        df = pd.read_sql_query(sql, conn)
        conn.close()
        return "Resumen de órdenes por estatus:", df

    # -----------------------------
    # Ventas / ingresos
    # -----------------------------
    if "ventas" in q or "revenue" in q or "ingresos" in q:
        sql = """
        SELECT store_id, ROUND(SUM(total), 2) AS revenue
        FROM orders
        WHERE status IN ('confirmed', 'shipped', 'delivered')
        GROUP BY store_id
        ORDER BY revenue DESC
        """
        df = pd.read_sql_query(sql, conn)
        conn.close()
        return "Ingresos por tienda:", df

    # -----------------------------
    # Vista general de inventario
    # -----------------------------
    if "stock" in q or "inventario" in q:
        sql = """
        SELECT product_name, category, stock, price, promo
        FROM products
        ORDER BY stock ASC
        """
        df = pd.read_sql_query(sql, conn)
        conn.close()
        return "Esta es una vista general del inventario, ordenada de menor a mayor stock:", df

    # -----------------------------
    # Evitar fallback genérico cuando el usuario pidió productos específicos
    # -----------------------------
    if wants_product_lookup(q):
        conn.close()
        return "No identifiqué con claridad los productos solicitados. Intenta con nombres como iPhone, Xiaomi, Samsung, funda, tablet o cargador.", None

    # -----------------------------
    # Fallback
    # -----------------------------
    sql = """
    SELECT product_name, category, price, stock, promo
    FROM products
    ORDER BY rating DESC, price DESC
    LIMIT 8
    """

    df = pd.read_sql_query(sql, conn)
    conn.close()
    return "Mostrando algunos productos destacados:", df

def get_price_extremes() -> tuple[pd.DataFrame, pd.DataFrame]:
    conn = get_connection()

    cheapest_df = pd.read_sql_query("""
        SELECT product_name, category, price, stock, promo
        FROM products
        WHERE price = (SELECT MIN(price) FROM products)
    """, conn)

    expensive_df = pd.read_sql_query("""
        SELECT product_name, category, price, stock, promo
        FROM products
        WHERE price = (SELECT MAX(price) FROM products)
    """, conn)

    conn.close()
    return cheapest_df, expensive_df

def answer_with_docs(question: str) -> str:
    docs = load_docs()
    selected_docs = keyword_retriever(question, docs, top_k=2)

    if not selected_docs:
        return "La POC todavía no contiene esa información."

    context = "\n\n".join(selected_docs).strip()

    if not context:
        return "La POC todavía no contiene esa información."

    max_chars = 900
    context = context[:max_chars].strip()

    return (
        "Encontré esta información en la documentación del demo:\n\n"
        f"{context}"
    )


def get_general_help_response(question: str) -> str | None:
    q = question.lower().strip()

    general_patterns = [
        "hola",
        "hello",
        "hi",
        "buenas",
        "buenos días",
        "buenas tardes",
        "qué haces",
        "que haces",
        "en qué me puedes ayudar",
        "en que me puedes ayudar",
        "qué puedes hacer",
        "que puedes hacer",
        "ayuda",
        "help",
    ]

    if any(p in q for p in general_patterns):
        return (
            "Puedo ayudarte con este demo de retail mobile commerce. "
            "Por ejemplo, puedo responder preguntas sobre productos, precios, "
            "inventario, pedidos, promociones, devoluciones, métodos de pago "
            "y políticas de entrega."
        )

    return None    


def get_current_history():
    return st.session_state.chats[st.session_state.current_chat]

def normalize_chat_title(text: str, max_len: int = 38) -> str:
    clean = " ".join(text.strip().split())
    if len(clean) <= max_len:
        return clean
    return clean[:max_len].rstrip() + "..."

def ensure_first_user_message_as_title(user_text: str):
    current = st.session_state.current_chat
    history = st.session_state.chats[current]

    # solo renombrar si el chat actual está vacío y sigue siendo uno nuevo
    if len(history) == 0 and current.startswith("Nuevo chat"):
        new_title = normalize_chat_title(user_text)

        # evitar colisiones de nombre
        original_title = new_title
        suffix = 2
        while new_title in st.session_state.chats:
            new_title = f"{original_title} ({suffix})"
            suffix += 1

        st.session_state.chats[new_title] = st.session_state.chats.pop(current)
        st.session_state.current_chat = new_title

def add_message(role: str, content: str):
    st.session_state.chats[st.session_state.current_chat].append({
        "role": role,
        "content": content
    })

def get_current_turns() -> int:
    history = get_current_history()
    return sum(1 for msg in history if msg["role"] == "user")

def get_recent_memory(max_turns: int = 5) -> str:
    recent = get_current_history()[-(max_turns * 2):]
    lines = []
    for msg in recent:
        prefix = "Usuario" if msg["role"] == "user" else "Asistente"
        lines.append(f"{prefix}: {msg['content']}")
    return "\n".join(lines)

def create_new_chat():
    st.session_state.new_chat_counter += 1
    name = f"Nuevo chat {st.session_state.new_chat_counter}"
    st.session_state.chats[name] = []
    st.session_state.current_chat = name
    st.session_state.pending_welcome_for_chat = name
    reset_scatter_state()

def delete_current_chat():
    current = st.session_state.current_chat

    if len(st.session_state.chats) == 1:
        st.session_state.chats = {"Nuevo chat": []}
        st.session_state.current_chat = "Nuevo chat"
        st.session_state.new_chat_counter = 1
        st.session_state.pending_welcome_for_chat = "Nuevo chat"
        reset_scatter_state()
        return

    del st.session_state.chats[current]
    st.session_state.current_chat = list(st.session_state.chats.keys())[0]
    st.session_state.pending_welcome_for_chat = st.session_state.current_chat
    reset_scatter_state()

def delete_all_chats():
    st.session_state.chats = {"Nuevo chat": []}
    st.session_state.current_chat = "Nuevo chat"
    st.session_state.new_chat_counter = 1
    st.session_state.pending_welcome_for_chat = "Nuevo chat"
    reset_scatter_state()


def extract_products_from_question(question: str) -> list[str]:
    q = normalize_text(question)

    product_keywords = {
        "iphone": "iphone",
        "galaxy": "galaxy",
        "samsung": "samsung",
        "tablet": "tablet",
        "ipad": "tablet",
        "xiaomi": "xiaomi",
        "redmi": "redmi",
        "usb": "usb",
        "cargador": "cargador",
        "cable": "cable",
        "funda": "funda",
        "tuna": "funda",   # <- para absorber ese typo frecuente
        "watch": "watch",
        "smartwatch": "smartwatch",
        "audio": "audio",
        "audifonos": "audifonos",
        "audífonos": "audifonos",
        "bluetooth": "bluetooth",
    }

    found = []

    for key, value in product_keywords.items():
        if key in q:
            found.append(value)

    # quitar duplicados conservando orden
    unique_found = []
    for item in found:
        if item not in unique_found:
            unique_found.append(item)

    return unique_found

def wants_product_lookup(question: str) -> bool:
    q = normalize_text(question)

    trigger_words = [
        "dato", "datos",
        "detalle", "detalles",
        "informacion", "información",
        "muestrame", "muéstrame",
        "dame", "quiero ver",
        "producto", "productos",
    ]

    detected_products = extract_products_from_question(q)

    return bool(detected_products) or (
        any(t in q for t in trigger_words) and bool(detected_products)
    )


def normalize_text(text: str) -> str:
    text = text.lower().strip()
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
    }
    for a, b in replacements.items():
        text = text.replace(a, b)
    return text


def is_basic_stats_request(question: str) -> bool:
    q = normalize_text(question)
    patterns = [
        "estadisticas",
        "estadísticas",
        "estadisticos",
        "estadísticos",
        "estadistica",
        "estadístico",
        "resumen estadistico",
        "resumen estadístico",
        "resumen de precios",
        "resumen de stock",
        "metricas basicas",
        "métricas básicas",
        "estadisticas basicas",
        "estadísticas básicas",
        "diagnostico",
        "diagnóstico",
        "resumen general",
    ]
    return any(p in q for p in patterns)

def wants_average(question: str) -> bool:
    q = normalize_text(question)
    return any(p in q for p in ["promedio", "media", "average", "mean"])


def wants_price_stats(question: str) -> bool:
    q = normalize_text(question)
    return any(p in q for p in ["precio", "precios", "price", "prices"])

def wants_stock_stats(question: str) -> bool:
    q = normalize_text(question)
    return any(p in q for p in ["stock", "inventario"])


def wants_any_stats(question: str) -> bool:
    q = normalize_text(question)
    return (
        is_basic_stats_request(q)
        or "estadisticas" in q
        or "estadísticos" in q
        or "estadisticos" in q
        or "diagnostico" in q
        or "diagnóstico" in q
        or "resumen" in q
    )


def extract_top_n(question: str, default: int = 5) -> int:
    q = normalize_text(question)

    patterns = [
        r"\btop\s*(\d+)\b",
        r"\b(\d+)\s+productos?\b",
        r"\blos\s+(\d+)\b",
        r"\blas\s+(\d+)\b",
        r"\bdame\s+(\d+)\b",
    ]

    for pattern in patterns:
        m = re.search(pattern, q)
        if m:
            return int(m.group(1))

    return default

def wants_category_average(question: str) -> bool:
    q = normalize_text(question)
    return (
        ("categoria" in q or "categoría" in question.lower())
        and ("promedio" in q or "media" in q or "average" in q)
    )


def wants_top_query(question: str) -> bool:
    q = normalize_text(question)

    if "top" in q:
        return True

    patterns = [
        r"\b\d+\s+productos?\b",
        r"\blos\s+\d+\b",
        r"\blas\s+\d+\b",
        r"\bdame\s+\d+\b",
    ]

    return any(re.search(pattern, q) for pattern in patterns)

def wants_category_average(question: str) -> bool:
    q = normalize_text(question)
    return (
        ("categoria" in q or "categoría" in question.lower())
        and ("promedio" in q or "media" in q or "average" in q)
    )

def wants_scatter_request(question: str) -> bool:
    q = normalize_text(question)
    patterns = [
        "scatter",
        "dispersion",
        "dispersión",
        "grafica de dispersion",
        "gráfica de dispersión",
        "correlacion",
        "correlación",
        "relacion entre",
        "relación entre",
        "comparar variables",
        "comparar numericas",
        "comparar numéricas",
    ]
    return any(p in q for p in patterns)


def get_numeric_columns(df: pd.DataFrame) -> list[str]:
    if df is None or df.empty:
        return []
    return df.select_dtypes(include=["int64", "float64"]).columns.tolist()


def format_number(value) -> str:
    try:
        return f"{float(value):,.2f}"
    except Exception:
        return str(value)


def build_statistical_summary(question: str, df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "No encontré datos para calcular estadísticas."

    q = normalize_text(question)
    lines = []

    if "metric" in df.columns and "value" in df.columns:
        metric_map = dict(zip(df["metric"], df["value"]))
        title = "Resumen estadístico:"
        lines.append(title)

        ordered_metrics = [
            ("count_products", "Cantidad de productos"),
            ("avg_price", "Precio promedio"),
            ("min_price", "Precio mínimo"),
            ("max_price", "Precio máximo"),
            ("sum_stock", "Stock total"),
            ("avg_stock", "Stock promedio"),
            ("min_stock", "Stock mínimo"),
            ("max_stock", "Stock máximo"),
        ]

        for key, label in ordered_metrics:
            if key in metric_map:
                value = metric_map[key]
                if "count" in key or "stock" in key and key != "avg_stock":
                    try:
                        value = int(float(value))
                    except Exception:
                        pass
                lines.append(f"- {label}: {format_number(value) if isinstance(value, float) else value}")

        return "\n".join(lines)

    # fallback para tablas normales
    numeric_df = df.select_dtypes(include=["int64", "float64"])
    if numeric_df.empty:
        return "Encontré resultados, pero no hay columnas numéricas para resumir."

    lines.append("Resumen numérico:")
    for col in numeric_df.columns:
        series = pd.to_numeric(numeric_df[col], errors="coerce").dropna()
        if series.empty:
            continue
        lines.append(f"- {col}: promedio {series.mean():,.2f}, mínimo {series.min():,.2f}, máximo {series.max():,.2f}")

    return "\n".join(lines)


def build_statistical_summary(question: str, df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "No encontré datos para calcular estadísticas."

    lines = []

    if "metric" in df.columns and "value" in df.columns:
        metric_map = dict(zip(df["metric"], df["value"]))

        lines.append("Resumen estadístico:")

        ordered_metrics = [
            ("count_products", "Cantidad de productos"),
            ("avg_price", "Precio promedio"),
            ("min_price", "Precio mínimo"),
            ("max_price", "Precio máximo"),
            ("sum_stock", "Stock total"),
            ("avg_stock", "Stock promedio"),
            ("min_stock", "Stock mínimo"),
            ("max_stock", "Stock máximo"),
        ]

        for key, label in ordered_metrics:
            if key in metric_map:
                value = metric_map[key]

                if key in ["count_products", "sum_stock", "min_stock", "max_stock"]:
                    try:
                        value = int(float(value))
                    except Exception:
                        pass
                else:
                    try:
                        value = f"{float(value):,.2f}"
                    except Exception:
                        pass

                lines.append(f"- {label}: {value}")

        diagnostico = []

        avg_price = metric_map.get("avg_price")
        min_price = metric_map.get("min_price")
        max_price = metric_map.get("max_price")
        avg_stock = metric_map.get("avg_stock")
        min_stock = metric_map.get("min_stock")
        max_stock = metric_map.get("max_stock")

        try:
            if avg_price is not None and max_price is not None:
                if float(max_price) > float(avg_price) * 2:
                    diagnostico.append("hay una dispersión relevante en precios, con productos premium claramente por encima del promedio")
        except Exception:
            pass

        try:
            if avg_stock is not None and min_stock is not None:
                if float(min_stock) < float(avg_stock) * 0.35:
                    diagnostico.append("hay productos con inventario sensiblemente por debajo del promedio, lo que sugiere revisar reposición")
        except Exception:
            pass

        try:
            if max_stock is not None and avg_stock is not None:
                if float(max_stock) > float(avg_stock) * 1.8:
                    diagnostico.append("existen diferencias importantes de inventario entre productos, lo que podría indicar desbalance de demanda o abastecimiento")
        except Exception:
            pass

        if diagnostico:
            lines.append("")
            lines.append("Diagnóstico breve:")
            for d in diagnostico:
                lines.append(f"- {d}")
        else:
            lines.append("")
            lines.append("Diagnóstico breve:")
            lines.append("- la distribución general luce relativamente estable en las métricas principales")

        return "\n".join(lines)

    numeric_df = df.select_dtypes(include=["int64", "float64"])
    if numeric_df.empty:
        return "Encontré resultados, pero no hay columnas numéricas para resumir."

    lines.append("Resumen numérico:")
    diagnostico = []

    for col in numeric_df.columns:
        series = pd.to_numeric(numeric_df[col], errors="coerce").dropna()
        if series.empty:
            continue

        mean_v = series.mean()
        min_v = series.min()
        max_v = series.max()

        lines.append(
            f"- {col}: promedio {mean_v:,.2f}, mínimo {min_v:,.2f}, máximo {max_v:,.2f}"
        )

        if mean_v != 0 and max_v > mean_v * 2:
            diagnostico.append(f"la variable {col} muestra alta dispersión respecto a su promedio")

    lines.append("")
    lines.append("Diagnóstico breve:")
    if diagnostico:
        for d in diagnostico:
            lines.append(f"- {d}")
    else:
        lines.append("- no se observan desviaciones muy marcadas en las variables numéricas analizadas")

    return "\n".join(lines)


def build_product_list_summary(df: pd.DataFrame) -> str:
    resumen = []

    if {"product_name", "price", "stock"}.issubset(df.columns):
        for _, row in df.iterrows():
            resumen.append(
                f"{row['product_name']} (${row['price']:,.0f}, stock: {int(row['stock'])})"
            )

        if len(resumen) == 1:
            return f"Producto encontrado:\n- {resumen[0]}"
        return "Productos encontrados:\n- " + "\n- ".join(resumen)

    if {"category", "avg_price"}.issubset(df.columns):
        for _, row in df.iterrows():
            if "avg_stock" in df.columns:
                resumen.append(
                    f"{row['category']}: precio promedio ${row['avg_price']:,.2f}, stock promedio {row['avg_stock']:,.2f}"
                )
            else:
                resumen.append(
                    f"{row['category']}: precio promedio ${row['avg_price']:,.2f}"
                )
        return "Promedios por categoría:\n- " + "\n- ".join(resumen)

    if {"store_id", "revenue"}.issubset(df.columns):
        for _, row in df.iterrows():
            resumen.append(
                f"{row['store_id']} (${row['revenue']:,.0f})"
            )

        if len(resumen) == 1:
            return f"Tienda encontrada:\n- {resumen[0]}"
        return "Tiendas encontradas:\n- " + "\n- ".join(resumen)

    return "Encontré resultados en la tabla."

def reset_scatter_state():
    st.session_state.scatter_mode = False
    st.session_state.scatter_step = None
    st.session_state.scatter_df = None
    st.session_state.scatter_x = None
    st.session_state.scatter_numeric_cols = []


def start_scatter_flow(df: pd.DataFrame):
    st.session_state.scatter_mode = True
    st.session_state.scatter_step = "await_x"
    st.session_state.scatter_df = df.copy()
    st.session_state.scatter_x = None
    st.session_state.scatter_numeric_cols = get_numeric_columns(df)


def is_valid_numeric_choice(user_text: str, numeric_cols: list[str]) -> str | None:
    q = normalize_text(user_text)

    # match exacto normalizado
    for col in numeric_cols:
        if normalize_text(col) == q:
            return col

    # match parcial
    for col in numeric_cols:
        if q in normalize_text(col) or normalize_text(col) in q:
            return col

    return None


# -----------------------------
# UI
# -----------------------------
MEJOR_MERCADO_GREEN = "#0A7A4B"
MEJOR_MERCADO_GREEN_DARK = "#075C39"
MEJOR_MERCADO_LIGHT = "#BBF6D5"
MEJOR_MERCADO_CREAM = "#ECEAE6"
MEJOR_MERCADO_ORANGE = "#E98A15"
MEJOR_MERCADO_DARK = "#0E241C"
MEJOR_MERCADO_TEXT = "#264236"
MEJOR_MERCADO_BORDER = "#D1F1DE"

LOTTIE_URL = "https://assets3.lottiefiles.com/packages/lf20_zrqthn6o.json"
lottie_robot = load_lottie(LOTTIE_URL)


st.markdown(f"""
<style>
.main .block-container {{
    padding-top: 1.1rem;
    padding-bottom: 2.2rem;
    max-width: 1260px;
}}

.stApp {{
    background:
        radial-gradient(circle at top right, rgba(233,138,21,0.08), transparent 22%),
        linear-gradient(180deg, #FCFDFB 0%, #F4FAF6 100%);
}}

[data-testid="stSidebar"] {{
    background:
        linear-gradient(180deg, #E7F2EC 0%, #D8EBE1 100%);
    border-right: 1px solid #C3DDD0;
    box-shadow:
        8px 0 24px rgba(14, 36, 28, 0.08),
        inset -1px 0 0 rgba(255,255,255,0.28);
}}

[data-testid="stSidebar"] * {{
    color: {MEJOR_MERCADO_GREEN_DARK};
}}

.hero-box {{
    background: linear-gradient(135deg, {MEJOR_MERCADO_CREAM} 0%, {MEJOR_MERCADO_LIGHT} 100%);
    border: 1px solid {MEJOR_MERCADO_BORDER};
    border-radius: 26px;
    padding: 28px 32px;
    margin-bottom: 18px;
    box-shadow:
        0 14px 34px rgba(14, 36, 28, 0.12),
        0 4px 12px rgba(14, 36, 28, 0.06);
}}

.hero-title {{
    font-size: 2.15rem;
    font-weight: 900;
    color: {MEJOR_MERCADO_DARK};
    margin-bottom: 0.4rem;
    line-height: 1.1;
    letter-spacing: -0.02em;
}}

.hero-subtitle {{
    font-size: 1rem;
    color: {MEJOR_MERCADO_TEXT};
    line-height: 1.7;
}}

.hero-badge {{
    display: inline-block;
    background: linear-gradient(135deg, {MEJOR_MERCADO_GREEN} 0%, {MEJOR_MERCADO_GREEN_DARK} 100%);
    color: white;
    padding: 7px 14px;
    border-radius: 999px;
    font-size: 0.84rem;
    font-weight: 800;
    margin-bottom: 12px;
    box-shadow: 0 8px 18px rgba(10, 122, 75, 0.28);
}}

.kpi-card {{
    background: linear-gradient(180deg, #FFFFFF 0%, #F9FCFA 100%);
    border: 1px solid {MEJOR_MERCADO_BORDER};
    border-radius: 22px;
    padding: 18px 18px;
    min-height: 138px;
    box-shadow:
        0 14px 26px rgba(14, 36, 30, 0.10),
        0 4px 10px rgba(14, 36, 30, 0.05);
    transition: transform 0.18s ease, box-shadow 0.18s ease;
}}

.kpi-card:hover {{
    transform: translateY(-2px);
    box-shadow:
        0 18px 34px rgba(14, 36, 28, 0.14),
        0 6px 14px rgba(14, 36, 28, 0.08);
}}

.kpi-label {{
    font-size: 0.80rem;
    color: #587465;
    margin-bottom: 6px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.03em;
}}

.kpi-value {{
    font-size: 1.30rem;
    font-weight: 900;
    color: {MEJOR_MERCADO_DARK};
    margin-bottom: 7px;
    line-height: 1.15;
}}

.kpi-sub {{
    font-size: 0.90rem;
    color: {MEJOR_MERCADO_TEXT};
    line-height: 1.45;
}}

.section-box {{
    background: linear-gradient(180deg, #FFFFFF 0%, #FAFDFC 100%);
    border: 1px solid {MEJOR_MERCADO_BORDER};
    border-radius: 22px;
    padding: 16px 18px;
    box-shadow:
        0 12px 24px rgba(14, 36, 28, 0.08),
        0 4px 10px rgba(14, 36, 28, 0.04);
    margin-top: 12px;
}}

.small-chip {{
    display: inline-block;
    background: #F2FBF6;
    color: {MEJOR_MERCADO_GREEN_DARK};
    border: 1px solid #CFE7D8;
    padding: 6px 11px;
    border-radius: 999px;
    font-size: 0.79rem;
    font-weight: 800;
    margin-right: 7px;
    margin-bottom: 7px;
    box-shadow: 0 4px 10px rgba(10, 122, 75, 0.08);
}}

h3, h2 {{
    color: {MEJOR_MERCADO_DARK};
    font-weight: 850;
}}

[data-testid="stChatMessage"] {{
    background: rgba(255,255,255,0.72);
    border: 1px solid rgba(215,232,222,0.92);
    border-radius: 20px;
    padding: 0.45rem 0.45rem;
    box-shadow:
        0 10px 22px rgba(14, 36, 28, 0.08),
        0 3px 8px rgba(14, 36, 28, 0.04);
    margin-bottom: 10px;
}}

[data-testid="stChatMessageContent"] {{
    border-radius: 16px;
    color: {MEJOR_MERCADO_DARK};
}}

[data-testid="stChatInput"] {{
    position: sticky;
    bottom: 0;
    background: rgba(252,253,251,0.96);
    backdrop-filter: blur(8px);
    border-top: 1px solid {MEJOR_MERCADO_BORDER};
    padding-top: 10px;
}}

.stTextInput > div > div,
div[data-baseweb="input"] > div,
div[data-baseweb="select"] > div {{
    border-radius: 14px !important;
    border: 1px solid #CFE0D7 !important;
    box-shadow:
        0 8px 18px rgba(14, 36, 28, 0.05),
        inset 0 1px 0 rgba(255,255,255,0.9);
    background: white !important;
}}

.stTextInput > div > div:focus-within,
div[data-baseweb="input"] > div:focus-within,
div[data-baseweb="select"] > div:focus-within {{
    border: 1px solid {MEJOR_MERCADO_GREEN} !important;
    box-shadow:
        0 0 0 3px rgba(10,122,75,0.12),
        0 10px 22px rgba(10,122,75,0.10) !important;
}}

.stDataFrame, div[data-testid="stDataFrame"] {{
    border-radius: 18px;
    overflow: hidden;
    border: 1px solid {MEJOR_MERCADO_BORDER};
    box-shadow:
        0 12px 24px rgba(14, 36, 28, 0.08),
        0 4px 10px rgba(14, 36, 28, 0.04);
    background: white;
}}

div.stButton > button {{
    width: 100%;
    border-radius: 14px;
    border: 1px solid transparent;
    background: linear-gradient(135deg, {MEJOR_MERCADO_GREEN} 0%, {MEJOR_MERCADO_GREEN_DARK} 100%);
    color: white !important;
    font-weight: 800;
    letter-spacing: 0.01em;
    padding: 0.62rem 1rem;
    box-shadow:
        0 12px 22px rgba(10, 122, 75, 0.22),
        0 4px 10px rgba(10, 122, 75, 0.12);
    transition: all 0.18s ease;
}}

/* 👇 AGREGA ESTO */
div.stButton > button p {{
    color: #FFFFFF !important;
}}

div.stButton > button span {{
    color: #FFFFFF !important;
}}

div.stButton > button:hover {{
    transform: translateY(-1px);
    background: linear-gradient(135deg, #0C8753 0%, #064D30 100%);
    color: white !important;
    box-shadow:
        0 16px 28px rgba(10, 122, 75, 0.28),
        0 6px 14px rgba(10, 122, 75, 0.16);
}}

div.stButton > button:hover p {{
    color: #FFFFFF !important;
}}

div.stButton > button:hover span {{
    color: #FFFFFF !important;
}}

div.stButton > button:active {{
    transform: translateY(0);
}}

button[kind="primary"] {{
    background: linear-gradient(135deg, {MEJOR_MERCADO_ORANGE} 0%, #D9730D 100%) !important;
    box-shadow:
        0 14px 26px rgba(233, 138, 21, 0.24),
        0 4px 10px rgba(233, 138, 21, 0.14) !important;
}}

button[kind="primary"]:hover {{
    background: linear-gradient(135deg, #F29A2C 0%, #C96509 100%) !important;
}}

.stAlert {{
    border-radius: 16px !important;
    box-shadow: 0 10px 22px rgba(14, 36, 28, 0.08);
}}

hr {{
    border: none;
    border-top: 1px solid #E2EEE7;
    margin: 0.8rem 0 1rem 0;
}}
</style>
""", unsafe_allow_html=True)

hero_col1, hero_col2 = st.columns([1.7, 0.5])

with hero_col1:
    st.markdown(f"""
    <div class="hero-box">
        <div class="hero-badge">Asistente inteligente</div>
        <div class="hero-title">Tu asistente retail, más humano y más claro</div>
        <div class="hero-subtitle">
            Haz preguntas sobre productos, inventario, pedidos, políticas o soporte.
            Este demo combina <b>SQLite + documentos + LLM local</b> para responder de forma práctica y amigable.
        </div>
    </div>
    """, unsafe_allow_html=True)
        
    cheapest_df, expensive_df = get_price_extremes()

    cheapest_name = cheapest_df.iloc[0]["product_name"] if not cheapest_df.empty else "N/D"
    cheapest_price = cheapest_df.iloc[0]["price"] if not cheapest_df.empty else 0
    cheapest_stock = cheapest_df.iloc[0]["stock"] if not cheapest_df.empty else 0

    expensive_name = expensive_df.iloc[0]["product_name"] if not expensive_df.empty else "N/D"
    expensive_price = expensive_df.iloc[0]["price"] if not expensive_df.empty else 0
    expensive_stock = expensive_df.iloc[0]["stock"] if not expensive_df.empty else 0

    k1, k2, k3, k4 = st.columns(4)

with k1:
            st.markdown(f"""
            <div class="kpi-card">
                <div class="kpi-label">Motor</div>
                <div class="kpi-value">LLM local</div>
                <div class="kpi-sub">SQLite + documentos + Ollama</div>
            </div>
            """, unsafe_allow_html=True)

with k2:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">Canal</div>
        <div class="kpi-value">Retail commerce</div>
        <div class="kpi-sub">POC conversacional para ventas y soporte</div>
    </div>
    """, unsafe_allow_html=True)

with k3:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">Producto más barato</div>
        <div class="kpi-value">${cheapest_price:,.0f}</div>
        <div class="kpi-sub">{cheapest_name}<br>Stock: {cheapest_stock}</div>
    </div>
    """, unsafe_allow_html=True)

with k4:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">Producto más caro</div>
        <div class="kpi-value">${expensive_price:,.0f}</div>
        <div class="kpi-sub">{expensive_name}<br>Stock: {expensive_stock}</div>
    </div>
    """, unsafe_allow_html=True)

with hero_col2:
    st.markdown(
        """
        <div style="
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100%;
        ">
        """,
        unsafe_allow_html=True
    )

    if lottie_robot:

        st.markdown("""
<div style="
    background:#FFFFFF;
    border-radius:24px;
    padding:18px;
    display:flex;
    justify-content:center;
    align-items:center;
">
""", unsafe_allow_html=True)

        st_lottie(
            lottie_robot,
            height=350,
            key="hero_robot",
            loop=True,
            quality="high",
        )

    st.markdown("</div>", unsafe_allow_html=True)

with st.sidebar:
    st.image("https://images.openai.com/static-rsc-3/BCxseKU2L3XoIXA8hoPYo5BAqjqFs6IQQqJ7A20b_-Pa_6hqkMFBTcrjIs4gYfvyg-YR1nQh9YNOZWW2NL9goPXnwOG6tUGP9wZr4go0jfI?purpose=fullsize&v=1", use_container_width=True)

    st.markdown("""
    <div style="
        text-align: center;
        font-weight: 800;
        font-size: 0.95rem;
        color: #0B7A4B;
        margin-top: -6px;
        margin-bottom: 12px;
    ">
        LLM Intelligence Engine
    </div>
    """, unsafe_allow_html=True)

    model_name = st.text_input("Modelo Ollama", value="tinyllama")

    st.markdown("### Chats")

    if st.button("➕ Nuevo chat", use_container_width=True):
        create_new_chat()
        st.rerun()

    if st.button("🗑️ Borrar chat actual", use_container_width=True):
        delete_current_chat()
        st.rerun()

    if st.button("🚮 Borrar todos los chats", use_container_width=True):
        delete_all_chats()
        st.rerun()

    st.markdown("---")

    for chat_name in list(st.session_state.chats.keys()):
        if st.button(
            chat_name,
            key=f"chat_btn_{chat_name}",
            use_container_width=True
        ):
            st.session_state.current_chat = chat_name
            st.rerun()

st.markdown("""
<div class="section-box">
    <div style="font-weight:800; color:#12372A; margin-bottom:8px;">Preguntas sugeridas</div>
    <span class="small-chip">¿Cuál es el precio del iPhone?</span>
    <span class="small-chip">Muéstrame productos con bajo inventario</span>
    <span class="small-chip">¿Cuál es el producto más caro?</span>
    <span class="small-chip">¿Cuál es el producto más barato?</span>
    <span class="small-chip">¿Cuál es la política de devoluciones?</span>
    <span class="small-chip">Haz un scatter</span>        
</div>
""", unsafe_allow_html=True)

current_turns = get_current_turns()

if current_turns >= MAX_TURNS:
    st.warning("Has sobrepasado el número de preguntas de este chat.")
    if st.button("Iniciar otro chat", type="primary", ):
        create_new_chat()
        st.rerun()
else:
    question = st.chat_input("Haz una pregunta sobre la app móvil retail")


for msg in get_current_history():
    with st.chat_message("user" if msg["role"] == "user" else "assistant"):
        st.write(msg["content"])

current_chat_name = st.session_state.current_chat
current_history = get_current_history()

if (
    len(current_history) == 0
    and st.session_state.welcome_shown.get(current_chat_name) != True
):
    with st.chat_message("assistant"):
        welcome_placeholder = st.empty()
        welcome_text = get_welcome_message()
        write_typing_effect(welcome_text, welcome_placeholder, speed=0.012)

    add_message("assistant", welcome_text)
    st.session_state.welcome_shown[current_chat_name] = True

df = None
scatter_plot_ready = False
scatter_plot_df = None
scatter_x_col = None
scatter_y_col = None

if get_current_turns() < MAX_TURNS and question:

    # 1️⃣ guardar pregunta del usuario
    ensure_first_user_message_as_title(question)
    add_message("user", question)

    with st.chat_message("user"):
        st.write(question)

    # -------------------------------------------------
    # FLUJO CONVERSACIONAL DE SCATTER
    # -------------------------------------------------
    if st.session_state.scatter_mode:
        numeric_cols = st.session_state.scatter_numeric_cols

        if st.session_state.scatter_step == "await_x":
            selected_x = is_valid_numeric_choice(question, numeric_cols)

            if selected_x is None:
                response_text = (
                    "No reconocí esa variable numérica para el eje X.\n\n"
                    f"Variables disponibles: {', '.join(numeric_cols)}"
                )
                route = "scatter_flow"

            else:
                st.session_state.scatter_x = selected_x
                st.session_state.scatter_step = "await_y"

                y_candidates = [col for col in numeric_cols if col != selected_x]

                response_text = (
                    f"Perfecto. Elegiste **{selected_x}** para el eje X.\n\n"
                    "Ahora elige la variable para el eje Y.\n\n"
                    f"Opciones disponibles: {', '.join(y_candidates)}"
                )
                route = "scatter_flow"

        elif st.session_state.scatter_step == "await_y":
            x_selected = st.session_state.scatter_x
            y_candidates = [col for col in numeric_cols if col != x_selected]
            selected_y = is_valid_numeric_choice(question, y_candidates)

            if selected_y is None:
                response_text = (
                    "No reconocí esa variable numérica para el eje Y.\n\n"
                    f"Opciones disponibles: {', '.join(y_candidates)}"
                )
                route = "scatter_flow"

            else:
                response_text = (
                    f"Listo. Generé el scatter con **{x_selected}** en X "
                    f"y **{selected_y}** en Y."
                )
                route = "scatter_flow"
                scatter_plot_ready = True
                scatter_plot_df = st.session_state.scatter_df.copy()
                scatter_x_col = x_selected
                scatter_y_col = selected_y
                reset_scatter_state()

        else:
            reset_scatter_state()
            response_text = "Reinicié el flujo del scatter. Puedes pedirlo otra vez."
            route = "scatter_flow"

    # -------------------------------------------------
    # FLUJO NORMAL
    # -------------------------------------------------
    else:
        farewell_answer = get_farewell_response(question)
        general_answer = get_general_help_response(question)

        if farewell_answer:
            response_text = farewell_answer
            route = "farewell"

        elif general_answer:
            response_text = general_answer
            route = "fallback"

        else:
            route = classify_question(question)
            memory_context = get_recent_memory()

            if route == "sql":
                intro, df = run_sql_router(question)

                # Si es petición de scatter, arrancar flujo conversacional
                if wants_scatter_request(question) and df is not None and not df.empty:
                    numeric_cols = get_numeric_columns(df)

                    if len(numeric_cols) >= 2:
                        start_scatter_flow(df)
                        response_text = (
                            "Claro. Vamos a construir el scatter paso a paso.\n\n"
                            "Primero elige la variable para el eje X.\n\n"
                            f"Variables numéricas disponibles: {', '.join(numeric_cols)}"
                        )
                        route = "scatter_flow"
                    else:
                        response_text = "No encontré al menos dos variables numéricas para construir el scatter."

                else:
                    response_text = intro

                    if df is not None and not df.empty:
                        if {"metric", "value"}.issubset(df.columns):
                            response_text += "\n\n" + build_statistical_summary(question, df)
                        else:
                            response_text += "\n\n" + build_product_list_summary(df)
                    else:
                        response_text = "No encontré resultados en la base para esa consulta."

            else:
                try:
                    response_text = answer_with_docs(question)
                except Exception:
                    response_text = "No pude consultar la documentación local del demo."
    # 3️⃣ mostrar respuesta
    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        write_typing_effect(response_text, response_placeholder, speed=0.01)

        # gráfico final del flujo conversacional scatter
        if scatter_plot_ready and scatter_plot_df is not None:
            st.markdown("### 📊 Scatter generado")
            try:
                st.scatter_chart(scatter_plot_df, x=scatter_x_col, y=scatter_y_col)
            except TypeError:
                st.scatter_chart(scatter_plot_df[[scatter_x_col, scatter_y_col]])

        # visualización normal para SQL
        elif route == "sql" and df is not None and not df.empty:
            st.markdown("### 📊 Visualización sugerida")

            viz_key_base = f"{st.session_state.current_chat}_{get_current_turns()}_{abs(hash(question))}"

            if {"metric", "value"}.issubset(df.columns):
                st.bar_chart(df.set_index("metric")["value"])
            else:
                numeric_cols = df.select_dtypes(include=['int64', 'float64']).columns.tolist()

                if len(numeric_cols) >= 1 and len(df.columns) >= 2:
                    x_col = df.columns[0]
                    y_col = numeric_cols[0]

                    chart_type = st.selectbox(
                        "Tipo de gráfica",
                        ["Barra", "Línea"],
                        key=f"chart_{viz_key_base}"
                    )

                    if chart_type == "Barra":
                        st.bar_chart(df.set_index(x_col)[y_col])
                    else:
                        st.line_chart(df.set_index(x_col)[y_col])

                else:
                    st.info("No hay columnas adecuadas para graficar.")

    # 4️⃣ guardar respuesta
    add_message("assistant", response_text)

