import os
import sqlite3
import base64
import re
import json
import math
import ast
from datetime import datetime, timedelta
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, redirect, session, url_for
from authlib.integrations.flask_client import OAuth
from groq import Groq
from markitdown import MarkItDown

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'tutor-lamp-development-key')

oauth = OAuth(app)
google_client_id = os.environ.get('GOOGLE_CLIENT_ID')
google_client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
if google_client_id and google_client_secret:
    oauth.register(
        name='google',
        client_id=google_client_id,
        client_secret=google_client_secret,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'}
    )

# Initialize Groq client and MarkItDown engine
GROQ_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_KEY) if GROQ_KEY else None
md_converter = MarkItDown()

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize SQLite Database
DB_NAME = "tutor_lamp.db"
VOICE_CONTEXT = {
    "last_person": None,
    "last_place": None,
    "last_topic": None,
}


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS focus_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL,
            is_focused INTEGER NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_date TEXT NOT NULL UNIQUE,
            focused_count INTEGER NOT NULL,
            distracted_count INTEGER NOT NULL,
            total_checks INTEGER NOT NULL,
            focus_rate REAL NOT NULL,
            focus_streak INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()


def get_date_string(value=None):
    if value is None:
        value = datetime.now()
    return value.strftime('%Y-%m-%d')


def calculate_focus_summary_from_rows(rows):
    total_checks = len(rows)
    focused_count = sum(1 for r in rows if r[0] == 1)
    distracted_count = total_checks - focused_count
    focus_rate = round((focused_count / total_checks) * 100, 1) if total_checks else 0

    focus_streak = 0
    for is_focused in rows:
        if is_focused[0] == 1:
            focus_streak += 1
        else:
            break

    return {
        'total_checks': total_checks,
        'focused_count': focused_count,
        'distracted_count': distracted_count,
        'focus_rate': focus_rate,
        'focus_streak': focus_streak
    }


def archive_closed_sessions(cursor):
    cursor.execute("SELECT DISTINCT DATE(timestamp) AS session_day FROM focus_logs ORDER BY session_day ASC")
    session_days = [row[0] for row in cursor.fetchall()]
    today = get_date_string()

    for session_day in session_days:
        if session_day == today:
            continue

        cursor.execute("SELECT is_focused FROM focus_logs WHERE DATE(timestamp) = ? ORDER BY id ASC", (session_day,))
        rows = cursor.fetchall()
        summary = calculate_focus_summary_from_rows(rows)

        cursor.execute(
            '''
            INSERT INTO daily_sessions (session_date, focused_count, distracted_count, total_checks, focus_rate, focus_streak)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_date)
            DO UPDATE SET focused_count=excluded.focused_count,
                          distracted_count=excluded.distracted_count,
                          total_checks=excluded.total_checks,
                          focus_rate=excluded.focus_rate,
                          focus_streak=excluded.focus_streak,
                          created_at=CURRENT_TIMESTAMP
            ''',
            (session_day, summary['focused_count'], summary['distracted_count'], summary['total_checks'], summary['focus_rate'], summary['focus_streak'])
        )
        cursor.execute("DELETE FROM focus_logs WHERE DATE(timestamp) = ?", (session_day,))


