import streamlit as st
from pathlib import Path

def load_theme(theme_name):
    """
    Load a theme CSS file and apply it to the Streamlit app
    
    Args:
        theme_name (str): Name of the theme file without .css extension
    """
    theme_path = Path(__file__).parent.parent / 'themes' / f'{theme_name}.css'
    
    try:
        with open(theme_path, 'r') as f:
            st.markdown(f"""
                <style>
                {f.read()}
                </style>
            """, unsafe_allow_html=True)
    except FileNotFoundError:
        st.error(f"Theme '{theme_name}' not found")

def initialize_theme_state():
    """Initialize the theme state and character state in session state if they don't exist"""
    if 'current_theme' not in st.session_state:
        st.session_state.current_theme = 'orange_theme'
    if 'character_emoji' not in st.session_state:
        st.session_state.character_emoji = '👨‍💼'
    if 'character_name' not in st.session_state:
        st.session_state.character_name = 'Fred'

def toggle_theme():
    """Toggle between orange and gradient blue themes"""
    if st.session_state.current_theme == 'orange_theme':
        st.session_state.current_theme = 'gradient_blue_theme'
    else:
        st.session_state.current_theme = 'orange_theme'

def add_theme_toggle():
    """Add a small toggle button for theme switching and character indicator"""
    initialize_theme_state()
    
    # Create a small container for the toggle button and character indicator in the sidebar
    with st.sidebar:
        st.write("")  # Add some spacing
        # Use custom HTML/CSS for better alignment
        st.markdown(
            f"""
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 10px;">
                <span style="font-size: 1.2em;">{st.session_state.character_emoji}</span>
                <span style="flex-grow: 1;">{st.session_state.character_name}</span>
                <span style="font-size: 1.2em; cursor: pointer;" title="Toggle theme">
                    {"🌅" if st.session_state.current_theme == 'orange_theme' else "🌊"}
                </span>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        # Hidden button for theme toggle functionality
        if st.button("Toggle Theme", key="theme_toggle", on_click=toggle_theme, help="Toggle theme"):
            pass
        
        # Hide the button using custom CSS
        st.markdown("""
            <style>
            [data-testid="stButton"] {
                display: none;
            }
            </style>
            """, unsafe_allow_html=True)
    
    # Load the current theme
    load_theme(st.session_state.current_theme) 