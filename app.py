import datetime
import pandas as pd
import requests
import streamlit as st

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(
    page_title="ZeroSpreco AI - Famiglia",
    page_icon="🥗",
    layout="centered",
    initial_sidebar_state="expanded"
)

st.title("🥗 ZeroSpreco Familiare")
st.caption("Versione 10.1 - Multi-Utente Condiviso in Cloud")

# --- SIDEBAR: CHIAVI E CONNESSIONI ---
st.sidebar.header("⚙️ Impostazioni AI & Cloud")

# 💡 CHIAVE GROQ:
DEFAULT_KEY = "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"

ai_key = st.sidebar.text_input(
    "API Key (Groq o Gemini):",
    value=DEFAULT_KEY,
    type="password"
)

# 💡 CONFIGURAZIONE API SUPABASE (HTTPS - Esente da errori di porta/IPv6)
SUPABASE_URL = "https://incwdmenairgbqcvbhk.supabase.co"
# Inseriamo la Publishable/Anon Key trovata nelle impostazioni API di Supabase:
SUPABASE_KEY = "sb_publishable_key" 

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}


# --- 2. GESTIONE DATABASE SUPABASE VIA REST API ---
def salva_in_db(nome, marca, scadenza, giorni_rimasti, quantita, kcal_100g, categoria="Altro", giorni_da_aperto=3):
    url = f"{SUPABASE_URL}/rest/v1/dispensa"
    payload = {
        "nome": nome,
        "marca": marca,
        "scadenza": scadenza,
        "giorni_rimasti": giorni_rimasti,
        "quantita": quantita,
        "kcal_100g": kcal_100g,
        "categoria": categoria,
        "aperto": 0,
        "giorni_da_aperto": giorni_da_aperto
    }
    try:
        res = requests.post(url, json=payload, headers=HEADERS, timeout=5)
        if res.status_code not in [200, 201]:
            st.error(f"Errore salvataggio Supabase: {res.text}")
    except Exception as e:
        st.error(f"Errore di rete: {e}")


def carica_da_db():
    url = f"{SUPABASE_URL}/rest/v1/dispensa?select=*&order=id.desc"
    try:
        res = requests.get(url, headers=HEADERS, timeout=5)
        if res.status_code == 200:
            data = res.json()
            df = pd.DataFrame(data)
            if not df.empty:
                df['Scadenza_dt'] = pd.to_datetime(df['scadenza'], format='%d/%m/%Y', errors='coerce')
                oggi = pd.Timestamp.now().normalize()
                df['Giorni Rimasti'] = (df['Scadenza_dt'] - oggi).dt.days.fillna(0).astype(int)
                df = df.drop(columns=['Scadenza_dt'])
                df = df.sort_values(by='Giorni Rimasti')
            return df
        else:
            st.error(f"🔴 Errore caricamento Supabase API ({res.status_code}): {res.text}")
            return pd.DataFrame()
    except Exception as e:
        st.error(f"🔴 Errore di connessione API Supabase: {e}")
        return pd.DataFrame()


def segna_come_aperto_db(item_id, giorni_max_aperto=3):
    url = f"{SUPABASE_URL}/rest/v1/dispensa?id=eq.{item_id}"
    nuova_scadenza = (datetime.date.today() + datetime.timedelta(days=giorni_max_aperto)).strftime("%d/%m/%Y")
    payload = {"aperto": 1, "scadenza": nuova_scadenza}
    try:
        requests.patch(url, json=payload, headers=HEADERS, timeout=5)
    except Exception as e:
        st.error(f"Errore aggiornamento: {e}")


def scala_quantita_db(item_id, delta=1):
    url_get = f"{SUPABASE_URL}/rest/v1/dispensa?id=eq.{item_id}"
    try:
        res = requests.get(url_get, headers=HEADERS)
        if res.status_code == 200 and res.json():
            qta_attuale = res.json()[0]['quantita']
            nuova_qta = qta_attuale - delta
            if nuova_qta <= 0:
                elimina_item_db(item_id)
            else:
                requests.patch(url_get, json={"quantita": nuova_qta}, headers=HEADERS)
    except Exception as e:
        st.error(f"Errore modifica quantità: {e}")


def elimina_item_db(item_id):
    url = f"{SUPABASE_URL}/rest/v1/dispensa?id=eq.{item_id}"
    try:
        requests.delete(url, headers=HEADERS, timeout=5)
    except Exception as e:
        st.error(f"Errore eliminazione: {e}")


def svuota_db():
    url = f"{SUPABASE_URL}/rest/v1/dispensa?id=gt.0"
    try:
        requests.delete(url, headers=HEADERS, timeout=5)
    except Exception as e:
        st.error(f"Errore svuotamento: {e}")


