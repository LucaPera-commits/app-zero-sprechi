import datetime
import json
import pandas as pd
import requests
import streamlit as st
import psycopg2

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(
    page_title="ZeroSpreco AI - Famiglia",
    page_icon="🥗",
    layout="centered",
    initial_sidebar_state="expanded",
)

st.title("🥗 ZeroSpreco Familiare")
st.caption("Versione 10.0 - Multi-Utente Condiviso in Cloud")

# --- SIDEBAR: CHIAVI E CONNESSIONI ---
st.sidebar.header("⚙️ Impostazioni AI & Cloud")

DEFAULT_KEY = "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"
ai_key = st.sidebar.text_input(
    "API Key (Groq o Gemini):",
    value=DEFAULT_KEY,
    type="password",
    placeholder="gsk_... oppure AIzaSy...",
)

# Connessione PostgreSQL (Supabase/Neon) gestita tramite st.secrets o input sidebar
db_url = st.secrets.get("DATABASE_URL", ""postgresql://postgres.incwdmenairgbqcvbhk:METTI_QUI_LA_TUA_PASSWORD@aws-0-eu-central-1.pooler.supabase.com:6543/postgres"")

# --- 2. GESTIONE DATABASE POSTGRESQL (CLOUD CONDIVISO) ---
def get_db_connection():
    if not db_url:
        st.error("⚠️ Configura DATABASE_URL nei secrets di Streamlit per sincronizzare i dispositivi!")
        st.stop()
    return psycopg2.connect(db_url)

def salva_in_db(nome, marca, scadenza, giorni_rimasti, quantita, kcal_100g, categoria="Altro", giorni_da_aperto=3):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO dispensa (nome, marca, scadenza, giorni_rimasti, quantita, kcal_100g, categoria, aperto, giorni_da_aperto)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s)
    """,
        (nome, marca, scadenza, giorni_rimasti, quantita, kcal_100g, categoria, giorni_da_aperto),
    )
    conn.commit()
    conn.close()

def carica_da_db():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM dispensa ORDER BY id DESC", conn)
    conn.close()

    if not df.empty:
        df["Scadenza_dt"] = pd.to_datetime(df["scadenza"], format="%d/%m/%Y", errors="coerce")
        oggi = pd.Timestamp.now().normalize()
        df["Giorni Rimasti"] = (df["Scadenza_dt"] - oggi).dt.days.fillna(0).astype(int)
        df = df.drop(columns=["Scadenza_dt"])
        df = df.sort_values(by="Giorni Rimasti")
    return df

def segna_come_aperto_db(item_id, giorni_max_aperto=3):
    conn = get_db_connection()
    c = conn.cursor()
    nuova_scadenza = (datetime.date.today() + datetime.timedelta(days=giorni_max_aperto)).strftime("%d/%m/%Y")
    c.execute("UPDATE dispensa SET aperto = 1, scadenza = %s WHERE id = %s", (nuova_scadenza, item_id))
    conn.commit()
    conn.close()

def scala_quantita_db(item_id, delta=1):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE dispensa SET quantita = quantita - %s WHERE id = %s", (delta, item_id))
    c.execute("DELETE FROM dispensa WHERE quantita <= 0")
    conn.commit()
    conn.close()

def elimina_item_db(item_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM dispensa WHERE id = %s", (item_id,))
    conn.commit()
    conn.close()

# --- PULSANTE DI AGGIORNAMENTO MANUALE ---
if st.button("🔄 Sincronizza / Ricarica Dati"):
    st.rerun()

# [Tutto il resto della logica dell'interfaccia, Open Food Facts e Chef AI rimane identico alla v9.1]
