# Figr AI Code Assistant (Mistral:7B)
### Full Demo - https://youtu.be/7h_ccEBgkMU?si=N_I5D7dAjXACva95
https://github.com/user-attachments/assets/f250160c-0fa8-47e7-a431-cdb993f93913
## Project Overview
An advanced AI Code Assistant designed to showcase creative coding approaches and efficient implementation of AI-based code analysis, developed as part of an assignment to build a simple coding assistant.

### Objective
To demonstrate the ability to:
1. Understand Python programming requests/questions from a user.
2. Generate Python code solutions or function templates.
3. Test the generated code through execution or simulation.
4. Request additional user input when necessary.

This project highlights practical applications of LLMs for code generation, analysis, and testing while adhering to clear design principles and assumptions.

---

## Key Features 🌟

### Core Functionality
- **Intelligent Code Analysis**: Contextually processes Python code queries.
- **Real-time Code Generation**: Produces Python code solutions and function templates.
- **Code Testing**: Executes or simulates tests for generated code snippets.
- **Interactive Input Handling**: Requests additional details when needed for clarity.
- **File Upload Analysis**: Evaluates uploaded `.py` files for errors and potential improvements.
- **Persistent Chat History**: Stores conversation context using SQLite for session continuity.

### Creativity in Design
This assistant integrates:
- Running its generated code in backend and producing output.
- Retry mechanisms for failed responses with user-friendly feedback.
- .py file upload and interpretation from it.


---

## Technical Implementation 💻

### Frontend
- HTML5 with Tailwind CSS for responsive design.
- Syntax-highlighted code rendering via Highlight.js.
- Markdown processing using Marked.js.
- Real-time code copying and testing capabilities.
- File upload handling with immediate analysis feedback.

### Backend
- **LLM Integration**: Leveraging Mistral-7B with LangChain for structured responses and dual-prompt code analysis.
- **Flask**: Lightweight web framework for API integration.
- **SQLite**: Contextual memory management for chat persistence.


### Memory Management
- Manual cleanup of older conversations.
- Session-specific context retrieval for seamless interactions.
- Uses langchain's conversational buffer to maintain in-chat memory.


## Installation & Setup 🛠️
1. Clone this repository.
2. Install dependencies: `pip install -r requirements.txt`.
3. Ensure Pandoc is installed for markdown rendering.
4. Download ollama and run model in terminal: `ollama run mistral:7b`.
5. Run the application: `python app.py`.
6. Access the assistant at `http://localhost:5000`.

---

## Deliverables Checklist
### Python File
- Contains all relevant code.
- Demonstrates sample interactions showcasing the assistant's core functionality.

### Short Explanation
- Discusses design approach, assumptions made, and areas for improvement.
- https://youtu.be/7h_ccEBgkMU?si=A-eTYSmHaSKoh8Eg

---

## Future Enhancements 🔄
- Optimization of conversation buffer for memory efficiency.
- Enhanced rendering reliability for code snippets.
- Multilingual programming language support.
- Switching between various models.

---

## Technical Architecture 🏗️
```
/
├── app.py                 # Main Flask application
├── templates/            
│   └── index.html        # Frontend interface
└── chat_database.db      # SQLite database
```

### API Endpoints
- `/api/chat`: Main conversation endpoint.
- `/api/test-code`: Code execution endpoint.
- `/api/chat-list`: Chat history management.
- `/api/chat-history`: Session history retrieval.
- `/api/clear-memory`: Memory management.

### Database Schema
```sql
- chats (id, title, date, last_message)
- messages (id, chat_id, role, content, timestamp)
- important_info (id, chat_id, content)
```

---

## Evaluation Highlights ✅
- **Code Organization**: Well-structured, readable, and extensively commented.
- **Creative Approach**: Thoughtful design choices balancing complexity and usability.
- **Clear Assumptions**: Transparent discussion of limitations and mock implementations.

---

## Author
Roshaun Infant R

---



