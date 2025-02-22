from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
import pdfplumber
import docx
import requests
import os
import sqlite3
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, String, Text
from sqlalchemy.orm import sessionmaker, declarative_base
from bs4 import BeautifulSoup

# Načtení API klíče z .env souboru
load_dotenv()
API_KEY = os.getenv("GROQ_API_KEY")
API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Inicializace FastAPI
app = FastAPI()

# Nastavení SQLite databáze
DATABASE_URL = "sqlite:///./files.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# Definice tabulky pro soubory
class FileModel(Base):
    __tablename__ = "files"
    filename = Column(String, primary_key=True)
    content = Column(Text, nullable=False)

# Definice tabulky pro webové stránky
class WebPage(Base):
    __tablename__ = "webpages"
    url = Column(String, primary_key=True)

# Vytvoření tabulek, pokud neexistují
Base.metadata.create_all(bind=engine)

# Nastavení složky pro HTML šablony
templates = Jinja2Templates(directory="templates")

# Servírování statických souborů (např. CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Hlavní stránka – zobrazí index.html
@app.get("/", response_class=HTMLResponse)
async def serve_home(request: Request):
    session = SessionLocal()
    webpages = session.query(WebPage.url).all()
    session.close()
    
    return templates.TemplateResponse("index.html", {"request": request, "webpages": [url[0] for url in webpages]})

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

# Funkce pro skenování webových stránek
def scrape_webpage(url):
    response = requests.get(url)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        links = [a["href"] for a in soup.find_all("a", href=True) if a["href"].endswith(".pdf") or a["href"].endswith(".docx")]
        return links
    return []

# Přidání nové webové stránky do seznamu
@app.post("/add_webpage/")
async def add_webpage(url: str = Form(...)):
    session = SessionLocal()
    webpage = WebPage(url=url)
    session.merge(webpage)
    session.commit()
    session.close()
    return {"message": "Stránka přidána", "url": url}

# Endpoint pro nahrání více souborů najednou
@app.post("/upload/")
async def upload_files(files: list[UploadFile] = File(...)):
    session = SessionLocal()
    uploaded_filenames = []

    for file in files:
        file_ext = file.filename.split(".")[-1]
        text = ""

        if file_ext == "pdf":
            text = extract_text_from_pdf(file.file)
        elif file_ext == "docx":
            text = extract_text_from_docx(file.file)
        else:
            continue  # Nepodporovaný formát

        # Uložit do databáze
        file_entry = FileModel(filename=file.filename, content=text)
        session.merge(file_entry)  # Pokud už existuje, aktualizuje ho
        uploaded_filenames.append(file.filename)

    session.commit()
    session.close()
    return {"message": "Soubory nahrány", "filenames": uploaded_filenames}

# Funkce pro volání Groq API
def ask_groq(prompt):
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "mixtral-8x7b-32768",
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        response = requests.post(API_URL, headers=headers, json=data)
        response_json = response.json()
        if "choices" in response_json and len(response_json["choices"]) > 0:
            return response_json["choices"][0]["message"]["content"]
        elif "error" in response_json:
            return f"❌ Chyba API: {response_json['error'].get('message', 'Neznámá chyba')}"
        else:
            return "❌ Chyba: Neočekávaný formát odpovědi od API."

    except requests.exceptions.RequestException as e:
        return f"❌ Chyba při komunikaci s AI: {str(e)}"

@app.post("/chat/")
async def chat_with_files(filenames: str = Form(...), user_input: str = Form(...)):
    session = SessionLocal()
    file_names_list = filenames.split(",")
    context = ""

    for filename in file_names_list:
        file_entry = session.query(FileModel).filter(FileModel.filename == filename.strip()).first()
        if file_entry:
            context += f"\n\n=== {filename} ===\n{file_entry.content}"

    session.close()

    if not context:
        return {"error": "❌ Žádné soubory nebyly nalezeny!"}

    # Zkrácení textu na 1500 slov (~1900 tokenů)
    truncated_context = " ".join(context.split()[-1500:])

    prompt = f"Dokumenty:\n{truncated_context}\n\nOtázka: {user_input}\nOdpověď:"
    response_text = ask_groq(prompt)
    return {"response": response_text}

# Vyhledávání klíčového slova v dokumentech
@app.post("/search/")
async def search_documents(keyword: str = Form(...)):
    session = SessionLocal()
    results = []
    seen_paragraphs = set()

    files = session.query(FileModel).all()
    for file in files:
        paragraphs = file.content.split("\n\n")  # Rozdělení textu na odstavce
        for paragraph in paragraphs:
            if keyword.lower() in paragraph.lower() and paragraph not in seen_paragraphs:
                results.append(paragraph.strip())
                seen_paragraphs.add(paragraph)

    session.close()

    if not results:
        return {"message": "❌ Žádné výsledky nenalezeny."}

    return {"results": results}
