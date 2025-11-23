# Redirect Checker per Migrazioni

Tool Streamlit per verificare redirect da un CSV e trovare:

- Status code del "Redirect from"
- Status code del "Redirect to"
- Loop di redirect
- Redirect problematici (loop o status 4xx/5xx)

## Input

CSV con almeno:

- Colonna A: `Redirect from`
- Colonna B: `Redirect to`

I nomi possono variare leggermente (es. `redirect_from`, `Redirect From`), l'app li riconosce in automatico.

## Come eseguire in locale

```bash
python -m venv .venv
source .venv/bin/activate  # su Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
