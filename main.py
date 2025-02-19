from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
import pdfplumber
import docx
import requests
import os
from dotenv import load_dotenv

# Načtení API klíče z .env souboru
load_dotenv()
API_KEY = os.getenv("GROQ_API_KEY")

# Debugging API klíče
if API_KEY:
    print("✅ API klíč načten:", API_KEY[:5] + "..." + API_KEY[-5:])  # Skrýt část klíče
else:
    print("❌ Chyba: API klíč se nenačetl! Zkontroluj .env nebo Render Environment Variables.")

API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Inicializace FastAPI
app = FastAPI()

# Kontrola, zda existuje složka 'static' (aby nedošlo k chybě)
if not os.path.exists("static"):
    os.makedirs("static")

# Nastavení složky pro HTML šablony
templates = Jinja2Templates(directory="templates")

# Servírování statických souborů (např. CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Hlavní stránka – zobrazí index.html
@app.get("/", response_class=HTMLResponse)
async def serve_home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Funkce pro extrakci textu z PDF
def extract_text_from_pdf(file):
    text = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            extracted_text = page.extract_text()
            if extracted_text:
                text += extracted_text + "\n"
    return text

# Funkce pro extrakci textu z Word dokumentu
def extract_text_from_docx(file):
    doc = docx.Document(file)
    text = "\n".join([para.text for para in doc.paragraphs])
    return text

# Uložení souborů do paměti
uploaded_files = {}

@app.post("/upload/")
async def upload_file(file: UploadFile = File(...)):
    # Zjištění typu souboru
    file_ext = file.filename.split(".")[-1]
    text = ""

    if file_ext == "pdf":
        text = extract_text_from_pdf(file.file)
    elif file_ext == "docx":
        text = extract_text_from_docx(file.file)
    else:
        return {"error": "Nepodporovaný formát. Použij PDF nebo DOCX."}

    uploaded_files[file.filename] = text
    return {"message": "Soubor nahrán", "filename": file.filename}

# Funkce pro volání Groq API
def ask_groq(prompt):
    if not API_KEY:
        return "❌ Chyba: API klíč není načten. Ověř proměnnou GROQ_API_KEY."

    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "mixtral-8x7b-32768",
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        response = requests.post(API_URL, headers=headers, json=data)
        response_json = response.json()

        # DEBUGGING: Loguj celou odpověď z API do Render Logs
        print("GROQ RESPONSE:", response_json)

        if "choices" in response_json and len(response_json["choices"]) > 0:
            return response_json["choices"][0]["message"]["content"]
        elif "error" in response_json:
            return f"❌ Chyba API: {response_json['error'].get('message', 'Neznámá chyba')}"
        else:
            return "❌ Chyba: Neočekávaný formát odpovědi od API."

    except requests.exceptions.RequestException as e:
        print("❌ Chyba při volání API:", str(e))
        return "❌ Chyba při komunikaci s AI modelem."

@app.post("/chat/")
async def chat_with_file(filename: str = Form(...), user_input: str = Form(...)):
    if filename not in uploaded_files:
        return {"error": "❌ Soubor nenalezen"}

    context = uploaded_files[filename]
    prompt = f"Dokument:\n{context}\n\nOtázka: {user_input}\nOdpověď:"

    # DEBUGGING: Loguj prompt do Render Logs
    print("GENEROVANÝ PROMPT:", prompt)

    response_text = ask_groq(prompt)
    return {"response": response_text}
