import os
import json
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///quiz.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Обмеження часу очікування відповіді до 10 секунд (10000 мс)
client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options=types.HttpOptions(timeout=10000)
) if GEMINI_API_KEY else None

class QuizResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, default="Денис")
    topic = db.Column(db.String(150), nullable=False)
    difficulty = db.Column(db.String(50), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    total_questions = db.Column(db.Integer, nullable=False)
    percentage = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "topic": self.topic,
            "difficulty": self.difficulty,
            "score": self.score,
            "total": self.total_questions,
            "percentage": round(self.percentage, 1),
            "date": self.created_at.strftime("%Y-%m-%d %H:%M")
        }

with app.app_context():
    db.create_all()
# 1. Оновлений клієнт із таймаутом 20 секунд (20000 мс)
client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options=types.HttpOptions(timeout=20000)
) if GEMINI_API_KEY else None


# 2. Функція з точною рекомендованою моделлю gemini-3.5-flash-lite
def generate_questions_via_ai(topic: str, difficulty: str, count: int = 5):
    print(f"🚀 Звертаємось до Gemini AI для теми: '{topic}' ({difficulty})...")
    
    prompt = f"""
    Ти — експертна система тестування. Згенеруй квіз на тему "{topic}" рівня складності "{difficulty}".
    Кількість питань: {count}.
    
    Вимоги до відповіді: Поверни ТІЛЬКИ строгий JSON масив об'єктів без будь-якого Markdown розмічання.
    Формат об'єкта:
    {{
      "id": 1,
      "question": "Текст питання українською мовою?",
      "options": ["Варіант A", "Варіант B", "Варіант C", "Варіант D"],
      "correct_index": 0,
      "explanation": "Коротке пояснення правильної відповіді (1-2 речення)."
    }}
    """
    
    if not client:
        raise Exception("API-ключ не вказано у файлі .env!")

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )
    
    print("✅ ШІ успішно згенерував унікальні питання!")
    
    raw_text = response.text.strip()
    if raw_text.startswith("```json"):
        raw_text = raw_text[7:]
    if raw_text.startswith("```"):
        raw_text = raw_text[3:]
    if raw_text.endswith("```"):
        raw_text = raw_text[:-3]
        
    return json.loads(raw_text.strip())

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/generate-quiz", methods=["POST"])
def generate_quiz():
    data = request.get_json() or {}
    topic = data.get("topic", "").strip()
    difficulty = data.get("difficulty", "Середній")
    
    if not topic:
        return jsonify({"error": "Вкажіть тему квізу!"}), 400
        
    try:
        questions = generate_questions_via_ai(topic, difficulty)
        return jsonify({"topic": topic, "difficulty": difficulty, "questions": questions})
    except Exception as e:
        print(f"❌ Помилка мережі/ШІ: {e}")
        return jsonify({"error": f"Помилка з'єднання: {str(e)}"}), 500

@app.route("/api/submit-quiz", methods=["POST"])
def submit_quiz():
    data = request.get_json() or {}
    username = data.get("username", "Денис").strip() or "Денис"
    topic = data.get("topic", "Загальна")
    difficulty = data.get("difficulty", "Середній")
    user_answers = data.get("user_answers", {})
    questions = data.get("questions", [])

    score = 0
    feedback = []

    for idx, q in enumerate(questions):
        user_ans = user_answers.get(str(idx))
        correct_ans = q.get("correct_index", 0)
        is_correct = (user_ans is not None and int(user_ans) == correct_ans)
        
        if is_correct:
            score += 1
            
        feedback.append({
            "question_id": q.get("id", idx + 1),
            "question": q.get("question", ""),
            "user_answer": user_ans,
            "correct_answer": correct_ans,
            "is_correct": is_correct,
            "explanation": q.get("explanation", "")
        })

    total = len(questions)
    percentage = (score / total * 100) if total > 0 else 0.0

    result_record = QuizResult(
        username=username,
        topic=topic,
        difficulty=difficulty,
        score=score,
        total_questions=total,
        percentage=percentage
    )
    db.session.add(result_record)
    db.session.commit()

    return jsonify({
        "score": score,
        "total": total,
        "percentage": round(percentage, 1),
        "feedback": feedback,
        "saved_id": result_record.id
    })

@app.route("/api/leaderboard", methods=["GET"])
def leaderboard():
    results = QuizResult.query.order_by(QuizResult.created_at.desc()).limit(10).all()
    return jsonify([r.to_dict() for r in results])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)