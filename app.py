import pandas as pd
import random
import difflib
from datetime import datetime, timedelta
import json
import os
from flask import Flask, request, redirect, url_for, session, flash, get_flashed_messages
from jinja2 import Environment, DictLoader

# Configura las rutas base
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
EXCEL_PATH = os.path.join(BASE_DIR, 'vocabulary_norwegian.xlsx')
PROGRESS_PATH = os.path.join(BASE_DIR, 'progress.json')

# ---------------------------
# Clases del Sistema SRS
# ---------------------------
class VocabularyCard:
    def __init__(self, data):
        # Manejar artículos vacíos y valores NaN
        article = str(data['Article']).strip() if pd.notna(data['Article']) else ""
        self.norwegian = f"{article} {data['Norwegian']}".strip() if article else data['Norwegian']
        self.english = data['English']  # Puede contener varias traducciones separadas por comas
        self.due_date = datetime.now()
        self.interval = 1
        self.ease = 2.5
        self.reps = 0
        self.fail_count = 0  # Contador de fallos
        self.id = None  # Se asignará un ID único en load_data

    def update(self, quality):
        if quality < 3:
            self.interval = 1
            self.reps = 0
            self.fail_count += 1  # Incrementa el contador de fallos si la respuesta es mala
        else:
            self.interval = (self.interval * self.ease) + 0.1
            self.reps += 1
        
        self.ease = max(1.3, self.ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
        self.due_date = datetime.now() + timedelta(days=int(self.interval))

class SpacedRepetitionSystem:
    def __init__(self, filename):
        self.cards = []
        self.progress_file = PROGRESS_PATH
        self.load_data(filename)
        # Asegúrate de que progress.json existe
        if not os.path.exists(self.progress_file):
            self.save_progress()  # Crea el archivo si no existe
        self.load_progress()
    
    def load_data(self, filename):
        df = pd.read_excel(filename, sheet_name='Sheet1')
        # Convertir NaN a strings vacíos y asegurar tipo string
        df['Article'] = df['Article'].fillna('').astype(str)
        
        for idx, (_, row) in enumerate(df.iterrows()):
            if pd.notna(row['Norwegian']) and pd.notna(row['English']):
                card = VocabularyCard({
                    'Article': row['Article'].strip(),
                    'Norwegian': row['Norwegian'],
                    'English': row['English']
                })
                card.id = idx  # Asignar un ID único
                self.cards.append(card)
    
    def load_progress(self):
        if os.path.exists(self.progress_file):
            with open(self.progress_file, 'r') as f:
                progress = json.load(f)
                for card, data in zip(self.cards, progress):
                    card.__dict__.update(data)
                    card.due_date = datetime.fromisoformat(data['due_date'])
    
    def save_progress(self):
        progress = []
        for card in self.cards:
            card_data = card.__dict__.copy()
            card_data['due_date'] = card.due_date.isoformat()
            progress.append(card_data)
        
        with open(self.progress_file, 'w') as f:
            json.dump(progress, f)
    
    def get_due_cards(self):
        print(f"Total cards loaded: {len(self.cards)}")
        due_cards = [card for card in self.cards if datetime.now() > card.due_date]
        print(f"Due cards: {len(due_cards)}")
        return due_cards
    
    def get_card_by_id(self, card_id):
        for card in self.cards:
            if card.id == card_id:
                return card
        return None

# ---------------------------
# Función para obtener diferencias
# ---------------------------
def get_diff(correct, user):
    """Genera un resumen de las diferencias entre la respuesta correcta y la del usuario."""
    sm = difflib.SequenceMatcher(None, correct, user)
    differences = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != 'equal':
            differences.append(f"{tag}: '{correct[i1:i2]}' vs '{user[j1:j2]}'")
    return "; ".join(differences)

# ---------------------------
# Configuración de Flask y Jinja2
# ---------------------------
app = Flask(__name__)
app.secret_key = "tu_clave_secreta_aqui"  # Necesaria para manejar la sesión

# Modifica la inicialización
srs = SpacedRepetitionSystem(EXCEL_PATH)

# ---------------------------
# Templates (almacenados en un diccionario)
# ---------------------------
templates = {
    "base": """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>SRS Vocabulario Noruego</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 0; }
        .container { display: flex; }
        .content { flex: 1; padding: 20px; }
        .sidebar { width: 300px; background: #f9f9f9; padding: 20px; border-left: 1px solid #ccc; }
        .card { background: #f4f4f4; padding: 20px; border-radius: 8px; }
        .feedback { font-size: 1.2em; margin-bottom: 20px; }
        .correct { color: green; }
        .incorrect { color: red; }
        ul { list-style: none; padding: 0; }
        li { margin-bottom: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="content">
            {% with messages = get_flashed_messages(with_categories=true) %}
              {% if messages %}
                {% for category, message in messages %}
                  <div class="feedback {{ category }}">{{ message }}</div>
                {% endfor %}
              {% endif %}
            {% endwith %}
            {% block content %}{% endblock %}
        </div>
        <div class="sidebar">
            <h3>Palabras Aprendidas</h3>
            {% if learned_cards %}
            <ul>
              {% for card in learned_cards %}
              <li><strong>{{ card.norwegian }}</strong><br>
                  Fiabilidad: {{ "%.2f"|format(card.ease) }}<br>
                  Repeticiones: {{ card.reps }}
              </li>
              {% endfor %}
            </ul>
            {% else %}
            <p>No hay palabras aprendidas todavía.</p>
            {% endif %}
            <h3>Palabras Falladas</h3>
            {% if failed_cards %}
            <ul>
              {% for card in failed_cards %}
              <li><strong>{{ card.norwegian }}</strong><br>
                  Fallos: {{ card.fail_count }}
              </li>
              {% endfor %}
            </ul>
            {% else %}
            <p>No hay palabras falladas todavía.</p>
            {% endif %}
        </div>
    </div>
</body>
</html>
""",
    "index": """
{% extends "base" %}
{% block content %}
  {% if card %}
    <h2>Palabra en Noruego:</h2>
    <h1>{{ card.norwegian }}</h1>
    <form method="post" action="{{ url_for('answer') }}">
        <input type="hidden" name="card_id" value="{{ card.id }}">
        <label for="answer">Traducción al inglés:</label><br>
        <input type="text" id="answer" name="answer" autofocus required style="width:100%;padding:8px;margin:10px 0;"><br>
        <button type="submit" style="padding:10px 20px;">Verificar</button>
    </form>
  {% else %}
    <h2>¡No hay tarjetas pendientes por ahora!</h2>
  {% endif %}
{% endblock %}
"""
}

# Configuramos el entorno Jinja2 usando DictLoader
env = Environment(loader=DictLoader(templates))
# Añadimos las funciones de Flask al entorno
env.globals.update({
    "get_flashed_messages": get_flashed_messages,
    "url_for": url_for
})

def render(template_name, **context):
    template = env.get_template(template_name)
    return template.render(**context)

# ---------------------------
# Rutas de la aplicación
# ---------------------------
@app.route("/", methods=["GET"])
def index():
    # Seleccionar una tarjeta pendiente
    due_cards = srs.get_due_cards()
    if due_cards:
        card = random.choice(due_cards)
        session["current_card_id"] = card.id
    else:
        card = None
    # Determinar las palabras aprendidas y falladas
    learned_cards = [card for card in srs.cards if card.reps > 0]
    failed_cards = [card for card in srs.cards if card.fail_count > 0]
    return render("index", card=card, learned_cards=learned_cards, failed_cards=failed_cards)

@app.route("/answer", methods=["POST"])
def answer():
    card_id = request.form.get("card_id")
    user_answer = request.form.get("answer", "").strip().lower()
    if card_id is None:
        flash("No se pudo identificar la tarjeta.", "incorrect")
        return redirect(url_for("index"))
    
    try:
        card_id = int(card_id)
    except ValueError:
        flash("Identificador de tarjeta inválido.", "incorrect")
        return redirect(url_for("index"))
    
    card = srs.get_card_by_id(card_id)
    if card is None:
        flash("Tarjeta no encontrada.", "incorrect")
        return redirect(url_for("index"))
    
    # Separamos las alternativas correctas (pueden estar separadas por comas)
    correct_translations = [alt.strip().lower() for alt in card.english.split(",")]
    
    # Comprobamos si la respuesta coincide exactamente con alguna alternativa
    if any(user_answer == alt for alt in correct_translations):
        flash("¡Correcto!", "correct")
        quality = 4
    else:
        # Buscamos la mejor coincidencia
        best_ratio = 0.0
        best_alt = None
        for alt in correct_translations:
            ratio = difflib.SequenceMatcher(None, alt, user_answer).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_alt = alt
        if best_ratio >= 0.8:
            diff_str = get_diff(best_alt, user_answer)
            flash(f"Incorrecto. La respuesta correcta es: {card.english}. ¡Casi! Has fallado por poco: {diff_str}", "incorrect")
            quality = 4
        else:
            flash(f"Incorrecto. La respuesta correcta es: {card.english}", "incorrect")
            quality = 2

    card.update(quality)
    srs.save_progress()
    
    return redirect(url_for("index"))

# ---------------------------
# Ejecución de la aplicación
# ---------------------------
if __name__ == "__main__":
    app.run(debug=True)