def normalize_query(query):
    if query is None:
        return ""
    cleaned = str(query).strip().lower()
    cleaned = cleaned.replace("’", "'").replace("“", '"').replace("”", '"')
    cleaned = re.sub(r"[^a-z0-9\s+\-*/%=.,:!?_'\"]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def log_voice_event(message):
    print(message)


def resolve_pronouns(query):
    resolved = query
    last_person = VOICE_CONTEXT.get("last_person")
    if last_person:
        for pronoun in [" he ", " him ", " his ", " she ", " her ", " they ", " them ", " their "]:
            if pronoun in resolved:
                resolved = resolved.replace(pronoun, f" {last_person} ")
    return re.sub(r"\s+", " ", resolved).strip()


def get_timezone_for_location(location_name):
    location_name = (location_name or "").strip().lower()
    if not location_name:
        return None

    city_map = {
        "london": "Europe/London",
        "new york": "America/New_York",
        "new york city": "America/New_York",
        "mumbai": "Asia/Kolkata",
        "delhi": "Asia/Kolkata",
        "kolkata": "Asia/Kolkata",
        "pune": "Asia/Kolkata",
        "paris": "Europe/Paris",
        "dubai": "Asia/Dubai",
        "tokyo": "Asia/Tokyo",
        "sydney": "Australia/Sydney",
        "berlin": "Europe/Berlin",
        "frankfurt": "Europe/Berlin",
        "toronto": "America/Toronto",
        "los angeles": "America/Los_Angeles",
        "dubai": "Asia/Dubai",
        "bangalore": "Asia/Kolkata",
        "india": "Asia/Kolkata",
        "united states": "America/New_York",
        "usa": "America/New_York",
        "uk": "Europe/London",
        "canada": "America/Toronto",
    }
    tz_name = city_map.get(location_name)
    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            return None
    for candidate in [location_name, location_name.replace(' ', '_')]:
        try:
            return ZoneInfo(candidate)
        except Exception:
            continue
    return None


def get_current_time_for_location(location_name=None):
    tz = get_timezone_for_location(location_name) if location_name else None
    now = datetime.now(tz) if tz else datetime.now()
    return now.strftime('%I:%M %p')


def get_current_date_for_offset(offset_days=0):
    day = datetime.now() + timedelta(days=offset_days)
    return day.date()


def safe_math_eval(expression):
    expression = str(expression).strip()
    if not expression:
        return None

    try:
        node = ast.parse(expression, mode='eval')
    except SyntaxError:
        return None

    def _eval(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            ops = {
                ast.Add: lambda a, b: a + b,
                ast.Sub: lambda a, b: a - b,
                ast.Mult: lambda a, b: a * b,
                ast.Div: lambda a, b: a / b,
                ast.FloorDiv: lambda a, b: a // b,
                ast.Mod: lambda a, b: a % b,
                ast.Pow: lambda a, b: a ** b,
            }
            op_type = type(node.op)
            if op_type not in ops:
                raise ValueError(f"Unsupported operator: {op_type.__name__}")
            return ops[op_type](left, right)
        if isinstance(node, ast.UnaryOp):
            value = _eval(node.operand)
            if isinstance(node.op, ast.UAdd):
                return +value
            if isinstance(node.op, ast.USub):
                return -value
            raise ValueError("Unsupported unary operator")
        if isinstance(node, ast.Name):
            if node.id == "pi":
                return math.pi
            if node.id == "e":
                return math.e
            raise ValueError(f"Unknown symbol: {node.id}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Only direct function calls are supported")
            func_name = node.func.id
            if func_name == "sqrt":
                if len(node.args) != 1:
                    raise ValueError("sqrt expects one argument")
                return math.sqrt(_eval(node.args[0]))
            if func_name == "cbrt":
                if len(node.args) != 1:
                    raise ValueError("cbrt expects one argument")
                return _eval(node.args[0]) ** (1/3)
            raise ValueError(f"Unsupported function: {func_name}")
        raise ValueError(f"Unsupported expression type: {type(node).__name__}")

    return _eval(node.body)


def extract_math_expression(query):
    q = normalize_query(query)
    q = q.replace("what is", "")
    q = q.replace("what's", "")
    q = q.replace("calculate", "")
    q = q.replace("compute", "")
    q = q.replace("determine", "")
    q = q.replace("find", "")
    q = re.sub(r"\?+$", "", q)
    q = q.strip()

    percent_match = re.search(r"([-+]?\d*\.?\d+)\s*percent\s*of\s*([-+]?\d*\.?\d+)", q)
    if percent_match:
        return {
            "type": "percent_of",
            "value": float(percent_match.group(1)),
            "total": float(percent_match.group(2)),
        }

    square_root_match = re.search(r"square root of\s*([-+]?\d*\.?\d+)", q)
    if square_root_match:
        return {"type": "sqrt", "value": float(square_root_match.group(1))}

    cube_root_match = re.search(r"cube root of\s*([-+]?\d*\.?\d+)", q)
    if cube_root_match:
        return {"type": "cbrt", "value": float(cube_root_match.group(1))}

    power_match = re.search(r"([-+]?\d*\.?\d+)\s*(?:to the power of|power)\s*([-+]?\d*\.?\d+)", q)
    if power_match:
        return {"type": "power", "base": float(power_match.group(1)), "exp": float(power_match.group(2))}

    q = q.replace(" squared", "**2")
    q = q.replace(" cubed", "**3")
    q = q.replace(" plus ", " + ")
    q = q.replace(" minus ", " - ")
    q = q.replace(" times ", " * ")
    q = q.replace(" multiplied by ", " * ")
    q = q.replace(" divided by ", " / ")
    q = q.replace(" divided by ", " / ")
    q = q.replace(" percent ", " % ")
    q = q.replace(" to the power of ", " ** ")
    q = q.replace(" power ", " ** ")
    q = re.sub(r"\s+", " ", q).strip()
    return {"type": "expression", "value": q}


def handle_math_query(query):
    q = normalize_query(query)
    math_info = extract_math_expression(q)
    if not math_info:
        return None

    if math_info["type"] == "percent_of":
        result = (math_info["value"] / 100) * math_info["total"]
        return f"{math_info['value']} percent of {math_info['total']} is {result}."

    if math_info["type"] == "sqrt":
        result = math.sqrt(math_info["value"])
        return f"The square root of {math_info['value']} is {result}."

    if math_info["type"] == "cbrt":
        result = math_info["value"] ** (1 / 3)
        return f"The cube root of {math_info['value']} is {result}."

    if math_info["type"] == "power":
        result = math_info["base"] ** math_info["exp"]
        return f"{math_info['base']} to the power of {math_info['exp']} is {result}."

    expression = math_info["value"]
    if not expression:
        return None
    result = safe_math_eval(expression)
    if result is None:
        return None
    return f"{expression} equals {result}."


def is_time_query(query):
    q = normalize_query(query)
    patterns = [
        r"what time", r"current time", r"time is it", r"time right now",
        r"what's the time", r"what is the time", r"tell me the time",
        r"current time in"
    ]
    return any(re.search(pattern, q) for pattern in patterns)


def is_date_query(query):
    q = normalize_query(query)
    patterns = [
        r"today's date", r"today date", r"what day is today", r"what day is it today",
        r"what is tomorrow's date", r"what day will it be tomorrow", r"days until",
        r"when is monday", r"what day is tomorrow", r"date tomorrow"
    ]
    return any(re.search(pattern, q) for pattern in patterns)


def is_math_query(query):
    q = normalize_query(query)
    if re.search(r"\d+\s*(?:\+|\-|\*|/|%|\^|plus|minus|times|multiplied by|divided by|percent|squared|cubed)\s*\d+", q):
        return True
    if any(keyword in q for keyword in ["plus", "minus", "times", "multiplied by", "divided by", "percent", "square root", "cube root", "squared", "cubed", "power"]):
        return True
    if re.search(r"\d+\s*[+\-*/]\s*\d+", q):
        return True
    return False


def is_definition_query(query):
    q = normalize_query(query)
    patterns = [
        r"what does .* mean", r"what is the meaning of", r"define ",
        r"definition of", r"meaning of", r"what does this word mean"
    ]
    return any(re.search(pattern, q) for pattern in patterns)


def is_person_query(query):
    q = normalize_query(query)
    patterns = [
        r"who is ", r"who was ", r"who are ", r"who founded ", r"who created ",
        r"who invented ", r"who is the ceo of ", r"who is the president of ",
        r"who is the founder of ", r"who owns ", r"who leads ", r"who is the current ceo of "
    ]
    return any(re.search(pattern, q) for pattern in patterns)


def is_weather_query(query):
    q = normalize_query(query)
    patterns = [
        r"weather", r"temperature", r"rain today", r"rain tomorrow", r"sunny",
        r"will it rain", r"forecast", r"weather in"
    ]
    return any(re.search(pattern, q) for pattern in patterns)


def is_news_query(query):
    q = normalize_query(query)
    patterns = [
        r"latest news", r"headlines", r"what's happening", r"what happened today",
        r"today's news", r"recent news", r"latest .* news", r"breaking news",
        r"current affairs", r"major headlines"
    ]
    return any(re.search(pattern, q) for pattern in patterns)


def is_current_query(query):
    q = normalize_query(query)
    current_terms = [
        "today", "now", "currently", "latest", "recent", "this week", "this month",
        "right now", "current", "yesterday", "tomorrow", "2026", "2025", "2024"
    ]
    return any(term in q for term in current_terms)


def is_place_query(query):
    q = normalize_query(query)
    patterns = [
        r"where is ", r"where are ", r"best restaurants in ", r"hotels near ",
        r"places to visit in ", r"things to do in ", r"nearest hospital",
        r"nearby ", r"location of ", r"map of ", r"directions to "
    ]
    return any(re.search(pattern, q) for pattern in patterns)


def is_sports_query(query):
    q = normalize_query(query)
    patterns = [
        r"score", r"match", r"fixture", r"league", r"tournament", r"team standings",
        r"player stats", r"upcoming match", r"who won", r"india cricket", r"football", r"cricket"
    ]
    return any(re.search(pattern, q) for pattern in patterns)


def is_currency_query(query):
    q = normalize_query(query)
    patterns = [
        r"usd to inr", r"dollar to rupee", r"rupees", r"exchange rate", r"bitcoin price",
        r"current price of", r"stock price", r"gold price", r"crypto price", r"nifty"
    ]
    return any(re.search(pattern, q) for pattern in patterns)


def is_conversion_query(query):
    q = normalize_query(query)
    patterns = [
        r"convert ", r"how many .* in ", r"kilometers to miles", r"fahrenheit to celsius",
        r"grams are in", r"liters are in", r"feet to centimeters", r"kilograms to grams"
    ]
    return any(re.search(pattern, q) for pattern in patterns)


def is_searchable_query(query):
    q = normalize_query(query)
    patterns = [
        r"what is the capital of ", r"what is the population of ", r"how many countries",
        r"what is the tallest ", r"when was ", r"who invented ", r"where is the ",
        r"how tall is ", r"how deep is ", r"which country has the largest ",
        r"what is the largest ", r"what is the population of ", r"what is the longest ",
        r"how old is ", r"when did ", r"who founded ", r"what country ", r"how many people "
    ]
    return any(re.search(pattern, q) for pattern in patterns)


def is_general_ai_query(query):
    q = normalize_query(query)
    patterns = [
        r"write an email", r"help me write", r"summarize this", r"compare ", r"analyze ",
        r"give me ideas", r"brainstorm", r"study plan", r"roleplay", r"explain .* simply",
        r"why do people", r"why might", r"help me", r"tell me a story", r"create a ",
        r"explain this concept", r"analyze these", r"debug this", r"write a python function"
    ]
    return any(re.search(pattern, q) for pattern in patterns)


def search_web(query):
    if not query or not str(query).strip():
        return None

    safe_query = quote_plus(str(query).strip())
    url = f"https://api.duckduckgo.com/?q={safe_query}&format=json&no_redirect=1&no_html=1&skip_disambig=1"
    try:
        request = Request(url, headers={"User-Agent": "TutorLamp/1.0"})
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode('utf-8', errors='replace'))
    except Exception:
        return None

    answer = payload.get('AbstractText') or payload.get('Answer') or payload.get('Heading')
    if answer:
        return re.sub(r"\s+", " ", answer).strip()

    related_topics = payload.get('RelatedTopics') or []
    entries = []
    for item in related_topics:
        if isinstance(item, dict):
            text = item.get('Text')
            if text:
                entries.append(text)
        elif isinstance(item, str):
            entries.append(item)
    if entries:
        combined = " ".join(entries[:3])
        return re.sub(r"\s+", " ", combined).strip()[:500]

    return None


def process_search_results(search_result):
    if not search_result:
        return "I couldn't find a reliable result for that question right now."
    cleaned = re.sub(r"https?://\S+", "", search_result)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.replace("..", ".")
    if len(cleaned) > 450:
        cleaned = cleaned[:447].rstrip() + "..."
    return cleaned


def ask_groq(query, system_prompt=None):
    if not query or not str(query).strip():
        return "I did not catch that. Please say it again."

    if client is None:
        return "The AI assistant is not configured yet. Add a valid GROQ_API_KEY in the environment or .env file."

    messages = [{
        "role": "system",
        "content": system_prompt or "You are Tutor Lamp, a helpful AI tutor. Keep responses concise, clear, and useful."
    }, {
        "role": "user",
        "content": str(query).strip()
    }]

    try:
        completion = client.chat.completions.create(
            messages=messages,
            model="openai/gpt-oss-20b",
            temperature=0.7,
            max_tokens=250,
        )
        return completion.choices[0].message.content
    except Exception as exc:
        return f"I couldn't reach the AI assistant right now. {exc}"


def handle_time_query(query):
    q = normalize_query(query)
    location_match = re.search(r"in\s+([a-zA-Z ]+)$|in\s+([a-zA-Z ]+?)\??$", q)
    location = None
    if location_match:
        location = location_match.group(1) or location_match.group(2)
        location = location.replace("in ", "").strip()
    if location:
        return f"The current time in {location.title()} is {get_current_time_for_location(location)}."
    return f"The current time is {get_current_time_for_location()}."


def handle_date_query(query):
    q = normalize_query(query)
    if "tomorrow" in q:
        target = get_current_date_for_offset(1)
        return f"Tomorrow's date is {target.strftime('%A, %B %d, %Y')}."
    if "today" in q or "what day is today" in q or "what day is it today" in q:
        current = datetime.now().date()
        return f"Today is {current.strftime('%A, %B %d, %Y')}."
    if "days until" in q:
        match = re.search(r"days until\s+([a-z]+)", q)
        if match:
            target_day = match.group(1).capitalize()
            days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            day_index = days.index(target_day.lower()) if target_day.lower() in days else None
            if day_index is not None:
                today_index = datetime.now().weekday()
                current_day = today_index
                target_offset = (day_index - current_day) % 7
                if target_offset == 0:
                    target_offset = 7
                return f"There are {target_offset} days until {target_day.title()}."
    return f"Today's date is {datetime.now().strftime('%A, %B %d, %Y')}."


def detect_intent(query):
    q = normalize_query(query)
    if not q:
        return "empty"

    if is_time_query(q):
        return "time"
    if is_date_query(q):
        return "date"
    if is_math_query(q):
        return "mathematics"
    if is_definition_query(q):
        return "definition"
    if is_person_query(q):
        return "person"
    if is_weather_query(q):
        return "weather"
    if is_news_query(q):
        return "news"
    if is_current_query(q):
        return "current_information"
    if is_place_query(q):
        return "place"
    if is_sports_query(q):
        return "sports"
    if is_currency_query(q):
        return "currency"
    if is_conversion_query(q):
        return "conversion"
    if is_searchable_query(q):
        return "searchable_factual"
    if is_general_ai_query(q):
        return "reasoning"
    return "general"


def can_answer_without_live_data(query):
    q = normalize_query(query)
    if is_definition_query(q):
        return True
    if is_person_query(q):
        return True
    if is_searchable_query(q):
        return True
    if is_general_ai_query(q):
        return True
    return False


def process_voice_query(query):
    if query is None or not str(query).strip():
        return "I did not catch that. Please say the question again."

    original_query = str(query).strip()
    normalized = normalize_query(original_query)
    resolved_query = resolve_pronouns(normalized)
    intent = detect_intent(resolved_query)

    log_voice_event(f"[VOICE] Query: \"{original_query}\"")
    log_voice_event(f"[VOICE] Intent: {intent}")

    if intent == "time":
        log_voice_event("[VOICE] Handler: time")
        log_voice_event("[VOICE] AI Used: false")
        return handle_time_query(original_query)
    if intent == "date":
        log_voice_event("[VOICE] Handler: date")
        log_voice_event("[VOICE] AI Used: false")
        return handle_date_query(original_query)
    if intent == "mathematics":
        log_voice_event("[VOICE] Handler: math")
        log_voice_event("[VOICE] AI Used: false")
        answer = handle_math_query(original_query)
        if answer:
            return answer
    if intent in {"definition", "person", "weather", "news", "current_information", "place", "sports", "currency", "searchable_factual"}:
        log_voice_event("[VOICE] Handler: web_search")
        log_voice_event("[VOICE] AI Used: false")
        search_result = search_web(original_query)
        if search_result:
            return process_search_results(search_result)

        if can_answer_without_live_data(original_query):
            log_voice_event("[VOICE] Handler: groq_fallback")
            log_voice_event("[VOICE] AI Used: true")
            return ask_groq(original_query)

        return "I couldn’t verify that information online right now."
    if intent == "conversion":
        log_voice_event("[VOICE] Handler: conversion")
        log_voice_event("[VOICE] AI Used: false")
        if "fahrenheit" in normalized and "celsius" in normalized:
            match = re.search(r"([-+]?\d*\.?\d+)\s*fahrenheit", normalized)
            if match:
                temp = float(match.group(1))
                celsius = (temp - 32) * 5 / 9
                return f"{temp} degrees Fahrenheit is {celsius:.2f} degrees Celsius."
        if "kilometers" in normalized and "miles" in normalized:
            match = re.search(r"([-+]?\d*\.?\d+)\s*kilometers", normalized)
            if match:
                km = float(match.group(1))
                miles = km * 0.621371
                return f"{km} kilometers is {miles:.2f} miles."
        if "dollars" in normalized and "rupees" in normalized:
            approx_rate = 83.5
            match = re.search(r"([-+]?\d*\.?\d+)\s*dollars", normalized)
            if match:
                amount = float(match.group(1))
                return f"{amount} US dollars is approximately {amount * approx_rate:.2f} rupees at an estimated rate of 83.5 INR per USD."
        return "I can help with that conversion, but I need a specific value and units to calculate it accurately."

    log_voice_event("[VOICE] Handler: groq")
    log_voice_event("[VOICE] AI Used: true")
    return ask_groq(original_query)


def extract_file_content(file_path):
    """Universal document text extractor converting PDF, DOCX, XLSX, PPTX, HTML, etc., to Markdown text."""
    try:
        result = md_converter.convert(file_path)
        extracted_text = result.text_content.strip()

        if not extracted_text:
            return "[Note: File uploaded successfully, but no readable text content could be extracted.]"

        return extracted_text[:4000]  # Cap prompt token length
    except Exception as e:
        return f"[Error processing file '{os.path.basename(file_path)}': {str(e)}]"

@app.route('/')
def landing():
    return render_template('landing.html')

@app.route('/login')
def login():
    return render_template('login.html', google_enabled=bool(google_client_id and google_client_secret))

@app.route('/login/google')
def google_login():
    if not google_client_id or not google_client_secret:
        return render_template('login.html', google_enabled=False, error='Google sign-in is not configured yet.'), 503
    redirect_uri = os.environ.get('GOOGLE_REDIRECT_URI') or url_for('google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@app.route('/auth/google/callback')
def google_callback():
    if not google_client_id or not google_client_secret:
        return redirect(url_for('login'))
    token = oauth.google.authorize_access_token()
    user_info = token.get('userinfo')
    if user_info:
        session['user'] = {
            'name': user_info.get('name', 'Google user'),
            'email': user_info.get('email', ''),
            'picture': user_info.get('picture', '')
        }
    return redirect(url_for('index'))

@app.route('/app', strict_slashes=False)
@app.route('/app/', strict_slashes=False)
@app.route('/workspace', strict_slashes=False)
@app.route('/workspace/', strict_slashes=False)
def index():
    return render_template('index.html')

@app.route('/chatbot')
def chatbot():
    return render_template('chatbot.html')

@app.route('/analytics')
def analytics():
    return render_template('analytics.html')

@app.route('/ask', methods=['POST'])
def ask():
    user_query = request.form.get('query', '')
    uploaded_file = request.files.get('file')

    if not user_query and not uploaded_file:
        return jsonify({'response': 'Please provide a prompt or attach a document.'}), 400

    if user_query and not uploaded_file:
        routed_answer = process_voice_query(user_query)
        if routed_answer and routed_answer != "I did not catch that. Please say the question again.":
            # Preserve the previous tutoring experience for file-less prompts unless the query is clearly a general AI task.
            if detect_intent(normalize_query(user_query)) not in {"reasoning", "general"}:
                return jsonify({'response': routed_answer})

    try:
        messages = [
            {"role": "system", "content": "You are Tutor Lamp, a helpful AI tutor. Keep responses helpful and concise (1-3 sentences)."}
        ]

        if client is None:
            return jsonify({'response': 'The AI assistant is not configured yet. Add GROQ_API_KEY to the environment or .env file.'}), 503

        # Handle Image Attachments via Groq Vision API
        if uploaded_file and uploaded_file.content_type.startswith('image/'):
            image_bytes = uploaded_file.read()
            base64_image = base64.b64encode(image_bytes).decode('utf-8')

            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": user_query or "Please analyze this homework/note image and provide feedback."},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{uploaded_file.content_type};base64,{base64_image}"
                        }
                    }
                ]
            })

            chat_completion = client.chat.completions.create(
                messages=messages,
                model="llama-3.2-11b-vision-preview",
                temperature=0.7,
                max_tokens=250
            )

        # Handle All Other File Formats (PDF, DOCX, PPTX, XLSX, TXT, CSV, etc.)
        else:
            file_text_content = ""
            if uploaded_file and uploaded_file.filename:
                filepath = os.path.join(UPLOAD_FOLDER, uploaded_file.filename)
                uploaded_file.save(filepath)

                # Extract structured text regardless of original format
                file_text_content = extract_file_content(filepath)

            prompt_content = user_query
            if file_text_content:
                prompt_content += f"\n\nAttached File Content:\n{file_text_content}"

            messages.append({"role": "user", "content": prompt_content})

            chat_completion = client.chat.completions.create(
                messages=messages,
                model="openai/gpt-oss-20b",
                temperature=0.7,
                max_tokens=250
            )

        return jsonify({'response': chat_completion.choices[0].message.content})

    except Exception as e:
        return jsonify({'response': f"AI Processing Error: {str(e)}"}), 500

