# Streamlit Chat Application - Version 3.1 - Render Optimized
import streamlit as st
import os
import sys
from pathlib import Path
import uuid
from datetime import datetime

# Add the current directory to Python path
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.append(str(current_dir))

# Import core functionality
from fred_us_tools_2 import chat
from google_services import (
    get_sheet_service,
    get_all_sheet_names,
    check_sheet_exists,
    create_sheet,
    SPREADSHEET_ID
)

# Basic page config
st.set_page_config(
    page_title="Client Conversation Assistant",
    layout="wide",
    initial_sidebar_state="expanded"
)

def save_message(sheet_service, client_name, message, response):
    """Save message to sheets"""
    try:
        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            message,
            response
        ]
        sheet_service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{client_name}!A:C",
            valueInputOption='RAW',
            body={'values': [row]}
        ).execute()
    except Exception as e:
        st.error(f"Error saving: {str(e)}")

def get_last_messages(sheet_service, client_name):
    """Get last 2 messages for minimal context"""
    try:
        result = sheet_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{client_name}!A:C"
        ).execute()
        values = result.get('values', [])
        return values[-2:] if len(values) > 2 else values
    except:
        return []

def main():
    # Initialize session state
    if 'client_name' not in st.session_state:
        st.session_state.client_name = None
    if 'sheet_service' not in st.session_state:
        st.session_state.sheet_service = get_sheet_service()
    if 'model_choice' not in st.session_state:
        st.session_state.model_choice = 'openai'
    
    # Sidebar
    with st.sidebar:
        st.title("Settings")
        
        # Client selection
        if not st.session_state.client_name:
            clients = [""] + get_all_sheet_names()
            selected = st.selectbox("Select client:", clients)
            new_client = st.text_input("Or enter new name:")
            
            if st.button("Start"):
                client = new_client or selected
                if client:
                    if not check_sheet_exists(st.session_state.sheet_service, SPREADSHEET_ID, client):
                        create_sheet(st.session_state.sheet_service, SPREADSHEET_ID, client)
                    st.session_state.client_name = client
        
        # Model selection
        st.session_state.model_choice = st.radio(
            "Model:",
            ["openai", "claude"],
            horizontal=True
        )
        
        # Reset button
        if st.button("New Client"):
            st.session_state.client_name = None
    
    # Main chat interface
    if st.session_state.client_name:
        st.title(f"Chat with {st.session_state.client_name}")
        
        # Chat input
        message = st.chat_input("Message")
        if message:
            # Get minimal context
            context = ""
            last_msgs = get_last_messages(st.session_state.sheet_service, st.session_state.client_name)
            if last_msgs:
                for msg in last_msgs:
                    if len(msg) >= 3:
                        context += f"User: {msg[1]}\nAssistant: {msg[2]}\n"
            context += f"User: {message}"
            
            # Get response
            try:
                response = chat(context, [], st.session_state.model_choice)
                
                # Save and display
                save_message(
                    st.session_state.sheet_service,
                    st.session_state.client_name,
                    message,
                    response
                )
                
                # Show exchange
                with st.chat_message("user"):
                    st.write(message)
                with st.chat_message("assistant"):
                    st.write(response)
                    # Simple retry button
                    if st.button("🔄 Retry"):
                        new_response = chat(context, [], st.session_state.model_choice)
                        st.write("---\nNew response:")
                        st.write(new_response)
                        save_message(
                            st.session_state.sheet_service,
                            st.session_state.client_name,
                            message,
                            new_response
                        )
            except Exception as e:
                st.error(f"Error: {str(e)}")
    else:
        st.info("Select or enter client name to start")

if __name__ == "__main__":
    main() 
