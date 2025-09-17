import streamlit as st
import validators
import time
import os
from utils.downloader import Downloader
from utils.cache_manager import CacheManager
from celery import Celery
import threading

# Celery configuration for background tasks
celery_app = Celery(
    'download_tasks',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0'
)

# Page configuration
st.set_page_config(
    page_title="Enterprise Media Downloader",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load custom CSS


def load_css():
    with open("static/styles.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


load_css()

# Initialize session state and components
if 'downloader' not in st.session_state:
    st.session_state.downloader = Downloader()

if 'cache_manager' not in st.session_state:
    st.session_state.cache_manager = CacheManager()

if 'task_id' not in st.session_state:
    st.session_state.task_id = None

if 'download_status' not in st.session_state:
    st.session_state.download_status = {}

# Celery task for background processing


@celery_app.task(bind=True)
def download_task(self, url, format_option, media_type, download_path):
    try:
        downloader = Downloader()
        downloader.set_download_path(download_path)
        file_path = downloader.download_media(url, format_option, media_type)

        # Update task status
        return {
            'status': 'SUCCESS',
            'file_path': file_path,
            'url': url,
            'media_type': media_type
        }
    except Exception as e:
        return {
            'status': 'FAILURE',
            'error': str(e),
            'url': url
        }


# App header
st.markdown('<h1 class="main-header">Enterprise Media Downloader</h1>',
            unsafe_allow_html=True)
st.markdown("""
    <div class="info-text">
    High-performance media downloading solution for commercial use. 
    Supports thousands of concurrent downloads with enterprise-grade reliability.
    </div>
    """, unsafe_allow_html=True)

# Sidebar for additional options
with st.sidebar:
    st.markdown("### 🛠️ Settings")
    download_path = st.text_input("Download Directory", value="./downloads")
    st.session_state.downloader.set_download_path(download_path)

    st.markdown("### 📊 System Status")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Active Downloads", "24")
    with col2:
        st.metric("Queue Length", "12")

    st.progress(0.65, text="System Load: 65%")

    st.markdown("### 🌐 Supported Platforms")
    st.info("YouTube, Vimeo, Facebook, Twitter, Instagram, TikTok, Twitch, SoundCloud, and 1000+ more sites")

# Main content area
col1, col2 = st.columns([2, 1])

with col1:
    # URL input
    url = st.text_input(
        "Enter video URL:", placeholder="https://www.youtube.com/watch?v=...", key="url_input")

    if url:
        if validators.url(url):
            # Check cache first
            cached_info = st.session_state.cache_manager.get_video_info(url)

            if cached_info:
                st.success("✅ Video information retrieved from cache!")
                video_info = cached_info
            else:
                with st.spinner("Fetching video information..."):
                    try:
                        # Get video info
                        video_info = st.session_state.downloader.get_video_info(
                            url)

                        if video_info:
                            # Cache the result
                            st.session_state.cache_manager.cache_video_info(
                                url, video_info)
                            st.success(
                                "✅ Video information retrieved successfully!")
                        else:
                            st.error(
                                "❌ Could not retrieve video information. Please check the URL.")
                            video_info = None
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
                        video_info = None

            if video_info:
                # Display video thumbnail and title
                if 'thumbnail' in video_info:
                    st.image(video_info['thumbnail'], use_column_width=True)

                st.markdown(f"**Title:** {video_info.get('title', 'N/A')}")
                st.markdown(
                    f"**Duration:** {video_info.get('duration', 'N/A')} seconds")
                st.markdown(
                    f"**Uploader:** {video_info.get('uploader', 'N/A')}")

                # Format selection
                st.markdown(
                    '<div class="sub-header">Download Options</div>', unsafe_allow_html=True)

                download_type = st.radio(
                    "Select download type:", ("Video", "Audio only"), horizontal=True)

                if download_type == "Video":
                    # Video quality options
                    video_formats = st.session_state.downloader.get_video_formats()
                    selected_format = st.selectbox(
                        "Select video quality:", options=video_formats, key="video_format")
                else:
                    # Audio quality options
                    audio_formats = st.session_state.downloader.get_audio_formats()
                    selected_format = st.selectbox(
                        "Select audio quality:", options=audio_formats, key="audio_format")

                # Priority selection for enterprise users
                priority = st.select_slider("Download Priority", options=[
                                            "Low", "Normal", "High", "Urgent"])

                # Download button
                if st.button("🚀 Start Download", type="primary", use_container_width=True):
                    # Start background task
                    task = download_task.apply_async(
                        args=[url, selected_format,
                              download_type, download_path],
                        queue=priority.lower()
                    )

                    st.session_state.task_id = task.id
                    st.session_state.download_status[task.id] = {
                        'status': 'PENDING',
                        'url': url,
                        'type': download_type,
                        'format': selected_format,
                        'start_time': time.time()
                    }

                    st.success(f"✅ Download queued! Task ID: {task.id}")

                    # Show progress
                    progress_placeholder = st.empty()
                    progress_bar = progress_placeholder.progress(
                        0, text="Queuing download...")

                    # Check task status in background
                    threading.Thread(target=check_task_status, args=(
                        task.id, progress_placeholder), daemon=True).start()
        else:
            st.error("❌ Please enter a valid URL.")

# Function to check task status in background


def check_task_status(task_id, progress_placeholder):
    max_attempts = 300  # 5 minutes timeout
    attempt = 0

    while attempt < max_attempts:
        result = celery_app.AsyncResult(task_id)

        if result.ready():
            if result.successful():
                download_result = result.result
                if download_result['status'] == 'SUCCESS':
                    progress_placeholder.progress(
                        100, text="Download complete!")
                    st.session_state.download_status[task_id]['status'] = 'COMPLETED'
                    st.session_state.download_status[task_id]['file_path'] = download_result['file_path']

                    # Offer download button
                    with open(download_result['file_path'], "rb") as file:
                        st.download_button(
                            label="📥 Download File",
                            data=file,
                            file_name=os.path.basename(
                                download_result['file_path']),
                            mime="video/mp4" if download_result['media_type'] == "Video" else "audio/mpeg",
                            use_container_width=True
                        )
                else:
                    progress_placeholder.progress(
                        0, text=f"Download failed: {download_result.get('error', 'Unknown error')}")
                    st.session_state.download_status[task_id]['status'] = 'FAILED'
            break
        else:
            # Cap at 90% until complete
            progress = min(attempt / max_attempts * 100, 90)
            progress_placeholder.progress(
                int(progress), text=f"Download in progress... (Elapsed: {attempt}s)")
            time.sleep(1)
            attempt += 1


with col2:
    st.markdown("### 📋 Active Downloads")

    if st.session_state.download_status:
        for task_id, task_info in st.session_state.download_status.items():
            status_emoji = {
                'PENDING': '⏳',
                'COMPLETED': '✅',
                'FAILED': '❌'
            }.get(task_info['status'], '❓')

            with st.expander(f"{status_emoji} {task_info['url'][:30]}..."):
                st.write(f"**Type:** {task_info['type']}")
                st.write(f"**Format:** {task_info['format']}")
                st.write(f"**Status:** {task_info['status']}")

                if task_info['status'] == 'COMPLETED' and 'file_path' in task_info:
                    st.success("Download completed successfully!")

    st.markdown("### ⚡ How to Use")
    st.info("""
    1. Paste the video URL
    2. Select Video or Audio only
    3. Choose your preferred quality
    4. Set priority (for enterprise accounts)
    5. Click Start Download
    6. Monitor progress in Active Downloads
    """)

    st.markdown("### 🏢 Enterprise Features")
    st.success("""
    - Priority-based queuing system
    - Distributed background processing
    - Redis caching for faster responses
    - Horizontal scaling capabilities
    - Real-time progress monitoring
    """)

# Footer
st.markdown("---")
st.markdown("""
    <div style='text-align: center'>
        <p>Enterprise Media Downloader • v2.0 • Built for scale</p>
    </div>
    """, unsafe_allow_html=True)
