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