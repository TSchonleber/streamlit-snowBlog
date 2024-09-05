import streamlit as st
from openai import OpenAI
import os

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def analyze_sentiment(user_input, model):
    """Analyze the sentiment of the user input using OpenAI."""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Analyze the sentiment of the following text. Respond with only 'positive', 'neutral', or 'negative'."},
                {"role": "user", "content": user_input}
            ],
            max_tokens=10
        )
        sentiment = response.choices[0].message.content.strip().lower()
        return sentiment
    except Exception as e:
        print(f"Error in analyze_sentiment: {str(e)}")
        return "neutral"

def enhanced_chatbot_response(user_input, history, model):
    """Generate a chatbot response based on user input, sentiment, and rich responses."""
    sentiment = analyze_sentiment(user_input, model)

    # Check for specific keywords for rich responses
    if "loop" in user_input.lower():
        response = "It looks like you're asking about loops in Python. Here's a useful diagram on loops:\n\n"
        response += "![Python Loop Diagram](https://example.com/loop-diagram.png)\n"
        response += "You can also check out this [detailed guide on Python loops](https://docs.python.org/3/tutorial/controlflow.html#for-statements)."
    elif "video" in user_input.lower():
        response = "It sounds like you might prefer a video explanation. Here's a helpful tutorial:\n\n"
        response += "[Watch Python Loops Tutorial](https://www.youtube.com/watch?v=6iF8Xb7Z3wQ)"
    else:
        # Default sentiment-driven responses
        if sentiment == "positive":
            context = "The user seems positive. Respond in an upbeat manner."
        elif sentiment == "negative":
            context = "The user seems negative. Respond with empathy and offer support."
        else:
            context = "Provide a balanced and informative response."

        messages = history + [
            {"role": "system", "content": context},
            {"role": "user", "content": user_input}
        ]

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages
            )
            return response.choices[0].message.content
        except Exception as e:
            error_message = f"Error in enhanced_chatbot_response: {str(e)}"
            print(error_message)  # Debug print
            return f"I apologize, but I encountered an error: {str(e)}"

    return response

def track_sentiment(user_input, history, model):
    """Track the sentiment throughout the conversation."""
    sentiment = analyze_sentiment(user_input, model)

    if 'sentiment_history' not in st.session_state:
        st.session_state.sentiment_history = []

    st.session_state.sentiment_history.append(sentiment)

    negative_count = st.session_state.sentiment_history.count('negative')

    if negative_count > 3:
        context = "The user has been consistently negative. Respond with extra empathy and support."
    else:
        context = ""

    response = enhanced_chatbot_response(user_input, history + [{"role": "system", "content": context}], model)
    return response

def set_user_preferences():
    """Allows the user to customize their experience."""
    st.sidebar.title("User Preferences")
    tone = st.sidebar.selectbox("Select Tone:", ["Casual", "Formal"])
    style = st.sidebar.radio("Learning Style:", ["Quick Responses", "Detailed Explanations"])
    st.session_state['tone'] = tone
    st.session_state['learning_style'] = style

def personalized_response(user_input, history, model):
    """Generate a chatbot response based on user preferences and sentiment."""
    response = track_sentiment(user_input, history, model)

    if st.session_state.get('tone') == "Formal":
        response = "Here is a formal explanation: " + response
    else:
        response = "Here's a quick explanation: " + response

    if st.session_state.get('learning_style') == "Detailed Explanations":
        response += "\n\nI can go into more detail if you'd like!"
    
    return response