@app.route('/log_event', methods=['POST'])
def log_event():
    data = request.get_json()
    status = str(data.get('status', 'Unknown')).strip()
    status_lower = status.lower()
    is_focused = 1 if 'focused' in status_lower else 0

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    archive_closed_sessions(cursor)
    cursor.execute("INSERT INTO focus_logs (status, is_focused) VALUES (?, ?)", (status, is_focused))
    conn.commit()
    conn.close()

    return jsonify({'status': 'success'})


@app.route('/save_session', methods=['POST'])
def save_session():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    archive_closed_sessions(cursor)

    cursor.execute("SELECT COUNT(*) FROM focus_logs")
    total_checks = cursor.fetchone()[0]
    if total_checks == 0:
        conn.close()
        return jsonify({'status': 'saved', 'session_date': get_date_string(), 'total_checks': 0})

    cursor.execute("SELECT is_focused FROM focus_logs ORDER BY id ASC")
    rows = cursor.fetchall()
    summary = calculate_focus_summary_from_rows(rows)
    session_date = get_date_string()

    cursor.execute(
        '''
        INSERT INTO daily_sessions (session_date, focused_count, distracted_count, total_checks, focus_rate, focus_streak)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_date)
        DO UPDATE SET focused_count=excluded.focused_count,
                      distracted_count=excluded.distracted_count,
                      total_checks=excluded.total_checks,
                      focus_rate=excluded.focus_rate,
                      focus_streak=excluded.focus_streak,
                      created_at=CURRENT_TIMESTAMP
        ''',
        (session_date, summary['focused_count'], summary['distracted_count'], summary['total_checks'], summary['focus_rate'], summary['focus_streak'])
    )
    cursor.execute("DELETE FROM focus_logs")
    conn.commit()
    conn.close()

    return jsonify({'status': 'saved', 'session_date': session_date, 'summary': summary})


