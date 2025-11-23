import streamlit as st
import pandas as pd
import requests
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

# --------------------------------------------------
# CONFIGURAZIONE BASE + STILE
# --------------------------------------------------
st.set_page_config(page_title="🛸Redirect Checker by Maria Paloschi👾", layout="wide")

# Tema: sfondo nero, pulsanti in gradiente #ffebf2 → #a078b8
st.markdown(
    """
    <style>
    .stApp {
        background-color: #000000;
        color: #ffffff;
    }

    .stButton>button {
        background: linear-gradient(90deg, #ffebf2, #a078b8);
        color: #000000;
        border: none;
        border-radius: 999px;
        font-weight: 600;
        padding: 0.5rem 1.4rem;
        cursor: pointer;
        transition: all 0.15s ease-in-out;
    }

    .stButton>button:hover {
        filter: brightness(1.05);
        transform: translateY(-1px);
    }

    [data-testid="metric-container"] {
        background-color: #111111;
        border-radius: 0.75rem;
        padding: 0.75rem 0.6rem;
        border: 1px solid #333333;
    }

    [data-testid="metric-container"] > div {
        color: #ffffff;
    }

    .stDataFrame, .stDataFrame table, .stDataFrame th, .stDataFrame td {
        color: #ffffff !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("🪄 Redirect Checker per Migrazioni")

st.write(
    "Carica un file CSV con le colonne **'Redirect from'** e **'Redirect to'** "
    "(intestazioni nelle colonne A e B)."
)

uploaded_file = st.file_uploader("Carica il CSV", type=["csv"])


# --------------------------------------------------
# FUNZIONI
# --------------------------------------------------

def normalize_col(name: str) -> str:
    """Normalizza i nomi colonna per riconoscere 'Redirect from' / 'Redirect to' anche se scritti leggermente diversi."""
    return name.strip().lower().replace(" ", "").replace("_", "")


def check_url(url: str, max_redirects: int = 20):
    """
    Controlla una URL:
    - segue fino a max_redirects redirect
    - rileva loop
    - restituisce primo status, status finale, flag loop
    """
    if not url or str(url).strip() == "":
        return {
            "first_code": None,
            "final_code": None,
            "loop": False,
            "chain": []
        }

    url = str(url).strip()
    visited = []
    current = url
    first_code = None
    chain = []

    try:
        for _ in range(max_redirects):
            # loop di redirect
            if current in visited:
                return {
                    "first_code": first_code,
                    "final_code": None,
                    "loop": True,
                    "chain": chain
                }

            visited.append(current)

            resp = requests.get(current, allow_redirects=False, timeout=10)
            code = resp.status_code
            chain.append((current, code))

            if first_code is None:
                first_code = code

            # redirect 3xx
            if 300 <= code <= 399:
                location = resp.headers.get("Location") or resp.headers.get("location")
                if not location:
                    # redirect senza Location → ci fermiamo
                    return {
                        "first_code": first_code,
                        "final_code": code,
                        "loop": False,
                        "chain": chain
                    }

                # Location relativa → la uniamo
                if not location.startswith("http"):
                    current = urljoin(current, location)
                else:
                    current = location
                continue

            # codice finale (200, 404, 500, ecc.)
            return {
                "first_code": first_code,
                "final_code": code,
                "loop": False,
                "chain": chain
            }

        # troppi redirect senza loop esplicito
        return {
            "first_code": first_code,
            "final_code": None,
            "loop": False,
            "chain": chain
        }

    except Exception:
        # errore di rete / timeout / DNS
        return {
            "first_code": None,
            "final_code": None,
            "loop": False,
            "chain": chain
        }


def style_status(val, col_type):
    """
    Colori degli status come da specifiche:
    - FROM (tipo 'from'):
        404 → rosso + grassetto
        301 → verde
        200 → arancione
    - TO (tipo 'to'):
        404 → rosso + grassetto
        301 → arancione + grassetto
        200 → verde
    """
    if pd.isna(val):
        return ""
    try:
        code = int(val)
    except Exception:
        return ""

    if col_type == "from":
        if code == 404:
            return "color: white; background-color: red; font-weight: bold;"
        if code == 301:
            return "background-color: green; font-weight: normal;"
        if code == 200:
            return "background-color: orange; font-weight: normal;"
    else:
        if code == 404:
            return "color: white; background-color: red; font-weight: bold;"
        if code == 301:
            return "background-color: orange; font-weight: bold;"
        if code == 200:
            return "background-color: green; font-weight: normal;"

    return ""


def highlight_row_if_loop(row):
    """Evidenzia l'intera riga se c'è un loop (from o to)."""
    if row.get("loop_from") or row.get("loop_to"):
        return ["background-color: #ffcccc"] * len(row)
    return [""] * len(row)


def process_row(idx, from_url, to_url):
    """Elabora una singola riga (in parallelo nei thread)."""
    res_from = check_url(from_url)
    res_to = check_url(to_url)
    csv_row_number = idx + 2  # header = riga 1
    return {
        "CSV row": csv_row_number,
        "Redirect from": from_url,
        "Status from (primo codice)": res_from["first_code"],
        "Status from (finale)": res_from["final_code"],
        "loop_from": res_from["loop"],
        "Redirect to": to_url,
        "Status to (primo codice)": res_to["first_code"],
        "Status to (finale)": res_to["final_code"],
        "loop_to": res_to["loop"],
    }


# --------------------------------------------------
# LOGICA PRINCIPALE
# --------------------------------------------------

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
    original_len = len(df)

    # Riconosco le colonne from/to in modo robusto
    cols_norm = {normalize_col(c): c for c in df.columns}
    from_col = None
    to_col = None
    for key, original in cols_norm.items():
        if "redirectfrom" in key or key == "from":
            from_col = original
        if "redirectto" in key or key == "to":
            to_col = original

    if from_col is None or to_col is None:
        st.error("Non ho trovato colonne compatibili con 'Redirect from' e 'Redirect to'.")
    else:
        st.success(f"Trovate colonne: **{from_col}** (from), **{to_col}** (to)")

        # Limite di righe analizzate per run
        max_righe = st.number_input(
            "Quante righe vuoi analizzare in questa esecuzione?",
            min_value=1,
            max_value=original_len,
            value=min(original_len, 1000),
            step=100,
        )
        df = df.head(int(max_righe))

        # Numero di thread (più alto = più veloce ma più carico)
        n_workers = st.slider(
            "Quanti thread in parallelo usare?",
            min_value=5,
            max_value=40,
            value=20,
            step=5,
            help="Aumenta per velocizzare l'elaborazione di molte URL. Se il server è debole, tienilo più basso."
        )

        st.info(f"Sto analizzando {len(df)} righe su {original_len} totali nel file.")

        # Bottone per avviare il check
        if st.button("🐨 Avvia l'analisi"):
            progress = st.progress(0)
            status_text = st.empty()

            results = []
            total = len(df)
            done = 0

            # Thread pool per elaborare le righe in parallelo
            with ThreadPoolExecutor(max_workers=n_workers) as executor:
                futures = []
                for idx, row in df.iterrows():
                    from_url = row[from_col]
                    to_url = row[to_col]
                    futures.append(executor.submit(process_row, idx, from_url, to_url))

                for f in as_completed(futures):
                    res = f.result()
                    results.append(res)
                    done += 1
                    progress.progress(done / total)
                    status_text.text(f"Elaborate {done} righe su {total}...")

            status_text.text("Analisi completata.")
            progress.progress(1.0)

            # DataFrame finale
            res_df = pd.DataFrame(results).sort_values("CSV row")

            # --------------------------------------------------
            # METRICHE E RIASSUNTI
            # --------------------------------------------------
            total = len(res_df)

            total_redirects = (
                res_df["Status from (primo codice)"].between(300, 399) |
                res_df["Status to (primo codice)"].between(300, 399)
            ).sum()

            total_loops = (res_df["loop_from"] | res_df["loop_to"]).sum()

            problematic_mask = (
                res_df["loop_from"] |
                res_df["loop_to"] |
                res_df["Status from (finale)"].fillna(0).between(400, 599) |
                res_df["Status to (finale)"].fillna(0).between(400, 599)
            )
            total_problematic = problematic_mask.sum()
            problematic_rows = list(res_df.loc[problematic_mask, "CSV row"])

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.markdown("### 📊 Totale righe")
                st.metric(label="Righe analizzate", value=int(total))

            with col2:
                st.markdown("### 🔁 Redirect")
                st.metric(label="Righe con redirect", value=int(total_redirects))

            with col3:
                st.markdown("### 🔂 Loop di redirect")
                st.metric(label="Loop trovati", value=int(total_loops))
                if total_loops == 0:
                    st.caption("TUTTO OK!")

            with col4:
                st.markdown("### ⚠️ Redirect problematici")
                st.metric(label="Righe problematiche", value=int(total_problematic))

            st.markdown("---")
            st.markdown("### Dettaglio redirect problematici")
            if total_problematic > 0:
                st.error("Sono stati trovati redirect problematici.")
                st.write("Righe nel CSV (contando l'intestazione come riga 1):")
                st.write(problematic_rows)
            else:
                st.success("Nessun redirect problematico rilevato nelle righe analizzate.")

            # --------------------------------------------------
            # TABELLA CON COLORI E LOOP EVIDENZIATI
            # --------------------------------------------------
            styled = (
                res_df.style
                .apply(
                    lambda col: [style_status(v, "from") for v in col]
                    if col.name in ["Status from (primo codice)", "Status from (finale)"]
                    else [""] * len(col)
                )
                .apply(
                    lambda col: [style_status(v, "to") for v in col]
                    if col.name in ["Status to (primo codice)", "Status to (finale)"]
                    else [""] * len(col)
                )
                .apply(highlight_row_if_loop, axis=1)
            )

            st.markdown("---")
            st.markdown("### 🧾 Tabella completa")
            st.dataframe(styled, use_container_width=True)
