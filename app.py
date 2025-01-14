from flask import Flask, render_template, request, jsonify
import subprocess
import tempfile
import os
from langchain.llms import Ollama
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain.memory import ConversationBufferMemory
from datetime import datetime
import json
from typing import Dict, List
import sqlite3
from contextlib import contextmanager

app = Flask(__name__)

# Database configuration
DATABASE_PATH = 'chat_database.db'

# Initialize LangChain with Ollama LLM
llm = Ollama(model="llama2")


@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_db_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                title TEXT,
                date TEXT,
                last_message TEXT
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT,
                role TEXT,
                content TEXT,
                timestamp TEXT,
                FOREIGN KEY (chat_id) REFERENCES chats (id)
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS important_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT,
                content TEXT,
                FOREIGN KEY (chat_id) REFERENCES chats (id)
            )
        ''')
        conn.commit()


# Initialize database on startup
init_db()


class ChatSession:
    def __init__(self, session_id):
        self.session_id = session_id
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )
        self._load_chat_history()
        self._load_important_info()

    def _load_chat_history(self):
        """Load chat history from database"""
        with get_db_connection() as conn:
            messages = conn.execute(
                'SELECT role, content, timestamp FROM messages WHERE chat_id = ? ORDER BY timestamp',
                (self.session_id,)
            ).fetchall()

            self.chat_history = []
            for msg in messages:
                self.chat_history.append({
                    "role": msg['role'],
                    "content": msg['content'],
                    "timestamp": msg['timestamp']
                })
                if msg['role'] == "user":
                    self.memory.chat_memory.add_user_message(msg['content'])
                else:
                    self.memory.chat_memory.add_ai_message(msg['content'])

    def _load_important_info(self):
        """Load important info from database"""
        with get_db_connection() as conn:
            info = conn.execute(
                'SELECT content FROM important_info WHERE chat_id = ?',
                (self.session_id,)
            ).fetchall()
            self.important_info = [row['content'] for row in info]

    def add_message(self, role, content):
        timestamp = datetime.now().isoformat()
        message = {
            "role": role,
            "content": content,
            "timestamp": timestamp
        }

        # Store in database
        with get_db_connection() as conn:
            conn.execute(
                'INSERT INTO messages (chat_id, role, content, timestamp) VALUES (?, ?, ?, ?)',
                (self.session_id, role, content, timestamp)
            )
            conn.commit()

        self.chat_history.append(message)

        # Update memory
        if role == "user":
            self.memory.chat_memory.add_user_message(content)
        else:
            self.memory.chat_memory.add_ai_message(content)

    def add_important_info(self, content):
        """Add important information to database"""
        with get_db_connection() as conn:
            conn.execute(
                'INSERT INTO important_info (chat_id, content) VALUES (?, ?)',
                (self.session_id, content)
            )
            conn.commit()
        self.important_info.append(content)

    def get_memory_variables(self):
        return self.memory.load_memory_variables({})

    def clear_memory(self):
        """Clear all memory from database"""
        with get_db_connection() as conn:
            conn.execute('DELETE FROM messages WHERE chat_id = ?', (self.session_id,))
            conn.execute('DELETE FROM important_info WHERE chat_id = ?', (self.session_id,))
            conn.commit()

        self.memory.clear()
        self.chat_history = []
        self.important_info = []

    def clear_chat_history(self):
        """Clear chat history from database"""
        with get_db_connection() as conn:
            conn.execute('DELETE FROM messages WHERE chat_id = ?', (self.session_id,))
            conn.commit()

        self.chat_history = []
        self.memory.chat_memory.clear()

    def clear_important_info(self):
        """Clear important info from database"""
        with get_db_connection() as conn:
            conn.execute('DELETE FROM important_info WHERE chat_id = ?', (self.session_id,))
            conn.commit()

        self.important_info = []


# Rest of the prompt template and other configurations remain the same
prompt_template = """
You are a helpful code assistant with memory of our conversation. 

Important Information from our conversation:
{important_info}

Chat History:
{chat_history}

Current request:
{user_request}
- If user asks multiple concepts or if you need to generate a very long code with separate use cases, you may give multiple code snippets separately and explanation for each snippet.
- If code is necessary, the response should include raw code with backticks (```python) for code blocks.
- Inline code should be in backticks.
- Return raw text without HTML formatting.
- If you identify any important information that should be remembered (like user preferences, project requirements, or technical constraints), start that line with [IMPORTANT] in your response.
"""

prompt = PromptTemplate(
    input_variables=["user_request", "chat_history", "important_info"],
    template=prompt_template
)
llm_chain = LLMChain(llm=llm, prompt=prompt)


def convert_to_html(raw_text):
    try:
        with tempfile.NamedTemporaryFile(delete=False, mode="w", suffix=".txt") as temp_input:
            temp_input.write(raw_text)
            temp_input_path = temp_input.name

        with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as temp_output:
            temp_output_path = temp_output.name

        result = subprocess.run(["pandoc", temp_input_path, "-o", temp_output_path], capture_output=True, text=True)

        if result.returncode == 0:
            with open(temp_output_path, "r") as f:
                html_content = f.read()
        else:
            html_content = f"Error: {result.stderr}"

    finally:
        # Clean up temporary files
        if os.path.exists(temp_input_path):
            os.remove(temp_input_path)
        if os.path.exists(temp_output_path):
            os.remove(temp_output_path)

    return html_content

def extract_important_info(response):
    important_items = []
    for line in response.split('\n'):
        if '[IMPORTANT]' in line:
            important_items.append(line.replace('[IMPORTANT]', '').strip())
    return important_items

def create_new_chat(session_id: str):
    """Create a new chat session with metadata in database"""
    with get_db_connection() as conn:
        conn.execute(
            'INSERT INTO chats (id, title, date, last_message) VALUES (?, ?, ?, ?)',
            (session_id, "New Chat", datetime.now().isoformat(), None)
        )
        conn.commit()

    return {
        "id": session_id,
        "title": "New Chat",
        "date": datetime.now().isoformat(),
        "last_message": None
    }


def update_chat_metadata(session_id: str, last_message: str):
    """Update chat metadata in database"""
    title = last_message[:30] + "..." if len(last_message) > 30 else last_message
    with get_db_connection() as conn:
        conn.execute(
            'UPDATE chats SET title = ?, last_message = ? WHERE id = ?',
            (title, last_message, session_id)
        )
        conn.commit()


@app.route("/api/chat-list", methods=["GET"])
def get_chat_list():
    """Get list of all chats from database"""
    with get_db_connection() as conn:
        chats = conn.execute('SELECT * FROM chats ORDER BY date DESC').fetchall()
        return jsonify({
            "chats": [dict(chat) for chat in chats]
        })


# The rest of your route handlers (convert_to_html, extract_important_info, etc.) remain the same

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json
    user_input = data.get("message", "")
    session_id = data.get("sessionId", "default")

    # Get or create session
    session = ChatSession(session_id)

    try:
        # Add user message
        session.add_message("user", user_input)
        update_chat_metadata(session_id, user_input)

        # Get memory variables
        memory_vars = session.get_memory_variables()

        # Generate response
        raw_response = llm_chain.run(
            user_request=user_input,
            chat_history=memory_vars.get("chat_history", ""),
            important_info="\n".join(session.important_info)
        )

        # Extract and store important information
        new_important_info = extract_important_info(raw_response)
        for info in new_important_info:
            session.add_important_info(info)

        # Convert to HTML
        formatted_response = convert_to_html(raw_response)

        # Add assistant response
        session.add_message("assistant", raw_response)

        return jsonify({
            "response": formatted_response,
            "success": True,
            "important_info": session.important_info
        })

    except Exception as e:
        return jsonify({
            "response": f"An error occurred: {str(e)}",
            "success": False
        })


@app.route("/api/new-chat", methods=["POST"])
def new_chat():
    """Create a new chat session"""
    session_id = str(datetime.now().timestamp())
    chat = create_new_chat(session_id)
    return jsonify({"success": True, "chat": chat})


@app.route("/api/chat-history", methods=["GET"])
def get_chat_history():
    """Get chat history for a specific session"""
    session_id = request.args.get("sessionId", "default")

    with get_db_connection() as conn:
        # Get messages
        messages = conn.execute(
            'SELECT role, content, timestamp FROM messages WHERE chat_id = ? ORDER BY timestamp',
            (session_id,)
        ).fetchall()

        # Get important info
        important_info = conn.execute(
            'SELECT content FROM important_info WHERE chat_id = ?',
            (session_id,)
        ).fetchall()

        return jsonify({
            "history": [dict(msg) for msg in messages],
            "important_info": [info['content'] for info in important_info]
        })


@app.route("/api/clear-memory", methods=["POST"])
def clear_memory():
    """Clear memory based on specified option"""
    session_id = request.json.get("sessionId", "default")
    clear_option = request.json.get("clearOption", "all")

    with get_db_connection() as conn:
        try:
            if clear_option == "all":
                conn.execute('DELETE FROM messages WHERE chat_id = ?', (session_id,))
                conn.execute('DELETE FROM important_info WHERE chat_id = ?', (session_id,))
                message = "All memory cleared successfully"
            elif clear_option == "chat":
                conn.execute('DELETE FROM messages WHERE chat_id = ?', (session_id,))
                message = "Chat history cleared successfully"
            elif clear_option == "important":
                conn.execute('DELETE FROM important_info WHERE chat_id = ?', (session_id,))
                message = "Important information cleared successfully"
            else:
                return jsonify({
                    "success": False,
                    "message": "Invalid clear option specified"
                })

            conn.commit()
            return jsonify({
                "success": True,
                "message": message
            })

        except Exception as e:
            return jsonify({
                "success": False,
                "message": f"Error clearing memory: {str(e)}"
            })


@app.route("/api/test-code", methods=["POST"])
def test_code():
    try:
        data = request.json
        code = data.get("code", "")

        # Create a temporary file to store the code
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(code)
            temp_file = f.name

        try:
            # Run the code using Node.js
            result = subprocess.run(
                ['node', temp_file],
                capture_output=True,
                text=True,
                timeout=5  # 5 second timeout for safety
            )

            # Prepare the response
            success = result.returncode == 0
            output = result.stdout if success else result.stderr

            return jsonify({
                "success": success,
                "output": output
            })

        finally:
            # Clean up the temporary file
            os.unlink(temp_file)

    except Exception as e:
        return jsonify({
            "success": False,
            "output": f"Error executing code: {str(e)}"
        })


@app.route("/")
def home():
    """Serve the main application page"""
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)