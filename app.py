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
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SRS Vocabulario Noruego</title>
    <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap" rel="stylesheet">
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            -webkit-tap-highlight-color: transparent;
        }
        
        body {
            font-family: 'Roboto', sans-serif;
            line-height: 1.6;
            background-color: #f0f2f5;
            color: #333;
            padding-bottom: env(safe-area-inset-bottom);
        }

        .container {
            max-width: 100%;
            margin: 0 auto;
            padding: 0.5rem;
        }

        .content {
            margin-bottom: 1rem;
        }

        .sidebar {
            background: white;
            border-radius: 12px 12px 0 0;
            padding: 1rem;
            box-shadow: 0 -2px 10px rgba(0,0,0,0.1);
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            max-height: 40vh;
            overflow-y: auto;
            z-index: 1000;
            transition: transform 0.3s ease;
        }

        .sidebar.hidden {
            transform: translateY(100%);
        }

        .sidebar-toggle {
            position: fixed;
            bottom: 41vh;
            right: 1rem;
            background: #4a90e2;
            color: white;
            border: none;
            border-radius: 50%;
            width: 3rem;
            height: 3rem;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
            z-index: 1001;
        }

        .card {
            background: white;
            padding: 1.5rem;
            border-radius: 12px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 1rem;
        }

        .feedback {
            font-size: 1rem;
            padding: 1rem;
            border-radius: 8px;
            margin-bottom: 1rem;
            position: fixed;
            top: 1rem;
            left: 1rem;
            right: 1rem;
            z-index: 1002;
            animation: slideIn 0.3s ease;
        }

        @keyframes slideIn {
            from { transform: translateY(-100%); }
            to { transform: translateY(0); }
        }

        .correct {
            background-color: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }

        .incorrect {
            background-color: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }

        h1 {
            font-size: 2rem !important;
            margin: 1rem 0 !important;
        }

        h2 {
            font-size: 1.5rem;
        }

        h3 {
            font-size: 1.2rem;
            margin: 0.5rem 0;
        }

        input[type="text"] {
            width: 100%;
            padding: 1rem;
            font-size: 1.2rem;
            border: 2px solid #ddd;
            border-radius: 8px;
            margin: 0.5rem 0;
            transition: border-color 0.3s;
            -webkit-appearance: none;
        }

        input[type="text"]:focus {
            outline: none;
            border-color: #4a90e2;
        }

        button {
            background-color: #4a90e2;
            color: white;
            padding: 1rem;
            border: none;
            border-radius: 8px;
            font-size: 1.2rem;
            cursor: pointer;
            transition: background-color 0.3s;
            width: 100%;
            margin-top: 0.5rem;
            -webkit-appearance: none;
        }

        button:active {
            background-color: #357abd;
            transform: scale(0.98);
        }

        .word-card {
            padding: 0.8rem;
            border-bottom: 1px solid #eee;
        }

        .word-norwegian {
            font-size: 1.1rem;
            font-weight: 500;
        }

        .word-stats {
            font-size: 0.9rem;
            color: #666;
        }

        .no-cards {
            text-align: center;
            padding: 1.5rem;
            color: #666;
        }

        @media (min-width: 768px) {
            .container {
                max-width: 1200px;
                padding: 1rem;
                display: flex;
                gap: 2rem;
            }

            .content {
                flex: 1;
            }

            .sidebar {
                position: static;
                width: 300px;
                max-height: none;
                border-radius: 12px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }

            .sidebar-toggle {
                display: none;
            }

            .card {
                padding: 2rem;
            }

            h1 {
                font-size: 2.5rem !important;
            }
        }

        .stats-card {
            background: white;
            padding: 1.5rem;
            border-radius: 12px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 1rem;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 1rem;
            margin-bottom: 1.5rem;
        }

        .stat-item {
            text-align: center;
        }

        .stat-value {
            font-size: 1.8rem;
            font-weight: bold;
            color: #4a90e2;
        }

        .stat-label {
            font-size: 0.9rem;
            color: #666;
        }

        .progress-bar {
            height: 24px;
            background: #f0f0f0;
            border-radius: 12px;
            overflow: hidden;
            display: flex;
        }

        .progress-segment {
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 0.8rem;
            transition: width 0.3s ease;
        }

        .progress-segment.mastered {
            background-color: #4CAF50;
        }

        .progress-segment.learning {
            background-color: #2196F3;
        }

        .progress-label {
            display: inline-block;
            padding: 0 0.5rem;
            white-space: nowrap;
        }

        .feedback-card {
            text-align: center;
            padding: 1.5rem;
            margin-bottom: 1rem;
            border-left: 5px solid;
        }

        .feedback-card.correct {
            background-color: #f8fff9;
            border-color: #4CAF50;
        }

        .feedback-card.incorrect {
            background-color: #fff8f8;
            border-color: #f44336;
        }

        .feedback-content {
            font-size: 1.2rem;
            margin-bottom: 1.5rem;
        }

        .next-button {
            background-color: #4a90e2;
            color: white;
            padding: 1rem 2rem;
            border: none;
            border-radius: 8px;
            font-size: 1.1rem;
            cursor: pointer;
            transition: all 0.3s ease;
            width: auto;
            display: inline-block;
        }

        .next-button:hover {
            background-color: #357abd;
        }

        .next-button:active {
            transform: scale(0.98);
        }

        .word-modal {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 2000;
            padding: 1rem;
        }

        .word-modal-content {
            background: white;
            border-radius: 12px;
            width: 90%;
            max-width: 500px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
        }

        .word-modal-header {
            padding: 1rem;
            border-bottom: 1px solid #eee;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .word-modal-header h2 {
            margin: 0;
            font-size: 1.5rem;
            color: #2c3e50;
        }

        .close-button {
            background: none;
            border: none;
            font-size: 1.5rem;
            color: #666;
            cursor: pointer;
            padding: 0.5rem;
            width: auto;
        }

        .word-modal-body {
            padding: 1rem;
        }

        .word-detail {
            padding: 0.8rem 0;
            border-bottom: 1px solid #eee;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .word-detail:last-child {
            border-bottom: none;
        }

        .detail-label {
            color: #666;
            font-weight: 500;
        }

        .detail-value {
            color: #2c3e50;
            font-weight: 600;
        }

        .word-card {
            cursor: pointer;
            transition: background-color 0.2s;
        }

        .word-card:active {
            background-color: #f5f5f5;
        }

        .stats-header {
            display: flex;
            align-items: center;
            gap: 1rem;
            margin-bottom: 1rem;
        }

        .back-button {
            background: #4a90e2;
            color: white;
            padding: 0.5rem 1rem;
            border: none;
            border-radius: 8px;
            font-size: 1rem;
            cursor: pointer;
            width: auto;
        }

        .words-section {
            margin-top: 2rem;
        }

        .words-section h2 {
            margin: 1.5rem 0 1rem;
            color: #2c3e50;
        }

        .words-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }

        .word-card.detailed {
            background: white;
            padding: 1rem;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }

        .word-card.detailed:active {
            transform: scale(0.98);
        }

        .word-card.detailed .word-stats {
            display: flex;
            flex-direction: column;
            gap: 0.3rem;
            margin-top: 0.5rem;
            font-size: 0.9rem;
            color: #666;
        }
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
        <button class="sidebar-toggle" onclick="toggleSidebar()">↑</button>
        <div class="sidebar hidden" id="sidebar">
            <h3>Palabras Aprendidas</h3>
            {% if learned_cards %}
            <div class="word-list">
              {% for card in learned_cards %}
              <div class="word-card" onclick="showWordDetails('{{ card.norwegian }}', '{{ card.english }}', {{ card.ease }}, {{ card.reps }}, {{ card.fail_count }}, '{{ card.due_date.isoformat() }}')">
                  <div class="word-norwegian">{{ card.norwegian }}</div>
                  <div class="word-stats">
                      Fiabilidad: {{ "%.2f"|format(card.ease) }} | 
                      Repeticiones: {{ card.reps }}
                  </div>
              </div>
              {% endfor %}
            </div>
            {% else %}
            <p class="no-cards">No hay palabras aprendidas todavía.</p>
            {% endif %}

            <h3>Palabras Falladas</h3>
            {% if failed_cards %}
            <div class="word-list">
              {% for card in failed_cards %}
              <div class="word-card" onclick="showWordDetails('{{ card.norwegian }}', '{{ card.english }}', {{ card.ease }}, {{ card.reps }}, {{ card.fail_count }}, '{{ card.due_date.isoformat() }}')">
                  <div class="word-norwegian">{{ card.norwegian }}</div>
                  <div class="word-stats">Fallos: {{ card.fail_count }}</div>
              </div>
              {% endfor %}
            </div>
            {% else %}
            <p class="no-cards">No hay palabras falladas todavía.</p>
            {% endif %}
        </div>
    </div>
    <script>
        function toggleSidebar() {
            const sidebar = document.getElementById('sidebar');
            sidebar.classList.toggle('hidden');
            const button = document.querySelector('.sidebar-toggle');
            button.textContent = sidebar.classList.contains('hidden') ? '↑' : '↓';
        }

        function showWordDetails(norwegian, english, ease, reps, failCount, dueDate) {
            const modal = document.createElement('div');
            modal.className = 'word-modal';
            
            const formattedDate = new Date(dueDate).toLocaleString('es-ES', {
                year: 'numeric',
                month: 'long',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });

            modal.innerHTML = `
                <div class="word-modal-content">
                    <div class="word-modal-header">
                        <h2>${norwegian}</h2>
                        <button onclick="this.parentElement.parentElement.parentElement.remove()" class="close-button">×</button>
                    </div>
                    <div class="word-modal-body">
                        <div class="word-detail">
                            <span class="detail-label">Significado:</span>
                            <span class="detail-value">${english}</span>
                        </div>
                        <div class="word-detail">
                            <span class="detail-label">Facilidad:</span>
                            <span class="detail-value">${parseFloat(ease).toFixed(2)}</span>
                        </div>
                        <div class="word-detail">
                            <span class="detail-label">Repeticiones:</span>
                            <span class="detail-value">${reps}</span>
                        </div>
                        <div class="word-detail">
                            <span class="detail-label">Fallos:</span>
                            <span class="detail-value">${failCount}</span>
                        </div>
                        <div class="word-detail">
                            <span class="detail-label">Próxima revisión:</span>
                            <span class="detail-value">${formattedDate}</span>
                        </div>
                    </div>
                </div>
            `;
            
            document.body.appendChild(modal);
            
            modal.addEventListener('click', function(e) {
                if (e.target === modal) {
                    modal.remove();
                }
            });
        }

        // Ocultar mensajes de feedback después de 3 segundos
        document.addEventListener('DOMContentLoaded', () => {
            const feedbacks = document.querySelectorAll('.feedback');
            feedbacks.forEach(feedback => {
                setTimeout(() => {
                    feedback.style.opacity = '0';
                    feedback.style.transition = 'opacity 0.5s ease';
                    setTimeout(() => feedback.remove(), 500);
                }, 3000);
            });
        });
    </script>
