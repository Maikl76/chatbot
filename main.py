import requests
import os
import pandas as pd
import logging
import time  
from flask import Flask, render_template, request, jsonify
from bs4 import BeautifulSoup
import fitz  
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

# ✅ Globální proměnná pro sledování tokenů
last_request_time = time.time()
total_tokens_sent = 0
TOKEN_LIMIT_PER_MINUTE = 6000
TOKEN_BUFFER = 500  # Rezerva pro jistotu

# ✅ Funkce pro sledování a čekání
def check_rate_limit():
    global total_tokens_sent, last_request_time

    elapsed_time = time.time() - last_request_time
    if elapsed_time < 60 and total_tokens_sent > (TOKEN_LIMIT_PER_MINUTE - TOKEN_BUFFER):
        wait_time = 60 - elapsed_time
        print(f"⏳ Překročen limit! Čekám {wait_time:.2f} sekund...")
        time.sleep(wait_time)
        total_tokens_sent = 0  # Resetujeme po 60 sekundách
    last_request_time = time.time()

# ✅ Funkce pro komunikaci s AI (každý požadavek max. 1500 tokenů)
def ask_groq(question, documents):
    """ Pošleme dotaz po malých částech max. 1500 tokenů a spojíme odpovědi. """
    global total_tokens_sent

    try:
        responses = []

        for i, doc in enumerate(documents):
            text = doc["Původní obsah"]

            # ✅ Rozdělení textu na 1500 tokenové části
            words = text.split()
            chunk_size = 1500
            text_chunks = [words[i:i + chunk_size] for i in range(0, len(words), chunk_size)]

            for j, chunk in enumerate(text_chunks):
                truncated_text = " ".join(chunk)
                prompt = f"Dokument {i+1}/{len(documents)}, část {j+1}/{len(text_chunks)}:\n{truncated_text}\n\nOtázka: {question}\nOdpověď:"

                check_rate_limit()  # ✅ Ověření před odesláním požadavku

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

                # ✅ Aktualizace počtu tokenů
                total_tokens_sent += len(truncated_text.split()) + 500
                print(f"📊 Celkem tokenů: {total_tokens_sent}")

                # ✅ Pauza mezi požadavky (2 sekundy)
                time.sleep(2)

        return "\n\n".join(responses)

    except Exception as e:
        logging.error(f"⛔ Chyba při volání Groq API: {e}")
        return f"❌ Chyba při komunikaci s AI: {str(e)}"

# ✅ API endpoint pro AI dotaz
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
