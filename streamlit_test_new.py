import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
import os
import html
from not_focus.chat_with_ai import create_interface

# Initialize session state for theme if it doesn't exist
if 'theme' not in st.session_state:
    st.session_state.theme = 'light'
if 'show_ai_chat' not in st.session_state:
    st.session_state.show_ai_chat = False

def toggle_theme():
    st.session_state.theme = 'dark' if st.session_state.theme == 'light' else 'light'

def toggle_ai_chat():
    st.session_state.show_ai_chat = not st.session_state.show_ai_chat

# Configure the page
st.set_page_config(
    page_title="Chat Interface",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS with theme-dependent colors
def get_theme_css():
    if st.session_state.theme == 'dark':
        return """
        <style>
            /* Dark theme colors */
            :root {
                --background-color: #111b21;
                --secondary-bg: #222e35;
                --text-color: #e9edef;
                --message-bg-out: #005c4b;
                --message-bg-in: #222e35;
                --timestamp-color: #8696a0;
            }
            
            .main .block-container {
                padding-top: 1rem;
                padding-right: 1rem;
                padding-left: 1rem;
                padding-bottom: 1rem;
                background-color: var(--background-color);
            }
            
            /* Clean header styling */
            .chat-header {
                background-color: var(--secondary-bg);
                padding: 10px 16px;
                display: flex;
                align-items: center;
                gap: 10px;
                border-bottom: 1px solid #e0e0e0;
                margin: -1rem -1rem 1rem -1rem;
            }
            
            /* Message styling */
            .message-container {
                max-width: 100%;
                margin-bottom: 8px;
                padding: 0 1rem;
            }
            
            .message {
                padding: 8px 12px;
                border-radius: 8px;
                max-width: 70%;
                position: relative;
                font-size: 14px;
                line-height: 1.4;
                color: var(--text-color);
            }
            
            .message-time {
                font-size: 11px;
                color: var(--timestamp-color);
                margin-top: 4px;
                text-align: right;
            }
            
            /* Hide default Streamlit elements */
            #MainMenu, footer {display: none;}
            div[data-testid="stToolbar"] {display: none;}
            div[data-testid="stDecoration"] {display: none;}
            div[data-testid="stStatusWidget"] {display: none;}

            /* Avatar styling */
            .avatar {
                width: 40px;
                height: 40px;
                background-color: #00a884;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-weight: 500;
                font-size: 16px;
            }
        </style>
        """
    else:
        return """
        <style>
            /* Light theme colors */
            :root {
                --background-color: #efeae2;
                --secondary-bg: #f0f2f5;
                --text-color: #111b21;
                --message-bg-out: #d9fdd3;
                --message-bg-in: #ffffff;
                --timestamp-color: #667781;
            }
            
            .main .block-container {
                padding-top: 1rem;
                padding-right: 1rem;
                padding-left: 1rem;
                padding-bottom: 1rem;
                background-color: var(--background-color);
            }
            
            /* Clean header styling */
            .chat-header {
                background-color: var(--secondary-bg);
                padding: 10px 16px;
                display: flex;
                align-items: center;
                gap: 10px;
                border-bottom: 1px solid #e0e0e0;
                margin: -1rem -1rem 1rem -1rem;
            }
            
            /* Message styling */
            .message-container {
                max-width: 100%;
                margin-bottom: 8px;
                padding: 0 1rem;
            }
            
            .message {
                padding: 8px 12px;
                border-radius: 8px;
                max-width: 70%;
                position: relative;
                font-size: 14px;
                line-height: 1.4;
                color: var(--text-color);
            }
            
            .message-time {
                font-size: 11px;
                color: var(--timestamp-color);
                margin-top: 4px;
                text-align: right;
            }
            
            /* Hide default Streamlit elements */
            #MainMenu, footer {display: none;}
            div[data-testid="stToolbar"] {display: none;}
            div[data-testid="stDecoration"] {display: none;}
            div[data-testid="stStatusWidget"] {display: none;}

            /* Avatar styling */
            .avatar {
                width: 40px;
                height: 40px;
                background-color: #00a884;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-weight: 500;
                font-size: 16px;
            }
        </style>
        """

# Apply theme CSS
st.markdown(get_theme_css(), unsafe_allow_html=True)

# Your spreadsheet ID
SPREADSHEET_ID = "1EsdKKIzfNr2wXFBvN4Ee9jKE8RToxO54DR2c7KOWPFg"

# Define the scope
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

def get_google_credentials():
    """Get and cache credentials for Google Sheets API."""
    creds = None
    if os.path.exists('token_sheets.pickle'):
        with open('token_sheets.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('/etc/secrets/credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token_sheets.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    return creds

def get_sheet_service():
    """Get Google Sheets API service."""
    creds = get_google_credentials()
    return build('sheets', 'v4', credentials=creds)

def get_all_sheet_names():
    """Get all sheet names from the spreadsheet."""
    try:
        sheet_service = get_sheet_service()
        spreadsheet = sheet_service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
        return [sheet['properties']['title'] for sheet in spreadsheet.get('sheets', [])]
    except Exception as e:
        st.error(f"Error getting sheet names: {str(e)}")
        return []

def get_sheet_data(sheet_name):
    """Get data from a specific sheet."""
    try:
        sheet_service = get_sheet_service()
        result = sheet_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{sheet_name}!A:G"
        ).execute()
        
        values = result.get('values', [])
        if not values:
            return pd.DataFrame()
        
        headers = values[0]
        df = pd.DataFrame(values[1:], columns=headers)
        
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp', ascending=True)
        
        return df
    except Exception as e:
        st.error(f"Error loading sheet {sheet_name}: {str(e)}")
        return pd.DataFrame()

def get_initials(name):
    """Get initials from a name."""
    return ''.join(word[0].upper() for word in name.split() if word)

# Get available sheets
sheet_names = get_all_sheet_names()

if sheet_names:
    # Add sidebar title with native Streamlit styling
    st.sidebar.title("Chats")
    
    # Add theme toggle to sidebar
    with st.sidebar:
        st.write("Theme")
        theme_emoji = "🌙" if st.session_state.theme == 'light' else "☀️"
        if st.toggle(f"Dark Mode {theme_emoji}", value=st.session_state.theme == 'dark', key="theme_toggle"):
            if st.session_state.theme == 'light':
                st.session_state.theme = 'dark'
                st.rerun()
        else:
            if st.session_state.theme == 'dark':
                st.session_state.theme = 'light'
                st.rerun()
        
        st.markdown("---")  # Add a separator
        
        # Add AI Chat button to sidebar
        if st.sidebar.button("💬 Chat with AI Assistant", use_container_width=True):
            st.session_state.show_ai_chat = True
            st.rerun()
        
        st.markdown("---")  # Add another separator
    
    # Create radio buttons for chat selection
    selected_sheet = st.sidebar.radio(
        "Select a chat:",
        options=sheet_names,
        label_visibility="collapsed",
        key="chat_selector"
    )
    
    # Show either the regular chat or AI chat interface
    if st.session_state.show_ai_chat:
        # Add a button to go back to regular chat
        if st.sidebar.button("← Back to Regular Chat", use_container_width=True):
            st.session_state.show_ai_chat = False
            st.rerun()
        
        # Create a new container for the AI chat
        with st.container():
            st.markdown("""
                <div style='padding: 1em; border-radius: 5px; margin-bottom: 1em;'>
                    <h2>AI Assistant Chat</h2>
                </div>
            """, unsafe_allow_html=True)
            
            # Import and run the AI chat interface
            create_interface()
    else:
        if selected_sheet:
            # Get sheet data
            df = get_sheet_data(selected_sheet)
            
            # Create header
            st.markdown(f"""
                <div class="chat-header">
                    <div class="avatar">{get_initials(selected_sheet)}</div>
                    <div>
                        <div style="font-weight: 600; color: var(--text-color);">{selected_sheet}</div>
                        <div style="font-size: 13px; color: var(--timestamp-color);">online</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            # Create messages container
            messages_container = st.container()
            
            # Display messages using Streamlit's native components with custom styling
            with messages_container:
                for _, row in df.iterrows():
                    timestamp = row['timestamp'].strftime('%I:%M %p') if pd.notna(row['timestamp']) else ''
                    
                    # Display user message
                    if pd.notna(row.get('message')):
                        st.markdown(f"""
                            <div class="message-container">
                                <div class="message" style="background-color: var(--message-bg-in); margin-right: auto;">
                                    {row['message']}
                                    <div class="message-time">{timestamp}</div>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                    
                    # Display reply
                    if pd.notna(row.get('Final Reply')):
                        st.markdown(f"""
                            <div class="message-container" style="text-align: right;">
                                <div class="message" style="background-color: var(--message-bg-out); margin-left: auto;">
                                    {row['Final Reply']}
                                    <div class="message-time">{timestamp}</div>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)

else:
    st.error("No sheets available. Please check your credentials and sheet ID.") 