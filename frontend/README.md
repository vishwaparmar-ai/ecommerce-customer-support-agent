# ShopFlow AI — Streamlit Frontend

## Run

Start the FastAPI backend first:

```bash
uvicorn backend.main:app --reload
```

Then from the project root:

```bash
pip install -r frontend/requirements.txt
streamlit run frontend/app.py
```

Optional API URL:

```bash
SHOPFLOW_API_URL=http://localhost:8000 streamlit run frontend/app.py
```

On Windows PowerShell:

```powershell
$env:SHOPFLOW_API_URL="http://localhost:8000"
streamlit run frontend/app.py
```