# --- 3. MOTORE AI CHEF ---
def genera_ricetta_ai(prompt, key):
    key_clean = key.strip()
    if key_clean.startswith("gsk_"):
        from groq import Groq
        client = Groq(api_key=key_clean)
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "Sei uno Chef Nutrizionista esperto Anti-Spreco."},
                {"role": "user", "content": prompt}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.7,
        )
        return chat_completion.choices[0].message.content
    elif key_clean.startswith("AIza"):
        import google.generativeai as genai
        genai.configure(api_key=key_clean)
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return response.text
    else:
        raise ValueError("Chiave API non valida.")


# --- 4. API OPEN FOOD FACTS ---
def cerca_alimento_api(query):
    if not query or len(query.strip()) < 2:
        return []
    
    url = "https://it.openfoodfacts.org/cgi/search.pl"
    params = {
        "action": "process",
        "search_terms": query.strip(),
        "search_simple": 1,
        "sort_by": "unique_scans_n",
        "page_size": 15,
        "json": "true"
    }
    headers = {"User-Agent": "ZeroSprecoApp - StreamlitClient/10.1 (contact@zerospreco.app)"}
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            prodotti = []
            for p in data.get("products", []):
                nutr = p.get("nutriments", {})
                def safe_float(key):
                    try:
                        val = nutr.get(key, 0)
                        return float(val) if val is not None else 0.0
                    except (ValueError, TypeError):
                        return 0.0

                prodotti.append({
                    "nome": p.get("product_name_it") or p.get("product_name") or "Senza Nome",
                    "marca": p.get("brands") or "Generico",
                    "foto": p.get("image_front_small_url", ""),
                    "kcal_100g": safe_float("energy-kcal_100g")
                })
            return prodotti
    except Exception as e:
        st.error(f"Errore connessione API: {e}")
        return []
    return []

CATEGORIE_LISTA = [
    "🥛 Latticini & Formaggi",
    "🍎 Frutta & Verdura Fresca",
    "🥩 Carne & Pesce",
    "🍝 Pasta, Riso & Cereali",
    "🥫 Scatolame & Conserve",
    "🧊 Surgelati",
    "🧃 Bevande",
    "🥖 Pane & Prodotti da Forno",
    "🍫 Snack & Dolci",
    "📦 Altro / Dispensa Generica"
]


# --- 5. SEZIONE INSERIMENTO PRODOTTO ---
@st.fragment
def sezione_ricerca():
    st.header("📥 1. Inserisci Prodotto")
    
    modalita = st.radio("Modalità inserimento:", ["🔎 Cerca Confezionati (Database)", "🥬 Cibo Fresco Manuale (Senza Scadenza)"], horizontal=True)
    
    if modalita == "🔎 Cerca Confezionati (Database)":
        with st.form(key="search_form"):
            query = st.text_input("Cerca alimento (es. 'Latte Coop', 'Yogurt', 'Panna'):")
            submit_search = st.form_submit_button("🔎 Cerca", type="primary")
        
        if submit_search and query:
            with st.spinner("Ricerca nel database..."):
                st.session_state["risultati_ricerca"] = cerca_alimento_api(query)
                
        risultati = st.session_state.get("risultati_ricerca", [])
        if risultati:
            opzioni = {f"{p['nome']} ({p['marca']}) - {p['kcal_100g']} kcal": p for p in risultati}
            scelta = st.selectbox("Seleziona il cibo esatto:", list(opzioni.keys()))
            prodotto_scelto = opzioni[scelta]
            
            st.divider()
            col1, col2 = st.columns([1, 2])
            with col1:
                if prodotto_scelto["foto"]:
                    st.image(prodotto_scelto["foto"], width=90)
            with col2:
                st.markdown(f"**{prodotto_scelto['nome']}**")
                st.caption(f"Marca: {prodotto_scelto['marca']}")
            
            col_cat, col_open = st.columns(2)
            with col_cat:
                cat_scelta = st.selectbox("Categoria:", CATEGORIE_LISTA, index=0)
            with col_open:
                giorni_dopo_apertura = st.number_input("Giorni max d'uso da APERTO:", min_value=1, max_value=30, value=3)
            
            scadenza_input = st.date_input("Data Scadenza Confezione Chiusa:", value=datetime.date.today() + datetime.timedelta(days=7))
            quantita = st.number_input("Quantità:", min_value=1, value=1, key="q_db")
            
            if st.button("💾 Salva in Dispensa"):
                giorni_mancanti = (scadenza_input - datetime.date.today()).days
                salva_in_db(
                    nome=prodotto_scelto["nome"],
                    marca=prodotto_scelto["marca"],
                    scadenza=scadenza_input.strftime("%d/%m/%Y"),
                    giorni_rimasti=giorni_mancanti,
                    quantita=quantita,
                    kcal_100g=prodotto_scelto["kcal_100g"],
                    categoria=cat_scelta,
                    giorni_da_aperto=giorni_dopo_apertura
                )
                st.success(f"✅ Salvato: {prodotto_scelto['nome']}")
                st.session_state["risultati_ricerca"] = []
                st.rerun()

    elif modalita == "🥬 Cibo Fresco Manuale (Senza Scadenza)":
        st.write("Inserisci cibi freschi comprati dal fruttivendolo/macellaio:")
        
        col_n, col_m = st.columns(2)
        with col_n:
            nome_fresco = st.text_input("Nome Cibo Fresco:", placeholder="es. Insalata, Mele, Fettine di Pollo")
        with col_m:
            cat_fresco = st.selectbox("Categoria:", CATEGORIE_LISTA, index=1)
            
        col_g, col_q = st.columns(2)
        with col_g:
            giorni_stima = st.number_input("Giorni stimati di durata:", min_value=1, max_value=60, value=4)
        with col_q:
            qta_fresco = st.number_input("Quantità / Porzioni:", min_value=1, value=1, key="q_fr")
            
        if st.button("💾 Salva Cibo Fresco"):
            if nome_fresco.strip():
                data_stimata = datetime.date.today() + datetime.timedelta(days=giorni_stima)
                salva_in_db(
                    nome=nome_fresco.strip(),
                    marca="Fresco/Locale",
                    scadenza=data_stimata.strftime("%d/%m/%Y"),
                    giorni_rimasti=giorni_stima,
                    quantita=qta_fresco,
                    kcal_100g=0.0,
                    categoria=cat_fresco,
                    giorni_da_aperto=giorni_stima
                )
                st.success(f"✅ Salvato cibo fresco: {nome_fresco}")
                st.rerun()


