# Streamlit Chat Application - Version 3.0 - Minimal Stable Build
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
import concurrent.futures
from typing import Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Memory monitoring
def check_memory_usage():
    """Monitor memory usage and force garbage collection if needed"""
    try:
        process = psutil.Process(os.getpid())
        memory_use = process.memory_info().rss / 1024 / 1024  # Convert to MB
        if memory_use > 512:  # If using more than 512MB
            logger.warning(f"High memory usage: {memory_use:.2f}MB")
            gc.collect()  # Force garbage collection
            return False
        return True
    except Exception as e:
        logger.error(f"Error checking memory: {e}")
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
    try:
        return get_sheet_service()
    except Exception as e:
        logger.error(f"Error getting sheet service: {e}")
        st.error("Unable to connect to Google Sheets. Please try again later.")
        return None

@st.cache_resource(ttl=1800)  # 30 minute cache
def get_cached_docs_service():
    try:
        return get_docs_service()
    except Exception as e:
        logger.error(f"Error getting docs service: {e}")
        st.error("Unable to connect to Google Docs. Please try again later.")
        return None

# Add timeout decorator for functions
def timeout_decorator(timeout_seconds):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not check_memory_usage():
                st.warning("System is busy. Please try again in a moment.")
                return None
                
            start_time = time.time()
            
            # Use ThreadPoolExecutor for timeout
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(func, *args, **kwargs)
                try:
                    result = future.result(timeout=timeout_seconds)
                    
                    if time.time() - start_time > timeout_seconds:
                        logger.warning(f"Function {func.__name__} timed out")
                        st.warning("Operation took longer than expected. Please try again.")
                        gc.collect()
                        return None
                    return result
                except concurrent.futures.TimeoutError:
                    logger.error(f"Function {func.__name__} execution timed out")
                    st.error("Operation timed out. Please try again.")
                    return None
                except Exception as e:
                    logger.error(f"Error in {func.__name__}: {e}")
                    st.error(f"An error occurred: {str(e)}")
                    return None
        return wrapper
    return decorator