</body>
</html>
""",
    "index": """
{% extends "base" %}
{% block content %}
  <div class="stats-card" onclick="window.location.href='{{ url_for('stats') }}'" style="cursor: pointer">
    <div class="stats-grid">
      <div class="stat-item">
        <div class="stat-value">{{ stats.mastered }}</div>
        <div class="stat-label">Dominadas</div>
      </div>
      <div class="stat-item">
        <div class="stat-value">{{ stats.learning }}</div>
        <div class="stat-label">Aprendiendo</div>
      </div>
      <div class="stat-item">
        <div class="stat-value">{{ stats.new }}</div>
        <div class="stat-label">Nuevas</div>
      </div>
    </div>
    <div class="progress-bar">
      <div class="progress-segment mastered" style="width: {{ stats.mastered_percent }}%">
        <span class="progress-label">{{ stats.mastered_percent }}%</span>
      </div>
      <div class="progress-segment learning" style="width: {{ stats.learning_percent }}%">
        <span class="progress-label">{{ stats.learning_percent }}%</span>
      </div>
    </div>
  </div>

  {% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}
      {% for category, message in messages %}
        <div class="card feedback-card {{ category }}">
          <div class="feedback-content">{{ message }}</div>
          <button onclick="window.location.href='{{ url_for('index') }}'" class="next-button">
            Siguiente palabra →
          </button>
        </div>
      {% endfor %}
    {% else %}
      {% if card %}
        <div class="card">
          <h2>Palabra en Noruego:</h2>
          <h1>{{ card.norwegian }}</h1>
          <form method="post" action="{{ url_for('answer') }}" autocomplete="off">
              <input type="hidden" name="card_id" value="{{ card.id }}">
              <label for="answer">Traducción al inglés:</label>
              <input type="text" 
                     id="answer" 
                     name="answer" 
                     autofocus 
                     required 
                     placeholder="Escribe la traducción..."
                     autocapitalize="off">
              <button type="submit">Verificar</button>
          </form>
        </div>
      {% else %}
        <div class="card no-cards">
          <h2>¡No hay tarjetas pendientes por ahora!</h2>
          <p style="color: #666;">Vuelve más tarde para continuar practicando.</p>
        </div>
      {% endif %}
    {% endif %}
  {% endwith %}
{% endblock %}
""",
    "stats": """
{% extends "base" %}
{% block content %}
    <div class="stats-header">
        <button onclick="window.location.href='{{ url_for('index') }}'" class="back-button">
            ← Volver
        </button>
        <h1>Estadísticas Detalladas</h1>
    </div>

    <div class="stats-card">
        <div class="stats-grid">
            <div class="stat-item">
                <div class="stat-value">{{ stats.mastered }}</div>
                <div class="stat-label">Dominadas</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">{{ stats.learning }}</div>
                <div class="stat-label">Aprendiendo</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">{{ stats.new }}</div>
                <div class="stat-label">Nuevas</div>
            </div>
        </div>
        <div class="progress-bar">
            <div class="progress-segment mastered" style="width: {{ stats.mastered_percent }}%">
                <span class="progress-label">{{ stats.mastered_percent }}%</span>
            </div>
            <div class="progress-segment learning" style="width: {{ stats.learning_percent }}%">
                <span class="progress-label">{{ stats.learning_percent }}%</span>
            </div>
        </div>
    </div>

    <div class="words-section">
        <h2>Palabras Dominadas ({{ stats.mastered }})</h2>
        <div class="words-grid">
            {% for card in stats.mastered_cards %}
            <div class="word-card detailed" onclick="showWordDetails('{{ card.norwegian }}', '{{ card.english }}', {{ card.ease }}, {{ card.reps }}, {{ card.fail_count }}, '{{ card.due_date.isoformat() }}')">
                <div class="word-norwegian">{{ card.norwegian }}</div>
                <div class="word-stats">
                    <span>Repeticiones: {{ card.reps }}</span>
                    <span>Facilidad: {{ "%.2f"|format(card.ease) }}</span>
                </div>
            </div>
            {% endfor %}
        </div>

        <h2>Palabras en Aprendizaje ({{ stats.learning }})</h2>
        <div class="words-grid">
            {% for card in stats.learning_cards %}
            <div class="word-card detailed" onclick="showWordDetails('{{ card.norwegian }}', '{{ card.english }}', {{ card.ease }}, {{ card.reps }}, {{ card.fail_count }}, '{{ card.due_date.isoformat() }}')">
                <div class="word-norwegian">{{ card.norwegian }}</div>
                <div class="word-stats">
                    <span>Repeticiones: {{ card.reps }}</span>
                    <span>Facilidad: {{ "%.2f"|format(card.ease) }}</span>
                </div>
            </div>
            {% endfor %}
        </div>

        <h2>Palabras Nuevas ({{ stats.new }})</h2>
        <div class="words-grid">
            {% for card in stats.new_cards %}
            <div class="word-card detailed" onclick="showWordDetails('{{ card.norwegian }}', '{{ card.english }}', {{ card.ease }}, {{ card.reps }}, {{ card.fail_count }}, '{{ card.due_date.isoformat() }}')">
                <div class="word-norwegian">{{ card.norwegian }}</div>
            </div>
            {% endfor %}
        </div>
    </div>
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
        
    # Mejorar la selección de palabras aprendidas y falladas
    learned_cards = sorted(
        [card for card in srs.cards if card.reps > 0],
        key=lambda x: x.reps,
        reverse=True
    )[:10]  # Top 10 palabras más practicadas
    
    failed_cards = sorted(
        [card for card in srs.cards if card.fail_count > 0],
        key=lambda x: x.fail_count,
        reverse=True
    )[:10]  # Top 10 palabras más falladas
    
    # Calcular estadísticas generales
    total_cards = len(srs.cards)
    mastered_cards = len([card for card in srs.cards if card.reps >= 5 and card.ease >= 2.5])
    learning_cards = len([card for card in srs.cards if 0 < card.reps < 5])
    new_cards = len([card for card in srs.cards if card.reps == 0])
    
    stats = {
        "total": total_cards,
        "mastered": mastered_cards,
        "learning": learning_cards,
        "new": new_cards,
        "mastered_percent": round((mastered_cards / total_cards) * 100 if total_cards > 0 else 0, 1),
        "learning_percent": round((learning_cards / total_cards) * 100 if total_cards > 0 else 0, 1)
    }
    
    return render("index", 
                 card=card, 
                 learned_cards=learned_cards, 
                 failed_cards=failed_cards,
                 stats=stats)

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
        flash(f"¡Correcto! '{card.norwegian}' significa '{card.english}'", "correct")
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
            flash(f"Casi correcto. '{card.norwegian}' significa '{card.english}'. Diferencias: {diff_str}", "incorrect")
            quality = 3
        else:
            flash(f"Incorrecto. '{card.norwegian}' significa '{card.english}'. Tu respuesta fue: '{user_answer}'", "incorrect")
            quality = 2

    card.update(quality)
    srs.save_progress()
    
    return redirect(url_for("index"))

