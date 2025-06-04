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
import openai
import anthropic

# Disable file watcher in production to avoid inotify limits
if not os.environ.get("DEVELOPMENT"):
    os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"

# Configure page
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
        .stError {
            background-color: #ffebee;
            padding: 1rem;
            border-radius: 0.5rem;
            margin: 1rem 0;
        }
    </style>
""", unsafe_allow_html=True)

# Add the current directory to Python path
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.append(str(current_dir))

# Google API scopes
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

def init_google_client():
    """Initialize Google client with proper error handling"""
    try:
        if not st.secrets.get("gcp_service_account"):
            st.error("Google service account credentials not found in secrets")
            return None
        
        credentials = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=SCOPES
        )
        return credentials
    except Exception as e:
        st.error(f"Error initializing Google client: {e}")
        return None

def init_api_clients():
    """Initialize API clients with proper error handling"""
    try:
        # Initialize OpenAI
        if st.secrets.get("OPENAI_API_KEY"):
            openai.api_key = st.secrets["OPENAI_API_KEY"]
        else:
            st.error("OpenAI API key not found in secrets")
        
        # Initialize Anthropic
        if st.secrets.get("ANTHROPIC_API_KEY"):
            try:
                st.session_state.claude = anthropic.Client(api_key=st.secrets["ANTHROPIC_API_KEY"])
            except Exception as e:
                st.error(f"Error initializing Anthropic client: {e}")
                st.session_state.claude = None
        else:
            st.error("Anthropic API key not found in secrets")
            st.session_state.claude = None
    except Exception as e:
        st.error(f"Error initializing API clients: {e}")

def get_sheet_service():
    """Get Google Sheets API service"""
    credentials = init_google_client()
    if not credentials:
        return None
    return build('sheets', 'v4', credentials=credentials)

def get_drive_service():
    """Get Google Drive API service"""
    credentials = init_google_client()
    if not credentials:
        return None
    return build('drive', 'v3', credentials=credentials)

def check_credentials():
    """Check for all required credentials"""
    missing = []
    
    if not st.secrets.get("OPENAI_API_KEY"):
        missing.append("OpenAI API key")
    if not st.secrets.get("ANTHROPIC_API_KEY"):
        missing.append("Anthropic API key")
    if not st.secrets.get("SPREADSHEET_ID"):
        missing.append("Google Spreadsheet ID")
    if not st.secrets.get("gcp_service_account"):
        missing.append("Google service account credentials")
    
    if missing:
        st.error(f"Missing required credentials: {', '.join(missing)}")
        st.info("Please add the missing credentials to your Streamlit secrets.")
        return False
    return True

def load_chat_history(client_name):
    """Load chat history from Google Sheets"""
    try:
        sheet_service = get_sheet_service()
        if not sheet_service:
            return []
            
        result = sheet_service.spreadsheets().values().get(
            spreadsheetId=st.secrets["SPREADSHEET_ID"],
            range=f"{client_name}!A:G"
        ).execute()
        
        values = result.get('values', [])
        if not values:
            return []
        
        # Skip header row and format history
        chat_history = []
        for row in values[1:]:
            if len(row) >= 7:
                chat_history.append({
                    "timestamp": row[0],
                    "message": row[2],
                    "response": row[5],
                    "summary": row[6]
                })
        return chat_history
    except Exception as e:
        st.error(f"Error loading chat history: {e}")
        return []

def save_chat(client_name, message, response, summary):
    """Save chat interaction to Google Sheets"""
    try:
        sheet_service = get_sheet_service()
        if not sheet_service:
            return False
            
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row = [[timestamp, client_name, message, "", "", response, summary]]
        
        sheet_service.spreadsheets().values().append(
            spreadsheetId=st.secrets["SPREADSHEET_ID"],
            range=f"{client_name}!A:G",
            valueInputOption="RAW",
            body={"values": row}
        ).execute()
        return True
    except Exception as e:
        st.error(f"Error saving chat: {e}")
        return False

def chat_with_ai(message, model="gpt-4"):
    """Chat with AI using either OpenAI or Anthropic"""
    try:
        if model == "claude":
            if not st.session_state.get("claude"):
                st.error("Anthropic client not initialized")
                return None
                
            try:
                response = st.session_state.claude.messages.create(
                    model="claude-3-opus-20240229",
                    max_tokens=1000,
                    messages=[{"role": "user", "content": message}]
                )
                return response.content[0].text
            except Exception as e:
                st.error(f"Error with Claude API: {e}")
                return None
        else:
            try:
                response = openai.ChatCompletion.create(
                    model=model,
                    messages=[{"role": "user", "content": message}],
                    max_tokens=1000
                )
                return response.choices[0].message.content
            except Exception as e:
                st.error(f"Error with OpenAI API: {e}")
                return None
    except Exception as e:
        st.error(f"Error in chat_with_ai: {e}")
        return None

def main():
    if not check_credentials():
        st.stop()
    
    init_api_clients()
    
    st.title("Client Conversation Assistant")
    
    # Sidebar
    with st.sidebar:
        st.header("Settings")
        model = st.selectbox("Select AI Model", ["gpt-4", "claude"])
        client_name = st.text_input("Client Name", "Example Client")
        
        if st.button("Clear Chat"):
            st.session_state.messages = []
    
    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []
        history = load_chat_history(client_name)
        for chat in history:
            st.session_state.messages.append({"role": "user", "content": chat["message"]})
            st.session_state.messages.append({"role": "assistant", "content": chat["response"]})
    
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
    
    # Chat input
    if prompt := st.chat_input():
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)
        
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                response = chat_with_ai(prompt, model)
                if response:
                    st.write(response)
                    st.session_state.messages.append({"role": "assistant", "content": response})
                    
                    # Save to Google Sheets
                    summary = chat_with_ai(f"Summarize this message briefly: {response}", model)
                    save_chat(client_name, prompt, response, summary or "No summary available")

if __name__ == "__main__":
    main() 
