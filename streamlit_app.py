import streamlit as st
import os
import sys
from pathlib import Path
import uuid
from datetime import datetime
import google_auth_oauthlib.flow
from googleapiclient.discovery import build
import webbrowser
import googleapiclient.http
from io import BytesIO
import json
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from openai import OpenAI
from anthropic import Anthropic

# Disable file watcher in production to avoid inotify limits
if not os.environ.get("DEVELOPMENT"):
    os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"

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

# Configure Streamlit theme
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
        .signin-button {
            position: absolute;
            top: 20px;
            right: 20px;
            z-index: 1000;
        }
        .auth-status {
            position: absolute;
            top: 20px;
            right: 200px;
            z-index: 1000;
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
    SPREADSHEET_ID, get_google_credentials
)

def load_chat_history(client_name):
    """Load chat history from Google Sheets and format it for context"""
    try:
        sheet_service = get_sheet_service()
        result = sheet_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{client_name}!A:G"
        ).execute()
        
        values = result.get('values', [])
        if not values:
            return []
            
        # Skip header row
        chat_history = []
        for row in values[1:]:
            if len(row) >= 7:  # Ensure row has all required columns
                timestamp = row[0]  # Timestamp
                message = row[2]    # Message column
                reply = row[5]      # Final Reply column
                summary = row[6]    # Summarized Reply column
                
                # Add to context history
                chat_history.append({
                    "timestamp": timestamp,
                    "user_message": message,
                    "bot_reply": reply,
                    "summary": summary
                })
                    
        return chat_history
    except Exception as e:
        st.error(f"Error loading chat history: {e}")
        return []

def get_conversation_context(chat_history, current_question):
    """Create a context for the AI by including all past interactions"""
    if not chat_history:
        return f"""You are having a conversation with {st.session_state.client_name}. 
This is your first interaction. Maintain a consistent personality throughout the conversation."""
    
    context = f"""You are having a conversation with {st.session_state.client_name}. 
You have a complete history of all previous interactions with this client.
Maintain consistency with your previous responses and personality.

Previous conversation history:
"""
    
    # Include all previous interactions
    for interaction in chat_history:
        timestamp = interaction.get('timestamp', 'No timestamp')
        context += f"\nTime: {timestamp}\n"
        context += f"User: {interaction['user_message']}\n"
        context += f"Your response: {interaction['bot_reply']}\n"
        if interaction.get('summary'):
            context += f"Summary: {interaction['summary']}\n"
        context += "---\n"
    
    context += f"\nCurrent message: {current_question}\n"
    context += "\nRespond naturally while maintaining consistency with your previous interactions."
    
    return context

def save_interaction_to_sheets(sheet_service, client_name, interaction):
    """Helper function to save/update interaction in sheets with proper session tracking"""
    try:
        # Format data for sheets
        row_data = [
            interaction.get('timestamp', ''),
            interaction.get('session_id', ''),
            interaction.get('user_message', ''),
            interaction.get('reply1', ''),
            interaction.get('reply2', ''),
            interaction.get('final_reply', ''),
            interaction.get('summary', '')
        ]
        
        # If this is a retry/edit of an existing message, try to update the existing row
        result = sheet_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{client_name}!A:H"
        ).execute()
        
        values = result.get('values', [])
        row_index = None
        
        # Look for matching session_id and message
        for idx, row in enumerate(values):
            if len(row) > 1 and row[1] == interaction['session_id'] and row[2] == interaction['user_message']:
                row_index = idx + 1  # +1 because sheets are 1-indexed
                break
        
        if row_index:
            # Update existing row
            range_name = f"{client_name}!A{row_index}:G{row_index}"
            sheet_service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=range_name,
                valueInputOption='RAW',
                body={'values': [row_data]}
            ).execute()
        else:
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

def handle_chat_input(prompt):
    if not prompt:
        return
        
    st.session_state.current_question = prompt
    
    # Get conversation context from history
    context = get_conversation_context(st.session_state.chat_history, prompt)
    
    with st.spinner("Processing..."):
        # Pass the full context as the prompt
        response = chat(context, [], st.session_state.model_choice)
    
    # Save the interaction to chat history with full details
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summary = summarize_message(response)
    
    # Parse replies
    reply1, reply2 = parse_replies(response)
    
    new_interaction = {
        "timestamp": current_time,
        "session_id": st.session_state.session_id,
        "user_message": prompt,
        "bot_reply": response,
        "reply1": reply1,
        "reply2": reply2,
        "final_reply": response,  # Initially same as full response
        "summary": summary
    }
    
    st.session_state.chat_history.append(new_interaction)
    st.session_state.current_response = response
    
    # Save to sheets
    try:
        sheet_service = get_sheet_service()
        save_interaction_to_sheets(sheet_service, st.session_state.client_name, new_interaction)
    except Exception as e:
        st.error(f"Error saving to sheets: {e}")

