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
def get_chatbot_response(messages, model="gpt-4"):
    response = client.chat.completions.create(
        model=model,
        messages=messages
    )
    return response.choices[0].message.content

def chatbot_interface(key_suffix=""):
    st.markdown("<h2 class='glitch' data-text='Snow-AI'>Snow-AI</h2>", unsafe_allow_html=True)

    model = st.selectbox("Select AI Model", ["gpt-4o-mini", "gpt-4o", "chatgpt-4o-latest"], index=0, key=f"chatbot_model_select_{key_suffix}")

    if 'messages' not in st.session_state:
        st.session_state.messages = []

    st.markdown("""
    <style>
    .chat-container {
        height: 400px;
        overflow-y: auto;
        border: 1px solid #00ff00;
        padding: 10px;
        margin-bottom: 10px;
        background-color: rgba(0, 0, 0, 0.7);
        font-family: 'Courier New', monospace;
    }
    .user-message {
        color: #00ff00;
        text-align: right;
        margin: 5px 0;
        padding: 5px;
        background-color: rgba(0, 255, 0, 0.1);
        border-radius: 5px;
        text-shadow: 0 0 5px #00ff00;
    }
    .assistant-message {
        color: #00ffff;
        text-align: left;
        margin: 5px 0;
        padding: 5px;
        background-color: rgba(0, 255, 255, 0.1);
        border-radius: 5px;
        text-shadow: 0 0 5px #00ffff;
    }
    .glitch {
        position: relative;
        color: #00ff00;
        text-shadow: 0 0 5px #00ff00;
    }
    .glitch::before,
    .glitch::after {
        content: attr(data-text);
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
    }
    .glitch::before {
        left: 2px;
        text-shadow: -2px 0 #ff00ff;
        clip: rect(44px, 450px, 56px, 0);
        animation: glitch-anim 5s infinite linear alternate-reverse;
    }
    .glitch::after {
        left: -2px;
        text-shadow: -2px 0 #00ffff;
        clip: rect(44px, 450px, 56px, 0);
        animation: glitch-anim 5s infinite linear alternate-reverse;
    }
    @keyframes glitch-anim {
        0% { clip: rect(31px, 9999px, 94px, 0); }
        20% { clip: rect(70px, 9999px, 71px, 0); }
        40% { clip: rect(29px, 9999px, 83px, 0); }
        60% { clip: rect(38px, 9999px, 98px, 0); }
        80% { clip: rect(93px, 9999px, 67px, 0); }
        100% { clip: rect(22px, 9999px, 35px, 0); }
    }
    </style>
    """, unsafe_allow_html=True)

    chat_placeholder = st.empty()

    def display_chat():
        messages_html = "".join([
            f"<div class='user-message'><strong>You:</strong> {msg['content']}</div>" if msg['role'] == "user" 
            else f"<div class='assistant-message'><strong>Snow-AI:</strong> {msg['content']}</div>"
            for msg in st.session_state.messages
        ])
        chat_placeholder.markdown(f"<div class='chat-container' id='chat-container'>{messages_html}</div>", unsafe_allow_html=True)

    display_chat()

    def clear_input():
        st.session_state[f"chat_input_{key_suffix}"] = ""

    user_input = st.text_input("Enter your message", key=f"chat_input_{key_suffix}", on_change=clear_input)

    col1, col2, col3 = st.columns([1,1,1])
    with col1:
        send_button = st.button("Send", key=f"send_button_{key_suffix}")
    with col2:
        if st.button("Wipe Chat", key=f"wipe_chat_{key_suffix}"):
            st.session_state.messages = []
            display_chat()
    with col3:
        if st.button("Stop Generation", key=f"stop_generation_{key_suffix}"):
            # Implement stop functionality here
            pass

    if send_button and user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        display_chat()

        with st.spinner("Snow-AI is thinking..."):
            message_placeholder = st.empty()
            for full_response in get_chatbot_response_stream([
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.messages
            ], model):
                message_placeholder.markdown(f"<div class='assistant-message'><strong>Snow-AI:</strong> {full_response}</div>", unsafe_allow_html=True)

            st.session_state.messages.append({"role": "assistant", "content": full_response})
            display_chat()

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

# Modify this function to use the selected model
def get_chatbot_response_stream(messages, model="gpt-4o-mini"):
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True
    )
    full_response = ""
    for chunk in response:
        if chunk.choices[0].delta.content is not None:
            full_response += chunk.choices[0].delta.content
            yield full_response

# Streamlit app
def main():
    st.set_page_config(page_title="Snow-Blog", layout="wide")
    create_tables()

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
        background-color: #00ff00;
        color: black;
        box-shadow: 0 0 10px #00ff00;
    }
    .stButton>button:hover {
        background-color: #00cc00;
        box-shadow: 0 0 15px #00ff00;
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
                st.rerun()

            choice = st.radio("Navigation", ["Home", "Create Post", "Image Generation"])
            
            # Add chatbot to sidebar for logged-in users, but only if not in expanded view
            if not st.session_state.get('expand_chatbot', False):
                st.markdown("---")
                st.subheader("Snow-AI Chatbot")
                if st.button("Expand Snow-AI"):
                    st.session_state.expand_chatbot = True
                    st.rerun()
                chatbot_interface(key_suffix="sidebar")
        else:
            choice = st.radio("Navigation", ["Home", "Login", "Register"])

    # Main content
    if st.session_state.get('expand_chatbot', False):
        chatbot_interface(key_suffix="expanded")
        if st.button("Close Expanded Snow-AI"):
            st.session_state.expand_chatbot = False
            st.rerun()
    else:
        if choice == "Home":
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
