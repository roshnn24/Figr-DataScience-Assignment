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
import re
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'py'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
# Database configuration
DATABASE_PATH = 'chat_database.db'

# Initialize LangChain with Ollama LLM
llm = Ollama(model="mistral:7b")


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
Role: You are Figr Code Assistant, specializing in providing clear, error-free Python code solutions.

Context:
{important_info}

Previous Conversation:
{chat_history}

Current Request:
{user_request}

Output Guidelines:
1. Code Format:
   - Use ```python for code blocks
   - Use `code` for inline code references
   - Provide raw text without HTML formatting

2. Code Organization:
   - Default to single, focused code snippets for clarity
   - Only split into multiple snippets(each individually runnable) if:
     a) Multiple distinct concepts are requested
     b) Complex functionality requires modular explanation
     
   - Mark critical information with [IMPORTANT] prefix and give small explanations with some bold headings if required and in white font always.
"""

prompt = PromptTemplate(
    input_variables=["user_request", "chat_history", "important_info"],
    template=prompt_template
)
llm_chain = LLMChain(llm=llm, prompt=prompt)


def convert_to_html(raw_text):
    """Convert markdown to HTML while preserving code blocks with custom buttons"""
    try:
        # Create a temporary markdown file
        with tempfile.NamedTemporaryFile(delete=False, mode="w", suffix=".md") as temp_input:
            temp_input.write(raw_text)
            temp_input_path = temp_input.name

        # Use pandoc with specific options to preserve code blocks
        with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as temp_output:
            temp_output_path = temp_output.name

        # Use pandoc with specific options
        cmd = [
            "pandoc",
            temp_input_path,
            "-f", "markdown",
            "-t", "html",
            "--highlight-style=pygments",
            "--no-highlight",  # Disable pandoc's highlighting
            "-o", temp_output_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            with open(temp_output_path, "r") as f:
                html_content = f.read()

            # Add custom buttons to code blocks
            import re
            def replace_code_block(match):
                code_class = match.group(1) or ''
                code_content = match.group(2)
                return f'''
                    <div class="code-block-wrapper">
                        <button class="test-button">Test Code</button>
                        <button class="copy-button">Copy Code</button>
                        <pre><code class="hljs {code_class}">{code_content}</code></pre>
                        <div class="test-results"></div>
                    </div>
                '''

            # Replace <pre><code> blocks with our custom wrapper
            pattern = r'<pre><code class="([^"]*)">(.*?)</code></pre>'
            html_content = re.sub(pattern, replace_code_block, html_content, flags=re.DOTALL)

        else:
            html_content = f"Error: {result.stderr}"

    finally:
        # Clean up temporary files
        if os.path.exists(temp_input_path):
            os.remove(temp_input_path)
        if os.path.exists(temp_output_path):
            os.remove(temp_output_path)

    return html_content


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


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


def format_response(response):
    """Format response with proper code block structure"""
    # First, handle code blocks with language specification
    formatted = re.sub(
        r'```(\w+)\n(.*?)\n```',
        lambda
            m: f'<div class="code-block-wrapper">\n<button class="test-button">Test Code</button>\n<button class="copy-button">Copy Code</button>\n<pre><code class="hljs {m.group(1)}">{m.group(2)}</code></pre>\n<div class="test-results"></div>\n</div>',
        response,
        flags=re.DOTALL
    )

    # Then handle code blocks without language specification
    formatted = re.sub(
        r'```\n(.*?)\n```',
        lambda
            m: f'<div class="code-block-wrapper">\n<button class="test-button">Test Code</button>\n<button class="copy-button">Copy Code</button>\n<pre><code class="hljs">{m.group(1)}</code></pre>\n<div class="test-results"></div>\n</div>',
        formatted,
        flags=re.DOTALL
    )

    # Handle inline code
    formatted = re.sub(
        r'`([^`]+)`',
        r'<code class="inline-code">\1</code>',
        formatted
    )

    return formatted


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

        # Format the response properly with code block structure
        def format_response(response):
            # First, handle code blocks with language specification
            formatted = re.sub(
                r'```(\w+)\n(.*?)\n```',
                lambda
                    m: f'<div class="code-block-wrapper">\n<button class="test-button">Test Code</button>\n<button class="copy-button">Copy Code</button>\n<pre><code class="hljs {m.group(1)}">{m.group(2)}</code></pre>\n<div class="test-results"></div>\n</div>',
                response,
                flags=re.DOTALL
            )

            # Then handle code blocks without language specification
            formatted = re.sub(
                r'```\n(.*?)\n```',
                lambda
                    m: f'<div class="code-block-wrapper">\n<button class="test-button">Test Code</button>\n<button class="copy-button">Copy Code</button>\n<pre><code class="hljs">{m.group(1)}</code></pre>\n<div class="test-results"></div>\n</div>',
                formatted,
                flags=re.DOTALL
            )

            # Handle inline code
            formatted = re.sub(
                r'`([^`]+)`',
                r'<code class="inline-code">\1</code>',
                formatted
            )

            return formatted

        # Format the response
        formatted_response = format_response(raw_response)

        # Store the formatted response
        session.add_message("assistant", formatted_response)

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

        # Format assistant messages if they aren't already formatted
        formatted_messages = []
        for msg in messages:
            message_dict = dict(msg)
            if message_dict['role'] == 'assistant' and '```' in message_dict['content']:
                # Format the response if it contains code blocks
                message_dict['content'] = format_response(message_dict['content'])
            formatted_messages.append(message_dict)

        # Get important info
        important_info = conn.execute(
            'SELECT content FROM important_info WHERE chat_id = ?',
            (session_id,)
        ).fetchall()

        return jsonify({
            "history": formatted_messages,
            "important_info": [info['content'] for info in important_info]
        })


@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file part'})

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No selected file'})

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Read the file content
        with open(filepath, 'r') as f:
            content = f.read()

        # Analyze the code using the LLM
        analysis_prompt = f"""
        Please analyze this Python code:

        {content}

        Provide:
        1. A clear, small explanation
        2. Any potential errors or improvements
        3. Suggestions for better practices
        
        - Each in separate neat paragraphs with highlighted headings.
        """

        analysis = llm.predict(analysis_prompt)

        # Clean up the uploaded file
        os.remove(filepath)

        return jsonify({
            'success': True,
            'filename': filename,
            'content': content,
            'analysis': analysis
        })

    return jsonify({'success': False, 'error': 'Invalid file type'})


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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name

        try:
            # Run the code using Python
            result = subprocess.run(
                ['python', temp_file],
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