def chatbot_interface(key_suffix=""):
    st.markdown("<h2 class='glitch' data-text='Snow-AI'>Snow-AI</h2>", unsafe_allow_html=True)

    if 'user_id' not in st.session_state:
        st.warning("Please log in to use the chatbot and manage your conversations.")
        return

    user_id = st.session_state['user_id']

    # Initialize session state variables
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    if 'conversations' not in st.session_state:
        st.session_state.conversations = get_user_conversations(user_id)
    if 'selected_conversation' not in st.session_state:
        st.session_state.selected_conversation = "New Conversation"

    set_user_preferences()  # Sidebar for user preferences

    # Conversation management
    conversation_titles = [conv[1] for conv in st.session_state.conversations]
    conversation_titles.insert(0, "New Conversation")

    def on_conversation_change():
        st.session_state.messages = []
        if st.session_state.selected_conversation != "New Conversation":
            conversation_id = next(conv[0] for conv in st.session_state.conversations if conv[1] == st.session_state.selected_conversation)
            st.session_state.conversation_id = conversation_id
            st.session_state.messages = get_chat_history(conversation_id)

    selected_conversation = st.selectbox("Select Conversation", conversation_titles, 
                                         key="conversation_select", 
                                         on_change=on_conversation_change)

    if selected_conversation == "New Conversation":
        with st.form(key="new_conversation_form"):
            new_conversation_title = st.text_input("Enter a title for the new conversation")
            submit_new_conv = st.form_submit_button("Create New Conversation")
            if submit_new_conv and new_conversation_title:
                conversation_id = create_conversation(user_id, new_conversation_title)
                st.session_state.conversation_id = conversation_id
                st.session_state.messages = []
                st.session_state.conversations = get_user_conversations(user_id)
                st.session_state.selected_conversation = new_conversation_title
                st.success(f"New conversation '{new_conversation_title}' created!")

    if st.button("Delete Conversation", key=f"delete_conversation_{key_suffix}"):
        if selected_conversation != "New Conversation":
            delete_conversation(st.session_state.conversation_id)
            st.session_state.conversations = get_user_conversations(user_id)
            st.session_state.selected_conversation = "New Conversation"
            st.session_state.messages = []
            st.success(f"Conversation '{selected_conversation}' deleted!")

    model = st.selectbox("Select AI Model", ["gpt-4o-mini", "gpt-4o", "chatgpt-4o-latest"], index=0, key=f"chatbot_model_select_{key_suffix}")

    chat_placeholder = st.empty()

    def display_chat():
        messages_html = "".join([
            f"<div class='user-message'><strong>You:</strong> {msg['content']}</div>" if msg['role'] == "user" 
            else f"<div class='assistant-message'><strong>Snow-AI:</strong> {msg['content']}</div>"
            for msg in st.session_state.messages
        ])
        chat_placeholder.markdown(f"<div class='chat-container' id='chat-container'>{messages_html}</div>", unsafe_allow_html=True)

    display_chat()

    with st.form(key="chat_input_form"):
        user_input = st.text_input("Enter your message", key=f"chat_input_{key_suffix}")
        send_button = st.form_submit_button("Send")

    if send_button and user_input and 'conversation_id' in st.session_state:
        st.session_state.messages.append({"role": "user", "content": user_input})
        save_chat_message(st.session_state.conversation_id, "user", user_input)
        display_chat()

        with st.spinner("Snow-AI is thinking..."):
            try:
                response = personalized_response(user_input, st.session_state.messages, model)
                st.session_state.messages.append({"role": "assistant", "content": response})
                save_chat_message(st.session_state.conversation_id, "assistant", response)
                display_chat()
            except Exception as e:
                error_message = f"Error in chatbot_interface: {str(e)}"
                print(error_message)  # Debug print
                st.error(error_message)

    # Scroll to bottom after loading
    st.components.v1.html(
        """
        <script>
            var chatContainer = document.getElementById('chat-container');
            chatContainer.scrollTop = chatContainer.scrollHeight;
        </script>
        """,
        height=0
    )

# Import necessary functions from app.py
from app import (
    get_user_conversations,
    create_conversation,
    delete_conversation,
    save_chat_message,
    get_chat_history
)

if __name__ == "__main__":
    chatbot_interface()