# Disable the dimming effect and configure page
st.set_page_config(
    page_title="Client Conversation Assistant",
    page_icon="💬",
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
        * {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }
        /* Override any default title styles */
        .main > div:first-child h1 {
            visibility: visible !important;
            height: auto !important;
            display: block !important;
        }
        /* Hide Simple Chat title if it exists */
        h1:contains("Simple Chat") {
            display: none !important;
        }
        .stSidebar {
            background-color: #f0f2f5;
            padding: 1rem;
        }
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

def save_interaction_to_sheets(sheet_service, client_name, interaction, max_retries=3):
    """Save interaction to sheets with retry mechanism"""
    if not sheet_service:
        logger.error("Sheet service not available")
        return False

    for attempt in range(max_retries):
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
            
            sheet_service.spreadsheets().values().append(
                spreadsheetId=SPREADSHEET_ID,
                range=f"{client_name}!A:G",
                valueInputOption='RAW',
                body={'values': [row_data]}
            ).execute()
                
            return True
        except Exception as e:
            logger.error(f"Error saving to sheets (attempt {attempt + 1}): {e}")
            if attempt == max_retries - 1:
                st.error(f"Error saving to sheets: {e}")
                return False
            time.sleep(1)  # Wait before retry

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

# Initialize session state variables
if 'initialized' not in st.session_state:
    st.session_state.initialized = False
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.client_name = None
    st.session_state.client_initialized = False
    st.session_state.chat_history = []
    st.session_state.current_question = None
    st.session_state.current_response = None
    st.session_state.model_choice = "openai"

def initialize_session_state():
    """Initialize or reset session state variables"""
    if not st.session_state.initialized:
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.client_name = None
        st.session_state.client_initialized = False
        st.session_state.chat_history = []
        st.session_state.current_question = None
        st.session_state.current_response = None
        st.session_state.model_choice = "openai"
        st.session_state.initialized = True

@timeout_decorator(30)
def handle_chat_input(prompt):
    """Handle chat input with optimized memory usage"""
    if not prompt:
        return
        
    st.session_state.current_question = prompt
    context = get_conversation_context(st.session_state.chat_history[-5:], prompt)  # Only use last 5 messages for context
    
    with st.spinner("Processing..."):
        try:
            response = chat(context, [], st.session_state.model_choice)
            if not response:
                st.error("Failed to get response from AI model")
                return
                
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
            
            # Maintain a maximum history size
            if len(st.session_state.chat_history) > 50:  # Keep only last 50 messages
                st.session_state.chat_history = st.session_state.chat_history[-50:]
            
            st.session_state.chat_history.append(new_interaction)
            st.session_state.current_response = response
            
            # Save to sheets with retry mechanism
            sheet_service = get_cached_sheet_service()
            if sheet_service:
                save_interaction_to_sheets(sheet_service, st.session_state.client_name, new_interaction)
            
        except Exception as e:
            logger.error(f"Error in chat input handling: {e}")
            st.error("An error occurred while processing your message. Please try again.")
            gc.collect()

def render_chat_interface():
    """Render chat interface with optimized performance"""
    try:
        # Always set the main title
        st.markdown("<h1>Client Conversation Assistant</h1>", unsafe_allow_html=True)
        
        if st.session_state.client_initialized:
            st.markdown(f"### Conversation with {st.session_state.client_name}")
            
            # Chat input at the bottom
            prompt = st.chat_input("Type your message here...")
            
            # Clear previous messages from display when new input is received
            if prompt:
                # Clear any previous messages from session state
                st.session_state.current_question = None
                st.session_state.current_response = None
                # Handle new input
                handle_chat_input(prompt)
            
            # Only show the most recent question and answer
            if st.session_state.current_question:
                # Container for current conversation
                chat_container = st.container()
                with chat_container:
                    with st.chat_message("user"):
                        st.write(st.session_state.current_question)
                    if st.session_state.current_response:
                        with st.chat_message("assistant"):
                            # First show the response
                            st.markdown(st.session_state.current_response)
                            
                            # Add retry button with error handling
                            col1, col2 = st.columns([0.1, 0.9])
                            with col1:
                                retry_key = f"retry_current_{st.session_state.session_id}"
                                if st.button("🔄", key=retry_key):
                                    try:
                                        with st.spinner("Regenerating response..."):
                                            # Regenerate response with full context
                                            context = get_conversation_context(
                                                st.session_state.chat_history[-5:],  # Only use last 5 messages
                                                st.session_state.current_question
                                            )
                                            new_response = chat(context, [], st.session_state.model_choice)
                                            
                                            if new_response:
                                                # Update the last interaction with new response
                                                reply1, reply2 = parse_replies(new_response)
                                                st.session_state.chat_history[-1].update({
                                                    "bot_reply": new_response,
                                                    "reply1": reply1,
                                                    "reply2": reply2,
                                                    "final_reply": new_response,
                                                    "summary": summarize_message(new_response)
                                                })
                                                
                                                # Save updated response to sheets
                                                sheet_service = get_cached_sheet_service()
                                                if sheet_service:
                                                    save_interaction_to_sheets(
                                                        sheet_service,
                                                        st.session_state.client_name,
                                                        st.session_state.chat_history[-1]
                                                    )
                                                    
                                                st.session_state.current_response = new_response
                                                st.rerun()
                                    except Exception as e:
                                        logger.error(f"Error in retry: {e}")
                                        st.error("Failed to regenerate response. Please try again.")
                
                # Save reply interface after the chat messages
                if st.session_state.current_response:
                    with st.expander("Save Reply Tool", expanded=False):
                        st.subheader("Save Reply to Google Docs")
                        
                        col1, col2 = st.columns([0.3, 0.7])
                        with col1:
                            reply_number = st.number_input(
                                "Reply Number (1 or 2)",
                                min_value=1,
                                max_value=2,
                                value=1,
                                key=f"reply_number_{st.session_state.session_id}"
                            )
                        
                        try:
                            # Preview and edit
                            reply1, reply2 = parse_replies(st.session_state.current_response)
                            selected_reply = reply1 if reply_number == 1 else reply2
                            
                            edited_reply = st.text_area(
                                "Preview & Edit Reply",
                                value=selected_reply,
                                height=150,
                                key=f"edited_reply_{st.session_state.session_id}"
                            )
                            
                            if st.button(
                                "Save to Google Docs",
                                key=f"save_docs_{st.session_state.session_id}",
                                use_container_width=True
                            ):
                                with st.spinner("Saving to Google Docs..."):
                                    try:
                                        docs_service = get_cached_docs_service()
                                        drive_service = get_drive_service()
                                        
                                        if not docs_service or not drive_service:
                                            st.error("Unable to connect to Google services")
                                            return
                                        
                                        # Format content for docs with session ID
                                        content = f"Session: {st.session_state.session_id}\n"
                                        content += f"@{st.session_state.client_name} - {st.session_state.current_question}\n\n"
                                        content += f"@Reply - {edited_reply}"
                                        
                                        # Save to docs with timeout
                                        with concurrent.futures.ThreadPoolExecutor() as executor:
                                            future = executor.submit(
                                                save_to_docs,
                                                docs_service,
                                                drive_service,
                                                st.session_state.client_name,
                                                content
                                            )
                                            result = future.result(timeout=20)  # 20 second timeout
                                        
                                        if result["status"] == "success":
                                            # Update the final reply in sheets
                                            st.session_state.chat_history[-1]["final_reply"] = edited_reply
                                            sheet_service = get_cached_sheet_service()
                                            if sheet_service:
                                                save_interaction_to_sheets(
                                                    sheet_service,
                                                    st.session_state.client_name,
                                                    st.session_state.chat_history[-1]
                                                )
                                            st.success(f"Saved to Google Docs - [View Document]({result['document_url']})")
                                        else:
                                            st.error(f"Error saving to docs: {result['message']}")
                                            
                                    except concurrent.futures.TimeoutError:
                                        st.error("Save operation timed out. Please try again.")
                                    except Exception as e:
                                        logger.error(f"Error saving reply: {e}")
                                        st.error(f"Error saving reply: {str(e)}")
                        except Exception as e:
                            logger.error(f"Error in save reply interface: {e}")
                            st.error("An error occurred in the save reply interface")
        else:
            st.info("👈 Please select or enter a client name in the sidebar to start.")
    except Exception as e:
        logger.error(f"Error in chat interface: {e}")
        st.error("An error occurred in the chat interface. Please refresh the page.")
        gc.collect()

def main():
    try:
        # Initialize if not already done
        if not st.session_state.initialized:
            initialize_session_state()
        
        # Always render sidebar first
        render_sidebar()
        
        # Then render main interface
        render_chat_interface()
        
        # Run cleanup periodically
        cleanup_old_sessions()
        
    except Exception as e:
        st.error(f"An error occurred while loading the application: {str(e)}")
        logger.error(f"Application error: {str(e)}")
        if st.button("Retry"):
            st.experimental_rerun()

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
    try:
        handle_cold_start()
        st.session_state.cold_start_completed = True
    except Exception as e:
        st.error(f"Error during cold start: {str(e)}")
        logger.error(f"Cold start error: {str(e)}")

if __name__ == "__main__":
    main() 