# --- 6. SEZIONE DISPENSA SUDDIVISA PER TIPOLOGIA ---
@st.fragment
def sezione_dispensa():
    st.header("🧺 2. La tua Dispensa Divisa per Categoria")
    
    if st.button("🔄 Sincronizza / Ricarica Dati", type="primary"):
        st.rerun()
        
    df = carica_da_db()
    if not df.empty:
        urgenti = df[df['Giorni Rimasti'] <= 2]
        if not urgenti.empty:
            st.error(f"🚨 **ATTENZIONE:** Hai {len(urgenti)} alimento/i da consumare subito!")
            
        categorie_presenti = list(df['categoria'].unique())
        tabs = st.tabs(["📌 Tutti i Cibi"] + categorie_presenti)
        
        with tabs[0]:
            st.write("#### Elenco Completo Ordinato per Urgenza:")
            mostra_tabella_cibi(df, prefix="all")
            
        for idx, cat_name in enumerate(categorie_presenti, start=1):
            with tabs[idx]:
                df_cat = df[df['categoria'] == cat_name]
                mostra_tabella_cibi(df_cat, prefix=f"cat_{idx}")
                
        st.divider()
        if st.button("🗑️ Svuota Tutta la Dispensa"):
            svuota_db()
            st.rerun()
    else:
        st.info("La tua dispensa è attualmente vuota o in attesa di caricamento.")


def mostra_tabella_cibi(df_subset, prefix=""):
    for _, row in df_subset.iterrows():
        col_info, col_mancanti, col_aperto, col_qta, col_btn1, col_btn2 = st.columns([3, 2, 1.5, 1, 1, 1])
        
        item_id = row['id']
        
        with col_info:
            aperto_tag = " 🔓 [APERTO]" if row.get('aperto') == 1 else ""
            st.markdown(f"**{row['nome']}** *({row['marca']})*{aperto_tag}")
            st.caption(f"📁 {row.get('categoria', 'Altro')}")
            
        with col_mancanti:
            if row['Giorni Rimasti'] < 0:
                st.caption(f"🔴 Scaduto il {row['scadenza']}")
            elif row['Giorni Rimasti'] <= 2:
                st.caption(f"🔴 {row['Giorni Rimasti']} gg ({row['scadenza']})")
            else:
                st.caption(f"🟢 {row['Giorni Rimasti']} gg ({row['scadenza']})")
                
        with col_aperto:
            if row.get('aperto') == 0:
                if st.button("🔓 Apri", key=f"{prefix}_open_{item_id}"):
                    segna_come_aperto_db(item_id, giorni_max_aperto=row.get('giorni_da_aperto', 3))
                    st.rerun()
            else:
                st.caption("⚠️ Consumare subito")
                
        with col_qta:
            st.write(f"x{row['quantita']}")
            
        with col_btn1:
            if st.button("➖", key=f"{prefix}_sub_{item_id}"):
                scala_quantita_db(item_id, delta=1)
                st.rerun()
                
        with col_btn2:
            if st.button("🗑️", key=f"{prefix}_del_{item_id}"):
                elimina_item_db(item_id)
                st.rerun()


