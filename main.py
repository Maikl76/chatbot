import requests
import os
import pandas as pd
import logging
import time  # ✅ Přidáváme pauzu mezi požadavky
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

# ✅ Funkce pro komunikaci s AI (PŘIDANÁ PAUZA)
def ask_groq(question, documents):
    """ Pošleme dotaz po malých částech s pauzou mezi požadavky. """
    try:
        responses = []
        total_tokens_sent = 0  # ✅ Sledujeme celkové množství tokenů za minutu

        for i, doc in enumerate(documents):
            text = doc["Původní obsah"]
            words = text.split()
            chunk_size = 2000  # ✅ Každý požadavek max. 2000 tokenů
            text_chunks = [words[i:i + chunk_size] for i in range(0, len(words), chunk_size)]

            for j, chunk in enumerate(text_chunks):
                truncated_text = " ".join(chunk)
                prompt = f"Dokument {i+1}/{len(documents)}, část {j+1}/{len(text_chunks)}:\n{truncated_text}\n\nOtázka: {question}\nOdpověď:"

                # ✅ Pokud bychom překročili limit 6000 tokenů za minutu, počkáme
                if total_tokens_sent + 2000 > 6000:
                    print("⏳ Čekám 60 sekund, abych nepřekročil limit API...")
                    time.sleep(60)
                    total_tokens_sent = 0  # ✅ Resetujeme počítadlo

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

                # ✅ Aktualizujeme počet tokenů odeslaných za minutu
                total_tokens_sent += 2000 + 500
                print(f"📊 Odesláno celkem tokenů: {total_tokens_sent}")

                # ✅ PAUZA mezi požadavky (5 sekund)
                time.sleep(5)

        return "\n\n".join(responses)

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
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)