def render_chat_interface():
    if st.session_state.client_initialized:
        st.title(f"Conversation with {st.session_state.client_name}")
        
        # Chat container for better performance
        chat_container = st.container()
        
        # Chat input at the bottom
        prompt = st.chat_input(
            "Type your message here...",
            key=f"chat_input_{st.session_state.session_id}"
        )
        if prompt:
            handle_chat_input(prompt)
        
        # Display chat in the container
        with chat_container:
            # Show current interaction
            if st.session_state.current_question:
                with st.chat_message("user"):
                    st.markdown(st.session_state.current_question)
                
                if st.session_state.current_response:
                    with st.chat_message("assistant"):
                        # First show the response
                        st.markdown(st.session_state.current_response)
                        
                        # Add retry button
                        col1, col2 = st.columns([0.1, 0.9])
                        with col1:
                            retry_key = f"retry_current_{st.session_state.session_id}"
                            if st.button("🔄", key=retry_key):
                                # Regenerate response with full context
                                context = get_conversation_context(
                                    st.session_state.chat_history[:-1], 
                                    st.session_state.current_question
                                )
                                new_response = chat(context, [], st.session_state.model_choice)
                                
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
                                try:
                                    sheet_service = get_sheet_service()
                                    save_interaction_to_sheets(
                                        sheet_service,
                                        st.session_state.client_name,
                                        st.session_state.chat_history[-1]
                                    )
                                except Exception as e:
                                    st.error(f"Error saving retry to sheets: {e}")
                                    
                                st.session_state.current_response = new_response
                                st.rerun()
            
            # Save reply interface after the chat messages
            if st.session_state.current_response:
                with st.expander("Save Reply Tool", expanded=False):  # Changed to collapsed by default
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
                                docs_service = get_docs_service()
                                drive_service = get_drive_service()
                                
                                # Format content for docs with session ID
                                content = f"Session: {st.session_state.session_id}\n"
                                content += f"@{st.session_state.client_name} - {st.session_state.current_question}\n\n"
                                content += f"@Reply - {edited_reply}"
                                
                                # Save to docs
                                result = save_to_docs(
                                    docs_service,
                                    drive_service,
                                    st.session_state.client_name,
                                    content
                                )
                                
                                if result["status"] == "success":
                                    # Update the final reply in sheets
                                    st.session_state.chat_history[-1]["final_reply"] = edited_reply
                                    sheet_service = get_sheet_service()
                                    save_interaction_to_sheets(
                                        sheet_service,
                                        st.session_state.client_name,
                                        st.session_state.chat_history[-1]
                                    )
                                    st.success(f"Saved to Google Docs - [View Document]({result['document_url']})")
                                else:
                                    st.error(f"Error saving to docs: {result['message']}")
                                    
                            except Exception as e:
                                st.error(f"Error saving reply: {e}")
    else:
        st.title("Client Conversation Assistant")
        st.info("👈 Please select or enter a client name in the sidebar to start.")

def main():
    initialize_session_state()
    render_auth_status()  # Add authentication status at the top
    render_sidebar()
    render_chat_interface()

def initialize_session_state():
    """Initialize session state variables"""
    defaults = {
        'session_id': str(uuid.uuid4()),
        'client_name': None,
        'chat_history': [],
        'current_question': None,
        'current_response': None,
        'model_choice': "openai",
        'client_initialized': False,
        'needs_update': False,
        'is_authenticated': False,
        'default_spreadsheet_loaded': False
    }
    
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

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
    st.session_state.needs_update = True

def handle_clear_chat():
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.chat_history = []
    st.session_state.current_response = None
    st.session_state.current_question = None
    st.session_state.needs_update = True

def handle_new_client():
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.client_name = None
    st.session_state.client_initialized = False
    st.session_state.chat_history = []
    st.session_state.current_response = None
    st.session_state.current_question = None
    st.session_state.needs_update = True

def handle_auth():
    """Handle Google authentication"""
    try:
        creds = get_google_credentials()
        if creds and creds.valid:
            st.session_state.is_authenticated = True
            return True
        return False
    except Exception as e:
        st.error(f"Authentication error: {str(e)}")
        return False

def load_default_spreadsheet():
    """Load the default RAG spreadsheet or create it if it doesn't exist"""
    try:
        if not st.session_state.is_authenticated:
            return
            
        sheet_service = get_sheet_service()
        try:
            # Try to access the spreadsheet
            sheet_service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
        except Exception:
            # Create new spreadsheet named "RAG"
            spreadsheet = {
                'properties': {
                    'title': 'RAG'
                }
            }
            spreadsheet = sheet_service.spreadsheets().create(body=spreadsheet).execute()
            os.environ['SPREADSHEET_ID'] = spreadsheet['spreadsheetId']
            
        st.session_state.default_spreadsheet_loaded = True
    except Exception as e:
        st.error(f"Error loading default spreadsheet: {str(e)}")

# Use container-level caching for smoother updates
@st.cache_data(ttl=300)
def get_cached_sheet_names():
    """Get cached sheet names with proper error handling"""
    try:
        if not st.session_state.is_authenticated:
            return ["Example Client"]
            
        if not st.session_state.default_spreadsheet_loaded:
            load_default_spreadsheet()
            
        names = get_all_sheet_names()
        if not names:
            return ["Example Client"]
        return names
    except Exception as e:
        print(f"Error getting sheet names: {e}")
        return ["Example Client"]

def render_auth_status():
    """Render authentication status and sign-in button"""
    col1, col2 = st.columns([3, 1])
    
    with col1:
        if st.session_state.is_authenticated:
            st.markdown('<div class="auth-status">✓ Connected to Google</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="auth-status">❌ Not connected</div>', unsafe_allow_html=True)
    
    with col2:
        if not st.session_state.is_authenticated:
            if st.button("Sign in with Google", key="google_signin"):
                if handle_auth():
                    st.rerun()
        else:
            if st.button("Sign out", key="google_signout"):
                st.session_state.is_authenticated = False
                st.session_state.default_spreadsheet_loaded = False
                st.rerun()

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
                if not st.session_state.is_authenticated:
                    st.error("Please sign in with Google first")
                else:
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

if __name__ == "__main__":
    main() 
