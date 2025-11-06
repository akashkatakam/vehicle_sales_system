import streamlit as st
from datetime import datetime, timedelta
from database import get_db
from data_manager import get_user_by_username
import models

def check_login():
    """
    Manages user login, session timeout (1 hour), and logout.
    Returns True if a valid, active session exists.
    """
    if st.session_state.get("logged_in", False):
        # --- Session Timeout Check ---
        if "login_time" in st.session_state:
            elapsed = datetime.now() - st.session_state.login_time
            if elapsed > timedelta(hours=1):
                st.session_state.clear()
                st.warning("Session expired due to inactivity. Please log in again.")
                st.rerun()
                return False
        
        # Refresh timer on every interaction
        st.session_state.login_time = datetime.now()
        
        # --- Sidebar User Info ---
        with st.sidebar:
            st.success(f"User: **{st.session_state.role}**")
            if st.session_state.role == "Back Office":
                st.info(f"Branch: **{st.session_state.branch_name}**")
            
            if st.button("Logout", type="primary", use_container_width=True):
                st.session_state.clear()
                st.rerun()
        return True

    # --- Login Form ---
    with st.form("login_form"):
        st.header("🔐 Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        
        if st.form_submit_button("Login", type="primary", use_container_width=True):
            db = next(get_db())
            try:
                user = get_user_by_username(db, username)
                if user and user.verify_password(password):
                    # Set Session State
                    st.session_state["logged_in"] = True
                    st.session_state["role"] = user.role
                    st.session_state["user_branch_id"] = user.Branch_ID 
                    st.session_state["login_time"] = datetime.now()
                    
                    if user.Branch_ID:
                        branch = db.query(models.Branch).filter(models.Branch.Branch_ID == user.Branch_ID).first()
                        st.session_state["branch_name"] = branch.Branch_Name if branch else "N/A"
                    else:
                        st.session_state["branch_name"] = "All Branches"
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
            finally:
                db.close()
    return False