@app.route('/get_session_history', methods=['GET'])
def get_session_history():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT session_date, focused_count, distracted_count, total_checks, focus_rate, focus_streak FROM daily_sessions ORDER BY session_date DESC")
    rows = cursor.fetchall()
    conn.close()

    history = [{
        'date': row[0],
        'focused_count': row[1],
        'distracted_count': row[2],
        'total_checks': row[3],
        'focus_rate': row[4],
        'focus_streak': row[5]
    } for row in rows]

    return jsonify({'history': history})


@app.route('/get_analytics', methods=['GET'])
def get_analytics():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    archive_closed_sessions(cursor)
    today = get_date_string()

    cursor.execute("SELECT COUNT(*) FROM focus_logs WHERE DATE(timestamp) = ? AND is_focused = 1", (today,))
    focused_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM focus_logs WHERE DATE(timestamp) = ? AND is_focused = 0", (today,))
    distracted_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM focus_logs WHERE DATE(timestamp) = ?", (today,))
    total_checks = cursor.fetchone()[0]

    cursor.execute("SELECT status, is_focused FROM focus_logs WHERE DATE(timestamp) = ? ORDER BY id DESC LIMIT 50", (today,))
    recent_rows = cursor.fetchall()
    latest_status = recent_rows[0][0] if recent_rows else 'No data'

    status_counts = {}
    cursor.execute("SELECT status, COUNT(*) FROM focus_logs WHERE DATE(timestamp) = ? GROUP BY status ORDER BY COUNT(*) DESC", (today,))
    for status, count in cursor.fetchall():
        status_counts[status] = count

    cursor.execute("SELECT strftime('%H:%M:%S', timestamp), is_focused FROM focus_logs WHERE DATE(timestamp) = ? ORDER BY id DESC LIMIT 20", (today,))
    logs = cursor.fetchall()[::-1]

    cursor.execute("SELECT is_focused FROM focus_logs WHERE DATE(timestamp) = ? ORDER BY id DESC LIMIT 50", (today,))
    recent_statuses = [row[0] for row in cursor.fetchall()]
    focus_streak = 0
    for status in recent_statuses:
        if status == 1:
            focus_streak += 1
        else:
            break

    hourly = []
    cursor.execute("SELECT strftime('%H', timestamp) AS hour, SUM(CASE WHEN is_focused = 1 THEN 1 ELSE 0 END) AS focused, SUM(CASE WHEN is_focused = 0 THEN 1 ELSE 0 END) AS distracted FROM focus_logs WHERE DATE(timestamp) = ? GROUP BY strftime('%H', timestamp) ORDER BY hour ASC", (today,))
    for hour, focused, distracted in cursor.fetchall():
        hourly.append({
            'label': f"{int(hour):02d}:00",
            'focused': focused,
            'distracted': distracted
        })

    conn.commit()
    conn.close()

    labels = [row[0] for row in logs]
    scores = [100 if row[1] == 1 else 0 for row in logs]
    focus_rate = round((focused_count / total_checks) * 100, 1) if total_checks else 0

    return jsonify({
        'focused_count': focused_count,
        'distracted_count': distracted_count,
        'total_checks': total_checks,
        'focus_rate': focus_rate,
        'focus_streak': focus_streak,
        'latest_status': latest_status,
        'status_counts': status_counts,
        'labels': labels,
        'scores': scores,
        'hourly': hourly
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)