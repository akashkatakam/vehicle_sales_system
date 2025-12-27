import streamlit as st
from datetime import datetime, timedelta
from core.database import get_db
from core.data_manager import get_user_by_username

def check_login():
    """
    Manages user login, session timeout (1 hour), and logout.
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

        # Refresh timer
        st.session_state.login_time = datetime.now()

        # --- Sidebar User Info ---
        with st.sidebar:
            roles_list = st.session_state.get("roles", [])
            roles_disp = ", ".join(roles_list)
            st.success(f"User: **{roles_disp}**")

            access_branches = st.session_state.get("accessible_branches", [])
            if "ALL" in access_branches:
                st.info("Access: **All Branches**")
            else:
                st.info(f"Access: **{len(access_branches)} Branch(es)**")

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
                    st.session_state["logged_in"] = True

                    # Parse Roles
                    raw_roles = user.role if user.role else ""
                    st.session_state["roles"] = [r.strip() for r in raw_roles.split(",") if r.strip()]

                    # Parse Branches
                    raw_branches = user.Branch_ID if user.Branch_ID else ""
                    if "ALL" in raw_branches.upper():
                        st.session_state["accessible_branches"] = ["ALL"]
                    else:
                        st.session_state["accessible_branches"] = [
                            b.strip() for b in raw_branches.split(",") if b.strip()
                        ]

                    st.session_state["username"] = user.username
                    st.session_state["login_time"] = datetime.now()
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
            finally:
                db.close()
    return False