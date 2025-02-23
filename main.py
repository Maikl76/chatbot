from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
import requests
from sqlalchemy import create_engine, Column, String
from sqlalchemy.orm import sessionmaker, declarative_base
from bs4 import BeautifulSoup

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

# ✅ Hlavní stránka (vrací seznam webů do šablony)
@app.get("/", response_class=HTMLResponse)
async def serve_home(request: Request):
    session = SessionLocal()
    webpages = [webpage.url for webpage in session.query(WebPage).all()]
    session.close()
    return templates.TemplateResponse("index.html", {"request": request, "webpages": webpages})

# ✅ Přidání nové webové stránky (správně ukládá do databáze)
@app.post("/add_webpage/")
async def add_webpage(url: str = Form(...)):
    session = SessionLocal()
    exists = session.query(WebPage).filter(WebPage.url == url).first()
    if not exists:
        webpage = WebPage(url=url)
        session.add(webpage)
        session.commit()
    session.close()
    return {"message": "Stránka přidána", "url": url}

# ✅ Načtení seznamu sledovaných webových stránek
@app.get("/webpages/")
async def get_webpages():
    session = SessionLocal()
    webpages = [webpage.url for webpage in session.query(WebPage).all()]
    session.close()
    return webpages

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

# ✅ Načtení dokumentů z dané stránky
@app.get("/scrape/")
async def scrape(url: str):
    return scrape_webpage_links(url)

# ✅ Spuštění aplikace (správně nastaví port pro Render)
if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))  # Používá správný port pro Render
    uvicorn.run(app, host="0.0.0.0", port=port, reload=True)
