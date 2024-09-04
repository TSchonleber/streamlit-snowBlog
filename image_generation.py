import streamlit as st
from PIL import Image
import base64
import io
import fal_client
import os
import asyncio

fal_client.api_key = os.getenv('FAL_KEY')
fal_models = {
    "flux-dev": "fal-ai/flux/dev",
    "sd-v3-medium": "fal-ai/stable-diffusion-v3-medium",
    "flux-realism": "fal-ai/flux-realism",
    "flux-lora": "fal-ai/flux-lora",
    "flux-dev-image-to-image": "fal-ai/flux/dev/image-to-image",
    "lora-image-to-image": "fal-ai/lora/image-to-image",
    "fast-sdxl": "fal-ai/fast-sdxl"
}

async def generate_image_fal(prompt, model, image_size="landscape_4_3", inference_steps=28, guidance_scale=3.5, input_image=None, disable_safety_checker=False):
    try:
        arguments = {
            "prompt": prompt,
            "image_size": image_size,
            "num_inference_steps": inference_steps,
            "guidance_scale": guidance_scale,
            "num_images": 1,
            "enable_safety_checker": not disable_safety_checker,
            "sync_mode": False
        }

        if "image-to-image" in model and input_image:
            arguments["image_url"] = input_image

        handler = fal_client.submit(
            fal_models[model],
            arguments=arguments,
        )

        max_attempts = 60
        for _ in range(max_attempts):
            status = handler.status()
            
            if isinstance(status, fal_client.Completed):
                result = handler.get()
                if result and 'images' in result and len(result['images']) > 0:
                    return result['images'][0]['url']
                else:
                    return None
            elif isinstance(status, (fal_client.InProgress, fal_client.Queued)):
                await asyncio.sleep(1)
            else:
                raise Exception(f"Unknown status: {status}")

        raise Exception("Timeout: Image generation took too long")

    except Exception as e:
        st.error(f"An error occurred while generating the image: {str(e)}")
        return None

def image_generation_page():
    st.title("AI Image Generation")
    
    if 'generated_images' not in st.session_state:
        st.session_state.generated_images = []

    # Use columns for layout
    col1, col2 = st.columns([1, 1])

    with col1:
        prompt = st.text_area("Enter your image prompt", height=100)
        
        with st.expander("Advanced Settings", expanded=False):
            model = st.selectbox("Choose a model", list(fal_models.keys()))
            image_size = st.selectbox("Choose image size", ["square_hd", "square", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"])
            inference_steps = st.slider("Inference steps", min_value=1, max_value=50, value=28)
            guidance_scale = st.slider("Guidance scale", min_value=0.0, max_value=20.0, value=3.5, step=0.1)
            disable_safety_checker = st.toggle("Disable Safety Checker (Allow NSFW)", value=False)

        input_image = None
        if model == "flux-dev-image-to-image":
            st.write("Upload an image for image-to-image generation:")
            uploaded_file = st.file_uploader("Choose an input image", type=["png", "jpg", "jpeg"])
            if uploaded_file is not None:
                input_image = base64.b64encode(uploaded_file.getvalue()).decode("utf-8")
                input_image = f"data:image/{uploaded_file.type.split('/')[-1]};base64,{input_image}"
                st.image(uploaded_file, caption="Uploaded Image", use_column_width=True)

        if st.button("Generate Image", type="primary"):
            with st.spinner("Generating image..."):
                try:
                    image_url = asyncio.run(generate_image_fal(prompt, model, image_size, inference_steps, guidance_scale, input_image, disable_safety_checker))
                    if image_url:
                        st.session_state.generated_images.append(image_url)
                        st.success("Image generated successfully!")
                    else:
                        st.error("Failed to generate image")
                except Exception as e:
                    st.error(f"An error occurred: {str(e)}")

    with col2:
        # Display the generated image
        if st.session_state.generated_images:
            st.subheader("Generated Image")
            st.image(st.session_state.generated_images[-1], use_column_width=True)

    # Display previously generated images
    if len(st.session_state.generated_images) > 1:
        st.subheader("Previously Generated Images")
        num_cols = 3
        image_cols = st.columns(num_cols)
        for i, img_url in enumerate(reversed(st.session_state.generated_images[:-1])):
            with image_cols[i % num_cols]:
                st.image(img_url, use_column_width=True, caption=f"Image {len(st.session_state.generated_images) - i - 1}")
                if st.button(f"Use as Input {i+1}", key=f"use_input_{i}"):
                    st.session_state.input_image = img_url
                    st.experimental_rerun()

    # Custom CSS to improve layout
    st.markdown("""
    <style>
    .stButton>button {
        width: 100%;
    }
    .stImage {
        margin-bottom: 1rem;
    }
    </style>
    """, unsafe_allow_html=True)

# Ensure FAL_KEY is set
if 'FAL_KEY' not in os.environ:
    st.error("FAL_KEY is not set in the environment variables. Please set it to use the image generation feature.")

# Set FAL_KEY from environment variable
fal_client.api_key = os.getenv('FAL_KEY')

# Make sure this line is present at the end of the file
if __name__ == "__main__":
    image_generation_page()