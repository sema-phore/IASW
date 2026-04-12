from pathlib import Path

import streamlit as st

_PAGES_DIR = Path(__file__).parent / "pages"

pg = st.navigation(
    [
        st.Page(_PAGES_DIR / "staff_intake.py", title="Staff Intake", icon="📋"),
        st.Page(_PAGES_DIR / "checker_ui.py", title="Checker Review", icon="🔍"),
    ]
)
pg.run()
