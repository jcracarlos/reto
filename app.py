import streamlit as st
import pandas as pd
from google.cloud import firestore
from google.oauth2 import service_account
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

# ---------------------------------------------------------
# Configuracion de conexiones (Firestore y PostgreSQL)
# ---------------------------------------------------------
# Conexion a Firestore
key_dict = dict(st.secrets["firebase"])
creds = service_account.Credentials.from_service_account_info(key_dict)
db = firestore.Client(credentials=creds, project="streamlit-app-70c78")

# Conexion a PostgreSQL (Usa st.connection con SQLAlchemy y secrets.toml)
conn_pg = st.connection("postgres", type="sql")


def mostrar_error_postgres(error, operacion):
    error_original = getattr(error, "orig", error)
    sqlstate = getattr(error_original, "sqlstate", None)
    mensaje = str(error_original).lower()

    if sqlstate == "42P01":
        detalle = "No existe la tabla `people` en la base de datos."
    elif sqlstate in {"28P01", "28000"}:
        detalle = "PostgreSQL rechazó la autenticación; revisa las credenciales."
    elif any(
        texto in mensaje
        for texto in (
            "could not translate host name",
            "name or service not known",
            "getaddrinfo failed",
            "temporary failure in name resolution",
        )
    ):
        detalle = (
            "No se pudo resolver el host de PostgreSQL. Revisa `host` en "
            "`.streamlit/secrets.toml` y que el nombre sea accesible por DNS."
        )
    elif "timeout" in mensaje or "timed out" in mensaje:
        detalle = "Se agotó el tiempo de espera al conectar con PostgreSQL."
    elif "connection refused" in mensaje:
        detalle = "PostgreSQL rechazó la conexión; revisa host, puerto y disponibilidad."
    else:
        detalle = f"Error de base de datos ({type(error).__name__})."

    st.error(f"No se pudo {operacion}. {detalle}")


# ---------------------------------------------------------
# Funciones de carga de datos
# ---------------------------------------------------------
@st.cache_data
def cargar_datos_firestore():
    """Obtiene todos los documentos de la colección 'movies' en un DataFrame."""
    movies_ref = list(db.collection("movies").stream())
    if not movies_ref:
        return pd.DataFrame()
    movies_dict = [doc.to_dict() for doc in movies_ref]
    return pd.DataFrame(movies_dict)

df_movies = cargar_datos_firestore()

# ---------------------------------------------------------
# Interfaz Principal (Dashboard)
# ---------------------------------------------------------
st.title("Netflix app")
st.write("Listo! (using st.cache)")
if st.session_state.pop("film_created", False):
    st.sidebar.success("Filme registrado correctamente.")

# ---------------------------------------------------------
# Barra lateral (Sidebar) - Controles y Formularios
# ---------------------------------------------------------

# Mostrar todos los filmes
mostrar_todos = st.sidebar.checkbox("Mostrar todos los filmes")
if mostrar_todos:
    st.subheader("Todos los filmes")
    st.dataframe(df_movies)

st.sidebar.markdown("---")

# Buscar filmes por titulo
st.sidebar.subheader("Buscar filmes")
titulo_buscar = st.sidebar.text_input("Título del filme:")
if st.sidebar.button("Buscar filmes"):
    if not df_movies.empty and titulo_buscar:
        # Filtrado ignorando mayúsculas/minúsculas
        filtro = df_movies[df_movies['name'].str.contains(titulo_buscar, case=False, na=False)]
        st.subheader(f"Resultados de la búsqueda: {titulo_buscar}")
        st.write(f"Total filmes mostrados: {len(filtro)}")
        st.dataframe(filtro)

st.sidebar.markdown("---")

# Filtrar por director
st.sidebar.subheader("Seleccionar Director")
if not df_movies.empty and 'director' in df_movies.columns:
    directores = df_movies['director'].dropna().unique().tolist()
    director_seleccionado = st.sidebar.selectbox("Director", directores, label_visibility="collapsed")

    if st.sidebar.button("Filtrar director"):
        filtro_dir = df_movies[df_movies['director'] == director_seleccionado]
        st.subheader(f"Filmes del director: {director_seleccionado}")
        st.write(f"Total filmes: {len(filtro_dir)}")
        st.dataframe(filtro_dir)

st.sidebar.markdown("---")

# Insertar nuevo filme en Firestore
st.sidebar.subheader("Nuevo filme")
nuevo_nombre = st.sidebar.text_input("Name:")
nueva_compania = st.sidebar.text_input("Company:")
nuevo_director = st.sidebar.text_input("Director:")
nuevo_genero = st.sidebar.text_input("Genre:")

if st.sidebar.button("Crear nuevo filme"):
    if nuevo_nombre and nueva_compania and nuevo_director and nuevo_genero:
        nuevo_doc = {
            "name": nuevo_nombre,
            "company": nueva_compania,
            "director": nuevo_director,
            "genre": nuevo_genero
        }
        db.collection("movies").add(nuevo_doc)
        st.cache_data.clear()
        st.session_state["film_created"] = True
        st.rerun()
    else:
        st.sidebar.error("Por favor completa todos los campos.")

st.sidebar.markdown("---")

# Libro de visitas (Insertar en PostgreSQL)
st.sidebar.subheader("Libro de visitas")
email_visita = st.sidebar.text_input("email:")
comentario_visita = st.sidebar.text_area("Comentario:")

if st.sidebar.button("Registrar Visita"):
    if email_visita and comentario_visita:
        try:
            with conn_pg.session as s:
                s.execute(
                    text("INSERT INTO people (email, comment) VALUES (:email, :comment);"),
                    {"email": email_visita, "comment": comentario_visita}
                )
                s.commit()
            st.sidebar.success("Visita registrada exitosamente.")
        except SQLAlchemyError as e:
            mostrar_error_postgres(e, "registrar la visita")
    else:
        st.sidebar.error("Ingresa email y comentario.")

st.sidebar.markdown("---")

# Ver visitas - Consultar en PostgreSQL
if st.sidebar.button("Ver visitas"):
    st.subheader("Libro de visitas")
    try:
        df_visitas = conn_pg.query("SELECT * FROM people;", ttl=0)
        for index, row in df_visitas.iterrows():
            st.write(f"{index + 1}.- {row['comment']} | {row['email']}")
    except SQLAlchemyError as e:
        mostrar_error_postgres(e, "consultar las visitas")