from fastapi import FastAPI, UploadFile, File, Form
import pdfplumber
import docx
import requests
import os
from dotenv import load_dotenv

# Načtení API klíče z .env souboru
load_dotenv()
API_KEY = os.getenv("GROQ_API_KEY")  # Použij svůj API klíč z Groq/OpenRouter
API_URL = "https://api.groq.com/v1/chat/completions"  # Upravit podle API poskytovatele

app = FastAPI()

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
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "mixtral-8x7b-32768",  # Použití Groq Mixtral (zdarma)
        "messages": [{"role": "system", "content": "Jsi asistent odpovídající na otázky k dokumentům."},
                     {"role": "user", "content": prompt}]
    }
    response = requests.post(API_URL, headers=headers, json=data)
    return response.json()["choices"][0]["message"]["content"]

@app.post("/chat/")
async def chat_with_file(filename: str = Form(...), user_input: str = Form(...)):
    if filename not in uploaded_files:
        return {"error": "Soubor nenalezen"}

    context = uploaded_files[filename]
    prompt = f"Dokument:\n{context}\n\nOtázka: {user_input}\nOdpověď:"
    
    response_text = ask_groq(prompt)
    return {"response": response_text}
