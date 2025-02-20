import requests
import os
import pandas as pd
import logging
from flask import Flask, render_template, request, jsonify
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
from dotenv import load_dotenv
from groq import Groq

# ✅ Načtení API klíče
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ✅ Inicializace klienta Groq
client = Groq(api_key=GROQ_API_KEY)

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ✅ Nastavení logování
logging.basicConfig(level=logging.DEBUG, filename='app.log', filemode='a', format='%(asctime)s - %(levelname)s - %(message)s')

# ✅ Cesty pro soubory
SOURCES_FILE = "sources.txt"
HISTORY_DIR = "historie_pdfs"

if not os.path.exists(HISTORY_DIR):
    os.makedirs(HISTORY_DIR)

# ✅ Inicializace databáze
columns = ["Název dokumentu", "Kategorie", "Datum vydání / aktualizace", "Odkaz na zdroj", "Shrnutí obsahu", "Soubor", "Klíčová slova", "Původní obsah"]
legislativa_db = pd.DataFrame(columns=columns)
document_status = {}

# ✅ Načteme seznam webových zdrojů
def load_sources():
    if os.path.exists(SOURCES_FILE):
        with open(SOURCES_FILE, "r", encoding="utf-8") as file:
            return [line.strip() for line in file.readlines()]
    return []

# ✅ Stáhneme PDF dokument a extrahujeme text
def extract_text_from_pdf(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            pdf_document = fitz.open(stream=response.content, filetype="pdf")
            return "\n".join([page.get_text("text") for page in pdf_document]).strip()
    except Exception as e:
        logging.error(f"Chyba při zpracování PDF: {e}")
    return ""

# ✅ Stáhneme seznam legislativních dokumentů
def scrape_legislation(url):
    response = requests.get(url)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        data = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if href.endswith(".pdf"):
                name = link.text.strip()
                full_url = href if href.startswith("http") else url[:url.rfind("/")+1] + href
                new_text = extract_text_from_pdf(full_url)
                document_status[name] = "Nový ✅"
                data.append([name, "Legislativa", "N/A", url, "", full_url, "předpisy", new_text])
        return pd.DataFrame(data, columns=columns)
    return pd.DataFrame(columns=columns)

# ✅ Načteme legislativní dokumenty
def load_initial_data():
    global legislativa_db
    urls = load_sources()
    legislativa_db = pd.concat([scrape_legislation(url) for url in urls], ignore_index=True)

load_initial_data()

# ✅ Vrátí seznam dokumentů pro konkrétní webovou stránku
@app.route('/get_documents', methods=['POST'])
def get_documents():
    selected_source = request.form.get("source", "").strip()
    if not selected_source:
        return jsonify({"error": "Vyberte webovou stránku."})

    filtered_docs = [doc for doc in legislativa_db.to_dict(orient="records") if doc["Odkaz na zdroj"] == selected_source]
    
    return jsonify({"documents": filtered_docs})

# ✅ Funkce pro komunikaci s AI (pevná dávka 2000 tokenů)
def ask_groq(question, documents):
    """ Pošleme dotaz po malých částech a spojíme odpovědi. """
    try:
        responses = []

        for i, doc in enumerate(documents):
            text = doc["Původní obsah"]

            # ✅ Rozdělení textu na 2000 tokenové části
            words = text.split()
            chunk_size = 2000
            text_chunks = [words[i:i + chunk_size] for i in range(0, len(words), chunk_size)]

            for j, chunk in enumerate(text_chunks):
                truncated_text = " ".join(chunk)
                prompt = f"Dokument {i+1}/{len(documents)}, část {j+1}/{len(text_chunks)}:\n{truncated_text}\n\nOtázka: {question}\nOdpověď:"

                completion = client.chat.completions.create(
                    model="deepseek-r1-distill-qwen-32b",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.6,
                    max_tokens=500,  # ✅ Každá odpověď max. 500 tokenů
                    top_p=0.95,
                    stream=False,
                    stop=None
                )

                responses.append(completion.choices[0].message.content.strip())

        # ✅ Finální odpověď
        final_answer = "\n\n".join(responses)

        # ✅ Shrnutí odpovědi, pokud je příliš dlouhá
        if len(final_answer.split()) > 400:
            summary_prompt = f"Shrň tuto odpověď do 100 slov:\n{final_answer}"

            summary_completion = client.chat.completions.create(
                model="deepseek-r1-distill-qwen-32b",
                messages=[{"role": "user", "content": summary_prompt}],
                temperature=0.6,
                max_tokens=200,  # ✅ Odpověď max. 200 tokenů
                top_p=0.95,
                stream=False,
                stop=None
            )

            return summary_completion.choices[0].message.content.strip()

        return final_answer

    except Exception as e:
        logging.error(f"⛔ Chyba při volání Groq API: {e}")
        return f"❌ Chyba při komunikaci s AI: {str(e)}"

# ✅ API endpoint pro AI dotaz (s výběrem webu)
@app.route('/ask', methods=['POST'])
def ask():
    question = request.form.get("question", "").strip()
    selected_source = request.form.get("source", "").strip()

    if not question:
        return jsonify({"error": "Zadejte otázku!"})
    if not selected_source:
        return jsonify({"error": "Vyberte webovou stránku!"})

    # ✅ Najdeme dokumenty z vybrané webové stránky
    selected_docs = [doc for doc in legislativa_db.to_dict(orient="records") if doc["Odkaz na zdroj"] == selected_source]

    if not selected_docs:
        return jsonify({"error": "Žádné dokumenty nenalezeny pro vybraný zdroj."})

    answer = ask_groq(question, selected_docs)
    return jsonify({"answer": answer})

# ✅ Hlavní webová stránka
@app.route('/')
def index():
    return render_template('index.html', documents=legislativa_db.to_dict(orient="records"), sources=load_sources(), document_status=document_status)

if __name__ == '__main__':
    app.run(debug=True)
