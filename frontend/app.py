import os

import requests
import streamlit as st

st.set_page_config(page_title="ShopFlow AI", page_icon="🛍️", layout="wide")

API_URL = os.getenv("SHOPFLOW_API_URL", "http://localhost:8000").rstrip("/")


def api_request(method: str, path: str, token: str | None = None, **kwargs):
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = requests.request(
            method,
            f"{API_URL}{path}",
            headers=headers,
            timeout=60,
            **kwargs,
        )
    except requests.RequestException as exc:
        return None, f"Cannot reach API: {exc}"

    try:
        data = response.json()
    except ValueError:
        data = {"detail": response.text or "Unexpected API response"}

    if not response.ok:
        detail = data.get("detail", "Request failed") if isinstance(data, dict) else str(data)
        return None, f"HTTP {response.status_code}: {detail}"

    return data, None


def logout():
    for key in ("token", "user", "conversation_id", "messages"):
        st.session_state.pop(key, None)
    st.rerun()


def login_screen():
    st.title("🛍️ ShopFlow AI")
    st.caption("AI-powered customer support for e-commerce")

    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login", use_container_width=True)

    if submitted:
        if not email or not password:
            st.error("Enter your email and password.")
            return

        data, error = api_request(
            "POST",
            "/auth/login",
            json={"email": email, "password": password},
        )
        if error:
            st.error(error)
            return

        st.session_state.token = data["access_token"]
        user, user_error = api_request("GET", "/auth/me", token=st.session_state.token)
        st.session_state.user = user if not user_error else {"email": email}
        st.session_state.messages = []
        st.rerun()


def create_conversation():
    data, error = api_request(
        "POST",
        "/conversations/",
        token=st.session_state.token,
        json={"channel": "web"},
    )
    if error:
        st.error(error)
        return False

    st.session_state.conversation_id = data["conversation_id"]
    st.session_state.messages = []
    return True


def send_message(message: str):
    conversation_id = st.session_state.get("conversation_id")
    if not conversation_id and not create_conversation():
        return

    data, error = api_request(
        "POST",
        f"/conversations/{st.session_state.conversation_id}/messages",
        token=st.session_state.token,
        json={"message": message},
    )
    if error:
        st.error(error)
        return

    st.session_state.messages.append({"role": "user", "content": message})

    if data.get("requires_confirmation"):
        confirmation = data.get("confirmation_request", {})
        question = confirmation.get("question", "Please confirm this action.")
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": question,
                "confirmation": confirmation,
            }
        )
    else:
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": data.get("answer", "No response returned."),
                "intent": data.get("intent"),
            }
        )


def chat_page():
    st.title("💬 AI Support")
    st.caption("Ask about policies, orders, shipments, returns, refunds, or support.")

    if not st.session_state.get("conversation_id"):
        if st.button("Start new conversation", type="primary"):
            create_conversation()
            st.rerun()

    for message in st.session_state.get("messages", []):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("intent"):
                st.caption(f"Intent: {message['intent']}")

            confirmation = message.get("confirmation")
            if confirmation:
                st.warning("This action requires your confirmation.")
                if st.button("Confirm", key=f"confirm_{len(st.session_state.messages)}"):
                    send_message("Yes, I confirm this action.")
                    st.rerun()

    prompt = st.chat_input("How can I help you?")
    if prompt:
        send_message(prompt)
        st.rerun()


def dashboard_page():
    st.title("🏠 Dashboard")

    health, error = api_request("GET", "/")
    if error:
        st.error("API: Offline")
    else:
        st.success(f"API: {health.get('status', 'healthy').title()}")

    user = st.session_state.get("user", {})
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Customer", user.get("name", "Authenticated user"))
    with col2:
        st.metric("Conversation", "Active" if st.session_state.get("conversation_id") else "None")

    st.info("Use AI Support to test your Phase 1–7 agent end-to-end.")


def main_app():
    with st.sidebar:
        st.title("ShopFlow AI")
        user = st.session_state.get("user", {})
        st.caption(user.get("email", "Authenticated"))

        page = st.radio("Navigation", ["Dashboard", "AI Support"])

        st.divider()
        st.caption(f"API: {API_URL}")
        if st.button("Logout", use_container_width=True):
            logout()

    if page == "Dashboard":
        dashboard_page()
    else:
        chat_page()


if "token" not in st.session_state:
    login_screen()
else:
    main_app()
