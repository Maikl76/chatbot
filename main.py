from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
import requests
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, String, Text
from sqlalchemy.orm import sessionmaker, declarative_base
from bs4 import BeautifulSoup

# Načtení API klíče z .env souboru
load_dotenv()
API_KEY = os.getenv("GROQ_API_KEY")

# Inicializace FastAPI
app = FastAPI()

# Nastavení SQLite databáze
DATABASE_URL = "sqlite:///./files.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

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

# ✅ Funkce pro skenování PDF/DOCX odkazů na webových stránkách
def scrape_webpage_links(url):
    response = requests.get(url)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        links = [a["href"] for a in soup.find_all("a", href=True) if a["href"].endswith(".pdf") or a["href"].endswith(".docx")]

        # Převod relativních odkazů na absolutní
        base_url = url[:url.rfind("/")+1]
        full_links = [link if link.startswith("http") else base_url + link for link in links]
        return full_links
    return []

# ✅ Hlavní stránka – zobrazí index.html se seznamem webových stránek a PDF/DOCX odkazy
@app.get("/", response_class=HTMLResponse)
async def serve_home(request: Request):
    session = SessionLocal()
    webpages = session.query(WebPage.url).all()
    session.close()

    # Skenování odkazů z uložených webových stránek
    all_links = {}
    for url in webpages:
        all_links[url[0]] = scrape_webpage_links(url[0])

    return templates.TemplateResponse("index.html", {
        "request": request, 
        "webpages": [url[0] for url in webpages], 
        "links": all_links  # Odkazy ke každé stránce
    })

# ✅ Přidání nové webové stránky do seznamu
@app.post("/add_webpage/")
async def add_webpage(url: str = Form(...)):
    session = SessionLocal()
    webpage = WebPage(url=url)
    session.merge(webpage)
    session.commit()
    session.close()
    return {"message": "Stránka přidána", "url": url}
