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
    """Initialize the theme state in session state if it doesn't exist"""
    if 'current_theme' not in st.session_state:
        st.session_state.current_theme = 'orange_theme'

def toggle_theme():
    """Toggle between orange and gradient blue themes"""
    if st.session_state.current_theme == 'orange_theme':
        st.session_state.current_theme = 'gradient_blue_theme'
    else:
        st.session_state.current_theme = 'orange_theme'

def add_theme_toggle():
    """Add a small toggle button for theme switching"""
    initialize_theme_state()
    
    # Create a small container for the toggle button in the sidebar
    with st.sidebar:
        st.write("")  # Add some spacing
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.button("🎨 Switch Theme", key="theme_toggle", on_click=toggle_theme, use_container_width=True)
    
    # Load the current theme
    load_theme(st.session_state.current_theme) 