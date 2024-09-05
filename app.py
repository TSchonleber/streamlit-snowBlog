import streamlit as st
import psycopg2
import os
from dotenv import load_dotenv
from streamlit_option_menu import option_menu
import bcrypt
from openai import OpenAI
import streamlit.components.v1 as components
from google.cloud import storage
import sqlalchemy
import pg8000
import uuid

# Import the functions from other files
from image_generation import image_generation_page

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
print(f"OpenAI client initialized with API key: {client.api_key[:5]}...")  # Debug print, only show first 5 characters

# Check if OPENAI_API_KEY is set
if "OPENAI_API_KEY" not in os.environ:
    st.error("OPENAI_API_KEY is not set in the environment variables. Please set it to use the chatbot feature.")
else:
    print(f"OPENAI_API_KEY is set: {os.environ['OPENAI_API_KEY'][:5]}...")  # Debug print, only show first 5 characters

# Initialize Google Cloud Storage client
storage_client = storage.Client()
bucket_name = "streamlit-blog"  # Your actual bucket name
bucket = storage_client.bucket(bucket_name)

# Database connection
def get_db_connection():
    db_config = {
        "database": os.getenv("DB_NAME"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASS"),
        "host": "127.0.0.1",  # Use localhost when using Cloud SQL proxy
        "port": 5432
    }
    
    engine = sqlalchemy.create_engine(
        "postgresql+pg8000://",
        creator=lambda: pg8000.connect(**db_config)
    )
    return engine.connect()

# Create tables if they don't exist
def create_tables():
    conn = get_db_connection()
    conn.execute(sqlalchemy.text("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username VARCHAR(50) UNIQUE NOT NULL,
        password VARCHAR(255) NOT NULL
    )
    """))
    conn.execute(sqlalchemy.text("""
    CREATE TABLE IF NOT EXISTS posts (
        id SERIAL PRIMARY KEY,
        title VARCHAR(100) NOT NULL,
        content TEXT NOT NULL,
        author_id INTEGER REFERENCES users(id),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """))
    
    # Add image_url column if it doesn't exist
    conn.execute(sqlalchemy.text("""
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='posts' AND column_name='image_url') THEN
            ALTER TABLE posts ADD COLUMN image_url TEXT;
        END IF;
    END $$;
    """))
    
    conn.execute(sqlalchemy.text("""
    CREATE TABLE IF NOT EXISTS conversations (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        title VARCHAR(100) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """))
    
    conn.execute(sqlalchemy.text("""
    CREATE TABLE IF NOT EXISTS chat_messages (
        id SERIAL PRIMARY KEY,
        conversation_id INTEGER REFERENCES conversations(id),
        role VARCHAR(10) NOT NULL,
        content TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """))
    
    conn.commit()
    conn.close()

# Function to upload file to Google Cloud Storage
def upload_to_gcs(file):
    if file is not None:
        file_extension = os.path.splitext(file.name)[1]
        file_name = f"{uuid.uuid4()}{file_extension}"
        blob = bucket.blob(file_name)
        blob.upload_from_string(file.getvalue(), content_type=file.type)
        return f"https://storage.googleapis.com/{bucket_name}/{file_name}"
    return None

# Modify create_new_post function to handle file uploads
def create_new_post(title, content, author_id, uploaded_file=None):
    image_url = upload_to_gcs(uploaded_file) if uploaded_file else None
    conn = get_db_connection()
    conn.execute(sqlalchemy.text(
        "INSERT INTO posts (title, content, author_id, image_url) VALUES (:title, :content, :author_id, :image_url)"
    ), {"title": title, "content": content, "author_id": author_id, "image_url": image_url})
    conn.commit()
    conn.close()

# User authentication
def authenticate_user(username, password):
    conn = get_db_connection()
    result = conn.execute(sqlalchemy.text(
        "SELECT id, password FROM users WHERE username = :username"
    ), {"username": username}).fetchone()
    conn.close()
    if result and bcrypt.checkpw(password.encode('utf-8'), result[1].encode('utf-8')):
        return result[0]  # Return user id
    return None

# Display recent posts
def get_recent_posts():
    conn = get_db_connection()
    posts = conn.execute(sqlalchemy.text("""
    SELECT p.id, p.title, p.content, u.username, p.created_at, p.image_url, p.author_id
    FROM posts p 
    JOIN users u ON p.author_id = u.id 
    ORDER BY p.created_at DESC 
    LIMIT 5
    """)).fetchall()
    conn.close()
    return posts

# AI Chatbot
def get_chatbot_response(messages, model="gpt-4o-mini"):
    try:
        print(f"Sending request to OpenAI with model: {model}")  # Debug print
        print(f"Messages: {messages}")  # Debug print
        response = client.chat.completions.create(
            model=model,
            messages=messages
        )
        return response.choices[0].message.content
    except Exception as e:
        error_message = f"Error in get_chatbot_response: {str(e)}"
        print(error_message)  # Debug print
        raise Exception(error_message)

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
                response = get_chatbot_response(st.session_state.messages, model)
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

def create_conversation(user_id, title):
    conn = get_db_connection()
    result = conn.execute(sqlalchemy.text(
        "INSERT INTO conversations (user_id, title) VALUES (:user_id, :title) RETURNING id"
    ), {"user_id": user_id, "title": title})
    conversation_id = result.fetchone()[0]
    conn.commit()
    conn.close()
    return conversation_id

def get_user_conversations(user_id):
    conn = get_db_connection()
    conversations = conn.execute(sqlalchemy.text(
        "SELECT id, title FROM conversations WHERE user_id = :user_id ORDER BY created_at DESC"
    ), {"user_id": user_id}).fetchall()
    conn.close()
    return conversations

def delete_conversation(conversation_id):
    conn = get_db_connection()
    conn.execute(sqlalchemy.text("DELETE FROM chat_messages WHERE conversation_id = :conversation_id"), {"conversation_id": conversation_id})
    conn.execute(sqlalchemy.text("DELETE FROM conversations WHERE id = :conversation_id"), {"conversation_id": conversation_id})
    conn.commit()
    conn.close()

def save_chat_message(conversation_id, role, content):
    conn = get_db_connection()
    conn.execute(sqlalchemy.text(
        "INSERT INTO chat_messages (conversation_id, role, content) VALUES (:conversation_id, :role, :content)"
    ), {"conversation_id": conversation_id, "role": role, "content": content})
    conn.commit()
    conn.close()

def get_chat_history(conversation_id):
    conn = get_db_connection()
    messages = conn.execute(sqlalchemy.text(
        "SELECT role, content FROM chat_messages WHERE conversation_id = :conversation_id ORDER BY timestamp ASC"
    ), {"conversation_id": conversation_id}).fetchall()
    conn.close()
    return [{"role": msg[0], "content": msg[1]} for msg in messages]

# Streamlit app
def main():
    st.set_page_config(page_title="Snow-Blog", layout="wide")
    create_tables()

    # Verify API key and test API call
    try:
        test_response = get_chatbot_response([{"role": "user", "content": "Hello, are you working?"}], "gpt-4o-mini")
        st.success(f"API test successful. Response: {test_response}")
        print(f"API test response: {test_response}")  # Debug print
    except Exception as e:
        st.error(f"Error testing API: {str(e)}")
        print(f"Error testing API: {str(e)}")  # Debug print
        return  # Exit the function if API test fails

    # Add cyberpunk theme to the entire app
    st.markdown("""
    <style>
    body {
        background-color: #0a0a0a;
        color: #00ff00;
        font-family: 'Courier New', monospace;
    }
    .stApp {
        background-image: linear-gradient(45deg, #0a0a0a 25%, #1a1a1a 25%, #1a1a1a 50%, #0a0a0a 50%, #0a0a0a 75%, #1a1a1a 75%, #1a1a1a 100%);
        background-size: 40px 40px;
    }
    h1, h2, h3 {
        color: #00ff00;
        text-shadow: 0 0 5px #00ff00;
    }
    .stButton>button {
        background-color: #000000;
        color: #00ff00;
        border: 2px solid #00ff00;
        box-shadow: 0 0 10px #00ff00;
        font-family: 'Courier New', monospace;
        font-weight: bold;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        background-color: #00ff00;
        color: #000000;
        box-shadow: 0 0 20px #00ff00;
    }
    .stTextInput>div>div>input {
        background-color: #1e1e1e;
        color: #00ff00;
        border-color: #00ff00;
    }
    .stTextArea textarea {
        background-color: #1e1e1e;
        color: #00ff00;
        border-color: #00ff00;
    }
    .stSelectbox>div>div>select {
        background-color: #1e1e1e;
        color: #00ff00;
        border-color: #00ff00;
    }
    .chat-container {
        border: 2px solid #00ff00;
        background-color: rgba(0, 0, 0, 0.7);
        padding: 10px;
        margin-bottom: 10px;
        height: 400px;
        overflow-y: auto;
    }
    .user-message {
        background-color: rgba(0, 255, 0, 0.1);
        padding: 5px;
        margin: 5px 0;
        border-radius: 5px;
        text-align: right;
    }
    .assistant-message {
        background-color: rgba(0, 255, 255, 0.1);
        padding: 5px;
        margin: 5px 0;
        border-radius: 5px;
        text-align: left;
    }
    </style>
    """, unsafe_allow_html=True)

    st.title("Snow-Blog")

    # Sidebar for navigation, login status, and chatbot
    with st.sidebar:
        if 'logged_in' in st.session_state and st.session_state['logged_in']:
            st.success(f"Logged in as: {st.session_state['username']}")
            if st.button("Logout"):
                st.session_state['logged_in'] = False
                st.session_state.pop('user_id', None)
                st.session_state.pop('username', None)
                st.session_state.pop('conversation_id', None)
                st.session_state.pop('messages', None)
                st.session_state.pop('conversations', None)
                st.session_state.pop('selected_conversation', None)
                st.rerun()

            choice = st.radio("Navigation", ["Home", "Create Post", "Image Generation", "Chatbot"])
            
        else:
            choice = st.radio("Navigation", ["Home", "Login", "Register"])

    # Main content
    if choice == "Chatbot" and st.session_state.get('logged_in', False):
        chatbot_interface()
    elif choice == "Chatbot":
        st.warning("Please log in to use the chatbot and manage your conversations.")
    elif choice == "Home":
        st.subheader("Recent Posts")
        posts = get_recent_posts()
        for post in posts:
            st.write(f"**{post[1]}** by {post[3]} on {post[4]}")
            st.write(post[2][:200] + "..." if len(post[2]) > 200 else post[2])
            if post[5]:  # If there's an image
                st.image(post[5], width=200)
            st.write("---")

    elif choice == "Login":
        st.subheader("Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type='password')
        if st.button("Login"):
            user_id = authenticate_user(username, password)
            if user_id:
                st.success("Logged in successfully")
                st.session_state['logged_in'] = True
                st.session_state['user_id'] = user_id
                st.session_state['username'] = username
                st.rerun()
            else:
                st.error("Incorrect username or password")

    elif choice == "Register":
        st.subheader("Create New Account")
        new_user = st.text_input("Username")
        new_password = st.text_input("Password", type='password')
        if st.button("Register"):
            conn = get_db_connection()
            hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
            try:
                conn.execute(sqlalchemy.text(
                    "INSERT INTO users (username, password) VALUES (:username, :password)"
                ), {"username": new_user, "password": hashed_password.decode('utf-8')})
                conn.commit()
                st.success("Account created successfully")
            except sqlalchemy.exc.IntegrityError:
                st.error("Username already exists")
            finally:
                conn.close()

    elif choice == "Create Post" and st.session_state.get('logged_in', False):
        st.subheader("Create a New Blog Post")
        post_title = st.text_input("Post Title")
        
        st.markdown("Post Content (Markdown supported)")
        st.markdown("Tips:")
        st.markdown("- To add an image: `![alt text](image_url)`")
        st.markdown("- To add a video: `![alt text](video_url)`")
        st.markdown("- To add a link: `[link text](url)`")
        
        post_content = st.text_area("Post Content", height=300, label_visibility="collapsed")
        
        uploaded_file = st.file_uploader("Upload an image (optional)", type=["png", "jpg", "jpeg"])
        if uploaded_file is not None:
            st.image(uploaded_file, caption="Uploaded Image")

        if st.button("Submit Post"):
            if post_title and post_content:
                create_new_post(post_title, post_content, st.session_state['user_id'], uploaded_file)
                st.success("Post created successfully!")
            else:
                st.warning("Please fill in both title and content.")

    elif choice == "Image Generation" and st.session_state.get('logged_in', False):
        image_generation_page()

    else:
        st.warning("Please log in to access this feature.")

if __name__ == "__main__":
    main()
