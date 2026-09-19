"""Deep teal, warm gold and locally bundled MaruBuri."""
from pathlib import Path
import streamlit as st
from core.law_galaxy import _font_styles


def inject_global_css() -> None:
    # Keep the bundled OFL license in assets/ and standalone exports.
    # Markdown sanitization removes `hidden` from the export's license block.
    fonts = _font_styles()
    st.markdown(fonts[fonts.index('<style>'):], unsafe_allow_html=True)
    st.markdown('<style>' + (Path(__file__).parent/'assets/atlas.css').read_text(encoding='utf-8') + '</style>', unsafe_allow_html=True)