# --- 7. SEZIONE AI CHEF ---
@st.fragment
def sezione_ai_chef():
    st.header("🧑‍🍳 3. AI Chef & Consumo Smart")
    
    df = carica_da_db()
    if df.empty:
        st.info("Aggiungi prima qualche alimento in dispensa per creare le ricette!")
        return

    st.write("Imposta i commensali ed i target calorici del pasto:")
    
    col_a, col_b = st.columns(2)
    with col_a:
        num_adulti = st.number_input("👨‍💼 Numero Adulti:", min_value=1, max_value=10, value=2)
    with col_b:
        num_bambini = st.number_input("👶 Numero Bambini:", min_value=0, max_value=10, value=2)

    col_ka, col_kb = st.columns(2)
    with col_ka:
        kcal_adulto = st.number_input("🔥 Kcal / Adulto:", min_value=200, max_value=1500, value=600)
    with col_kb:
        kcal_bambino = st.number_input("👶🔥 Kcal / Bambino:", min_value=100, max_value=1200, value=380)

    kcal_totali_pasto = (num_adulti * kcal_adulto) + (num_bambini * kcal_bambino)
    st.caption(f"📊 **Target Totale Calcolato:** ~{kcal_totali_pasto} kcal ({num_adulti}x {kcal_adulto} kcal + {num_bambini}x {kcal_bambino} kcal)")

    tipo_pianificazione = st.selectbox(
        "📋 Tipo di Output:",
        ["Ricetta Singola (Salva-Cena)", "Piano Settimanale (Lunedì-Venerdì)"]
    )

    if st.button("🪄 Genera con l'IA Chef", type="primary"):
        if not ai_key:
            st.error("⚠️ Inserisci la tua API Key nella barra laterale a sinistra!")
            return

        alimenti_list = [f"- {row['nome']} (Categoria: {row['categoria']}, Scade tra {row['Giorni Rimasti']} giorni, Aperto: {'Sì' if row['aperto']==1 else 'No'}, Qtà: {row['quantita']})" for _, row in df.iterrows()]
        alimenti_str = "\n".join(alimenti_list)

        prompt = f"""
        Sei uno Chef Nutrizionista ed esperto Anti-Spreco.
        Crea una ricetta o piano usando i cibi in dispensa. Dà massima priorità ai cibi già APERTI o con pochissimi giorni rimasti!
        
        DISPENSA:
        {alimenti_str}
        
        COMMENSALI E TARGET CALORICI:
        - Adulti: {num_adulti} (Quota per CIASCUN adulto: {kcal_adulto} kcal)
        - Bambini: {num_bambini} (Quota per CIASCUN bambino: {kcal_bambino} kcal)
        - Target Calorico Totale del pasto: ~{kcal_totali_pasto} kcal.
        
        TIPO RICHIESTA: {tipo_pianificazione}
        
        ISTRUZIONI IMPORTANTI:
        1. Indica le dosi in grammi e porzioni separatamente per Adulti e Bambini.
        2. Assicurati che le porzioni per bambino rispettino esattamente il target di {kcal_bambino} kcal.
        3. Fai un riepilogo finale dei macro e valori nutrizionali.
        """

        try:
            with st.spinner("🧑‍🍳 L'IA sta creando la ricetta perfetta..."):
                st.session_state["ultima_ricetta"] = genera_ricetta_ai(prompt, ai_key)
        except Exception as e:
            st.error(f"Errore IA: {e}")

    if "ultima_ricetta" in st.session_state:
        st.markdown("---")
        st.markdown(st.session_state["ultima_ricetta"])
        
        st.success("🍽️ **Hai cucinato questo piatto? Scarica i cibi usati!**")
        
        cibi_usati = st.multiselect(
            "Seleziona i cibi consumati dalla dispensa:",
            options=df['nome'].tolist(),
            default=df['nome'].tolist()[:2]
        )

        if st.button("✅ Conferma e Scala dalla Dispensa"):
            for nome_cibo in cibi_usati:
                item_row = df[df['nome'] == nome_cibo]
                if not item_row.empty:
                    item_id = item_row.iloc[0]['id']
                    scala_quantita_db(item_id, delta=1)
            
            st.success("🎉 Dispensa aggiornata!")
            del st.session_state["ultima_ricetta"]
            st.rerun()


# --- ESECUZIONE APPLICAZIONE ---
sezione_ricerca()
st.divider()
sezione_dispensa()
st.divider()
sezione_ai_chef()