@app.route("/stats", endpoint="stats")
def stats_page():
    # Obtener todas las palabras y categorizarlas
    total_cards = len(srs.cards)
    
    mastered_cards = sorted(
        [card for card in srs.cards if card.reps >= 5 and card.ease >= 2.5],
        key=lambda x: x.reps,
        reverse=True
    )
    
    learning_cards = sorted(
        [card for card in srs.cards if 0 < card.reps < 5],
        key=lambda x: x.reps,
        reverse=True
    )
    
    new_cards = sorted(
        [card for card in srs.cards if card.reps == 0],
        key=lambda x: x.norwegian
    )
    
    stats = {
        "total": total_cards,
        "mastered": len(mastered_cards),
        "learning": len(learning_cards),
        "new": len(new_cards),
        "mastered_percent": round((len(mastered_cards) / total_cards) * 100 if total_cards > 0 else 0, 1),
        "learning_percent": round((len(learning_cards) / total_cards) * 100 if total_cards > 0 else 0, 1),
        "mastered_cards": mastered_cards,
        "learning_cards": learning_cards,
        "new_cards": new_cards
    }
    
    return render("stats", stats=stats)

# ---------------------------
# Ejecución de la aplicación
# ---------------------------
if __name__ == "__main__":
    app.run(debug=True)
