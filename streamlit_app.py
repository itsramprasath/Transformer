# Streamlit Chat Application - Version 2.0 - Simplified for stability
import streamlit as st
import os
import sys
from pathlib import Path
import uuid
from datetime import datetime
import gc  # For garbage collection
import time
import psutil
import logging
from functools import wraps

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Memory monitoring
def check_memory_usage():
    process = psutil.Process(os.getpid())
    memory_use = process.memory_info().rss / 1024 / 1024  # Convert to MB
    if memory_use > 512:  # If using more than 512MB
        logger.warning(f"High memory usage: {memory_use:.2f}MB")
        gc.collect()  # Force garbage collection
        return False
    return True

# Render-specific optimizations
def handle_cold_start():
    """Initialize necessary services during cold start"""
    try:
        # Pre-initialize services
        get_cached_sheet_service()
        get_cached_docs_service()
        logger.info("Services pre-initialized successfully")
    except Exception as e:
        logger.error(f"Cold start initialization error: {e}")

# Cache services with shorter TTL for Render
@st.cache_resource(ttl=1800)  # 30 minute cache
def get_cached_sheet_service():
    return get_sheet_service()

@st.cache_resource(ttl=1800)  # 30 minute cache
def get_cached_docs_service():
    return get_docs_service()

# Add timeout decorator for functions
def timeout_decorator(timeout_seconds):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not check_memory_usage():
                st.warning("System is busy. Please try again in a moment.")
                return None
                
            start_time = time.time()
            result = func(*args, **kwargs)
            
            if time.time() - start_time > timeout_seconds:
                logger.warning(f"Function {func.__name__} timed out")
                st.warning("Operation took longer than expected. Please try again.")
                gc.collect()
                return None
            return result
        return wrapper
    return decorator

# Disable the dimming effect and configure page
st.set_page_config(
    page_title="Client Conversation Assistant",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': None
    }
)

# Configure Streamlit theme and memory management
st.markdown("""
    <style>
        .stDeployButton {display:none;}
        .stToolbar {display:none;}
        .stSpinner > div > div {border-top-color: transparent;}
        .stApp > header {display:none;}
        .stMarkdown {max-width: 100%;}
        .stButton > button {width: 100%;}
        div.row-widget.stRadio > div {flex-direction: row;}
        .stProgress .st-bo {background-color: transparent;}
    </style>
""", unsafe_allow_html=True)

# Add the current directory to Python path
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.append(str(current_dir))

# Import from our modules
from fred_us_tools_2 import chat, summarize_message
from google_services import (
    get_sheet_service, get_docs_service, get_drive_service,
    get_all_sheet_names, save_to_sheets, save_to_docs,
    check_sheet_exists, create_sheet,
    SPREADSHEET_ID
)

# Memory management: Clear old sessions
def cleanup_old_sessions():
    current_time = datetime.now()
    for key in list(st.session_state.keys()):
        if key.startswith('last_') and isinstance(st.session_state[key], datetime):
            if (current_time - st.session_state[key]).total_seconds() > 3600:  # 1 hour
                del st.session_state[key]
    gc.collect()  # Force garbage collection

@timeout_decorator(20)
def load_chat_history(client_name):
    """Load chat history from Google Sheets"""
    try:
        sheet_service = get_cached_sheet_service()
        result = sheet_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{client_name}!A:G"
        ).execute()
        
        values = result.get('values', [])
        if not values:
            return []
            
        # Process only last 20 messages for performance
        chat_history = []
        for row in values[-20:]:  # Get last 20 messages
            if len(row) >= 7:
                chat_history.append({
                    "timestamp": row[0],
                    "session_id": row[1] if len(row) > 1 else "",
                    "user_message": row[2],
                    "reply1": row[3] if len(row) > 3 else "",
                    "reply2": row[4] if len(row) > 4 else "",
                    "bot_reply": row[5],
                    "summary": row[6]
                })
                
        return chat_history
    except Exception as e:
        st.error(f"Error loading chat history: {e}")
        return []

def save_interaction_to_sheets(sheet_service, client_name, interaction):
    """Save interaction to sheets"""
    try:
        row_data = [
            interaction.get('timestamp', ''),
            interaction.get('session_id', ''),
            interaction.get('user_message', ''),
            interaction.get('reply1', ''),
            interaction.get('reply2', ''),
            interaction.get('final_reply', ''),
            interaction.get('summary', '')
        ]
        
        # Append new row
        sheet_service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{client_name}!A:G",
            valueInputOption='RAW',
            body={'values': [row_data]}
        ).execute()
            
        return True
    except Exception as e:
        st.error(f"Error saving to sheets: {e}")
        return False

def get_conversation_context(chat_history, current_question):
    """Create a context for the AI"""
    if not chat_history:
        return f"You are having a conversation with {st.session_state.client_name}. This is your first interaction."
    
    context = f"""You are having a conversation with {st.session_state.client_name}. 
Maintain consistency with your previous responses.

Recent conversation history:
"""
    
    # Include last 5 interactions for context
    recent_history = chat_history[-5:]
    for interaction in recent_history:
        context += f"\nUser: {interaction['user_message']}\n"
        context += f"Assistant: {interaction['bot_reply']}\n"
        context += "---\n"
    
    context += f"\nCurrent message: {current_question}\n"
    return context

def initialize_session_state():
    """Initialize session state"""
    defaults = {
        'session_id': str(uuid.uuid4()),
        'client_name': None,
        'chat_history': [],
        'current_question': None,
        'current_response': None,
        'model_choice': "openai",
        'client_initialized': False
    }
    
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

