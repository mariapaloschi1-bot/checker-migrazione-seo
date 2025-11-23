import streamlit as st
import pandas as pd
import requests
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

# --------------------------------------------------
# CONFIGURAZIONE BASE + STILE
# --------------------------------------------------
st.set_page_config(page_title="Redirect Magic Checker", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600&display=swap');

    .stApp {
        background-color: #000000;
        color: #ffffff;
    }

    /* Pulsanti con gradiente #ffebf2 → #a078b8 */
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

    /* File uploader – drag & drop box con lo stesso gradiente */
    [data-testid="stFileUploaderDropzone"] {
        background: linear-gradient(90deg, #ffebf2, #a078b8);
        border-radius: 16px;
        border: none;
    }

    [data-testid="stFileUploaderDropzone"] > div {
        color: #000000;
        font-weight: 500;
    }

    /* Metric box con gradiente e testo maiuscolo */
    [data-testid="metric-container"] {
        background: linear-gradient(90deg, #ffebf2, #a078b8);
        border-radius: 0.75rem;
        padding: 0.75rem 0.6rem;
        border: none;
        color: #000000 !important;
    }

    [data-testid="metric-container"] > div > div {
        color: #000000 !important;
        text-transform: uppercase;
        font-family: 'Poppins', sans-serif;
    }

    /* Tabella: font Poppins e testo chiaro */
    .stDataFrame, .stDataFrame table, .stDataFrame th, .stDataFrame td {
        color: #ffffff !important;
        font-family: 'Poppins', sans-serif !important;
        font-size: 13px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("🪄 Redirect Magic Checker 🐨")

st.markdown(
    """
    Questo tool 🔮 ti aiuta a controllare i redirect durante una migrazione (fino a **2.500 URL**).  
    Carica un CSV con le colonne **Redirect from** (URL di partenza) e **Redirect to** (URL di arrivo):  
    il tool controllerà gli status code, individuerà i loop di redirect e segnalerà i redirect problematici.
    """
)

uploaded_file = st.file_uploader("Trascina qui il tuo CSV (max ~2.500 URL)", type=["csv"])


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
        200 → verde (come i 301 della prima colonna)
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
    """Evidenzia l'intera riga se c'è un loop (Check Loop = True)."""
    if row.get("Check Loop"):
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


def explain_problem(row):
    """Spiega cosa non va in un redirect problematico."""
    reasons = []
    if row.get("Check Loop"):
        reasons.append("Loop di redirect (catena che torna su sé stessa)")
    sc_from = row.get("Status code url di partenza")
    sc_to = row.get("Status code url di arrivo")

    try:
        if pd.notna(sc_from) and 400 <= int(sc_from) <= 499:
            reasons.append("URL di partenza con errore client (4xx)")
        if pd.notna(sc_from) and 500 <= int(sc_from) <= 599:
            reasons.append("URL di partenza con errore server (5xx)")
        if pd.notna(sc_to) and 400 <= int(sc_to) <= 499:
            reasons.append("URL di arrivo con errore client (4xx)")
        if pd.notna(sc_to) and 500 <= int(sc_to) <= 599:
            reasons.append("URL di arrivo con errore server (5xx)")
    except Exception:
        pass

    if not reasons:
        return "Comportamento anomalo non classificato (controllare manualmente)"
    return " + ".join(reasons)


# --------------------------------------------------
# LOGICA PRINCIPALE
# --------------------------------------------------

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
    original_len = len(df)

    # Limite logico a 2500 URL
    if original_len > 2500:
        st.warning(
            f"Hai caricato {original_len} righe. Il tool è pensato per migrazioni fino a 2.500 URL: "
            "verranno considerate solo le prime 2.500."
        )
        df = df.head(2500)
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

        st.info(f"Sto analizzando {len(df)} righe (su {original_len} presenti nel file caricato).")

        # Bottone per avviare il check
        if st.button("🚀 Avvia analisi"):
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

            # DataFrame completo
            res_df = pd.DataFrame(results).sort_values("CSV row")

            # Colonna unica per il loop
            res_df["Check Loop"] = res_df["loop_from"] | res_df["loop_to"]

            # Status di partenza/arrivo (usiamo lo status finale)
            res_df["Status code url di partenza"] = res_df["Status from (finale)"]
            res_df["Status code url di arrivo"] = res_df["Status to (finale)"]

            # Conversione a interi "puliti" (niente .000000)
            for col in [
                "Status from (primo codice)",
                "Status from (finale)",
                "Status to (primo codice)",
                "Status to (finale)",
                "Status code url di partenza",
                "Status code url di arrivo",
            ]:
                res_df[col] = pd.to_numeric(res_df[col], errors="coerce").astype("Int64")

            # --------------------------------------------------
            # METRICHE E RIASSUNTI
            # --------------------------------------------------
            total_rows = len(res_df)

            total_redirects = (
                res_df["Status from (primo codice)"].between(300, 399) |
                res_df["Status to (primo codice)"].between(300, 399)
            ).sum()

            total_loops = res_df["Check Loop"].sum()

            problematic_mask = (
                res_df["Check Loop"] |
                res_df["Status code url di partenza"].between(400, 599) |
                res_df["Status code url di arrivo"].between(400, 599)
            )

            total_problematic = problematic_mask.sum()
            problematic_rows = list(res_df.loc[problematic_mask, "CSV row"])

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.markdown("### TOTALE RIGHE")
                st.metric(label="RIGHE ANALIZZATE", value=int(total_rows))

            with col2:
                st.markdown("### REDIRECT")
                st.metric(label="RIGHE CON REDIRECT", value=int(total_redirects))

            with col3:
                st.markdown("### LOOP DI REDIRECT")
                st.metric(label="LOOP TROVATI", value=int(total_loops))
                if total_loops == 0:
                    st.caption("TUTTO OK!")

            with col4:
                st.markdown("### REDIRECT PROBLEMATICI")
                st.metric(label="RIGHE PROBLEMATICHE", value=int(total_problematic))

            st.markdown("---")
            st.markdown("### DETTAGLIO REDIRECT PROBLEMATICI")

            if total_problematic > 0:
                st.error(
                    "Sono stati trovati dei redirect problematici. "
                    "Qui sotto trovi le righe coinvolte e una spiegazione del problema."
                )

                prob_df = res_df.loc[problematic_mask, [
                    "CSV row",
                    "Check Loop",
                    "Redirect from",
                    "Status code url di partenza",
                    "Redirect to",
                    "Status code url di arrivo",
                ]].copy()

                prob_df["Motivo problema"] = prob_df.apply(explain_problem, axis=1)

                st.dataframe(prob_df, use_container_width=True)
                st.write(
                    "Le righe sono indicate con il numero di riga del CSV (header = riga 1)."
                )
            else:
                st.success("Nessun redirect problematico rilevato nelle righe analizzate.")

            # --------------------------------------------------
            # TABELLA COMPLETA ORDINATA + STYLING
            # --------------------------------------------------
            display_df = res_df[[
                "CSV row",
                "Check Loop",
                "Redirect from",
                "Status code url di partenza",
                "Redirect to",
                "Status code url di arrivo",
            ]].copy()

            styled = (
                display_df.style
                .apply(
                    lambda col: [style_status(v, "from") for v in col]
                    if col.name == "Status code url di partenza"
                    else [""] * len(col)
                )
                .apply(
                    lambda col: [style_status(v, "to") for v in col]
                    if col.name == "Status code url di arrivo"
                    else [""] * len(col)
                )
                .apply(highlight_row_if_loop, axis=1)
            )

            st.markdown("---")
            st.markdown("### TABELLA COMPLETA REDIRECT")
            st.dataframe(styled, use_container_width=True)

            st.markdown("---")
            st.markdown(
                "<p style='text-align:center; color:#ffffff; font-family:Poppins, sans-serif;'>"
                "❤️ Made by <strong>Maria Paloschi</strong> with love"
                "</p>",
                unsafe_allow_html=True,
            )
