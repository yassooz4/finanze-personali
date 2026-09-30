"""Password gate for every page, before any financial data is accessed."""
import hmac
import secrets

import streamlit as st

_SESSION_KEY = secrets.token_bytes(32)


def logout():
    """Discard authentication and any financial widget state."""
    st.session_state.clear()


def require_login():
    try:
        password = st.secrets["accesso"]["password"]
    except (KeyError, FileNotFoundError):
        password = None
    if not isinstance(password, str) or not password.strip():
        logout()
        st.title("🔒 Accesso protetto")
        st.error('Configura nei Secrets di Streamlit la sezione [accesso] con password = "la tua password".')
        st.stop()

    # A password change invalidates already authenticated sessions.
    marker = hmac.digest(_SESSION_KEY, password.encode("utf-8"), "sha256")
    current = st.session_state.get("_login_verified")
    if isinstance(current, bytes) and hmac.compare_digest(current, marker):
        return

    def verify():
        attempt = st.session_state.pop("_login_password", "")
        if hmac.compare_digest(attempt.encode("utf-8"), password.encode("utf-8")):
            st.session_state.clear()
            st.session_state["_login_verified"] = marker
        else:
            st.session_state["_login_error"] = True

    _, center, _ = st.columns([1, 2, 1])
    with center:
        st.markdown("## 🔒 Il tuo spazio personale")
        st.caption("Inserisci la password per accedere alle tue finanze.")
        with st.form("login", clear_on_submit=True):
            st.text_input("Password", type="password", key="_login_password")
            st.form_submit_button("Accedi", type="primary", on_click=verify, width="stretch")
        if st.session_state.get("_login_error"):
            st.error("Password non corretta.")
    st.stop()