@timeout_decorator(30)
def handle_chat_input(prompt):
    """Handle chat input"""
    if not prompt:
        return
        
    st.session_state.current_question = prompt
    context = get_conversation_context(st.session_state.chat_history, prompt)
    
    with st.spinner("Processing..."):
        response = chat(context, [], st.session_state.model_choice)
        
    # Parse replies and save interaction
    reply1, reply2 = parse_replies(response)
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summary = summarize_message(response)
    
    new_interaction = {
        "timestamp": current_time,
        "session_id": st.session_state.session_id,
        "user_message": prompt,
        "bot_reply": response,
        "reply1": reply1,
        "reply2": reply2,
        "final_reply": response,
        "summary": summary
    }
    
    st.session_state.chat_history.append(new_interaction)
    st.session_state.current_response = response
    
    # Save to sheets
    try:
        sheet_service = get_cached_sheet_service()
        save_interaction_to_sheets(sheet_service, st.session_state.client_name, new_interaction)
    except Exception as e:
        st.error(f"Error saving to sheets: {e}")

def render_chat_interface():
    """Render chat interface"""
    if st.session_state.client_initialized:
        st.title(f"Conversation with {st.session_state.client_name}")
        
        # Chat input at the bottom
        prompt = st.chat_input(
            "Type your message here...",
            key=f"chat_input_{st.session_state.session_id}"
        )
        
        if prompt:
            handle_chat_input(prompt)
        
        # Display chat history
        for interaction in st.session_state.chat_history[-10:]:  # Show last 10 messages
            with st.chat_message("user"):
                st.markdown(interaction['user_message'])
            with st.chat_message("assistant"):
                st.markdown(interaction['bot_reply'])
        
        # Show current interaction
        if st.session_state.current_question:
            with st.chat_message("user"):
                st.markdown(st.session_state.current_question)
            
            if st.session_state.current_response:
                with st.chat_message("assistant"):
                    st.markdown(st.session_state.current_response)
                    
                    # Add retry button
                    col1, col2 = st.columns([0.1, 0.9])
                    with col1:
                        if st.button("🔄", key=f"retry_{st.session_state.session_id}"):
                            context = get_conversation_context(
                                st.session_state.chat_history[:-1], 
                                st.session_state.current_question
                            )
                            new_response = chat(context, [], st.session_state.model_choice)
                            
                            # Update the last interaction
                            reply1, reply2 = parse_replies(new_response)
                            st.session_state.chat_history[-1].update({
                                "bot_reply": new_response,
                                "reply1": reply1,
                                "reply2": reply2,
                                "final_reply": new_response,
                                "summary": summarize_message(new_response)
                            })
                            
                            st.session_state.current_response = new_response
                            st.rerun()
    else:
        st.title("Client Conversation Assistant")
        st.info("👈 Please select or enter a client name in the sidebar to start.")

def main():
    initialize_session_state()
    render_sidebar()
    render_chat_interface()

# Use container-level caching for smoother updates
@st.cache_data(ttl=300)
def get_cached_sheet_names():
    return get_all_sheet_names()

def parse_replies(response_text):
    """Parse the response text to extract Reply 1 and Reply 2"""
    try:
        if "Reply 1:" in response_text and "Reply 2:" in response_text:
            parts = response_text.split("Reply 2:")
            if len(parts) >= 2:
                reply2 = parts[1].strip()
                reply1 = parts[0].split("Reply 1:")[1].strip()
                return reply1, reply2
        return response_text, ""
    except Exception as e:
        st.error(f"Error parsing replies: {e}")
        return response_text, ""

def handle_start_conversation(client_name):
    if not client_name:
        st.error("Please select or enter a client name")
        return
    
    # Initialize sheet for new client
    sheet_service = get_sheet_service()
    if not check_sheet_exists(sheet_service, SPREADSHEET_ID, client_name):
        if create_sheet(sheet_service, SPREADSHEET_ID, client_name):
            st.success(f"Created new sheet for {client_name}")
        else:
            st.error("Failed to create sheet")
            return
    
    st.session_state.client_name = client_name
    st.session_state.client_initialized = True
    
    # Load chat history from sheets
    st.session_state.chat_history = load_chat_history(client_name)

def handle_clear_chat():
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.chat_history = []
    st.session_state.current_response = None
    st.session_state.current_question = None

def handle_new_client():
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.client_name = None
    st.session_state.client_initialized = False
    st.session_state.chat_history = []
    st.session_state.current_response = None
    st.session_state.current_question = None

def render_sidebar():
    with st.sidebar:
        st.title("Settings")
        
        # Client selection
        st.subheader("Client Selection")
        client_names = get_cached_sheet_names()
        
        if not st.session_state.client_initialized:
            selected_client = st.selectbox(
                "Select client:",
                [""] + client_names,
                key="client_selector"
            )
            
            new_client_name = st.text_input(
                "Or enter new client name:",
                key="new_client_name"
            )
            
            if st.button(
                "Start Conversation",
                key="start_conv",
                use_container_width=True
            ):
                handle_start_conversation(new_client_name or selected_client)
        
        # Model selection
        st.subheader("Model Settings")
        model = st.radio(
            "Select AI Model:",
            ["openai", "claude"],
            key="model_choice",
            horizontal=True
        )
        if model != st.session_state.model_choice:
            st.session_state.model_choice = model
        
        # Action buttons
        st.button(
            "Clear Chat",
            on_click=handle_clear_chat,
            use_container_width=True
        )
        
        st.button(
            "New Client",
            on_click=handle_new_client,
            use_container_width=True
        )
        
        # Display session info
        st.markdown("---")
        st.caption(f"Session ID: {st.session_state.session_id}")

# Initialize on startup
if 'cold_start_completed' not in st.session_state:
    handle_cold_start()
    st.session_state.cold_start_completed = True

if __name__ == "__main__":
    main() 
