import os
from pathlib import Path
from typing import Optional

import anthropic
from anthropic import APIError
import PyPDF2
import streamlit as st

from lcp_utils import extract_dimension_scores, render_definition_markdown

st.set_page_config(page_title="LCP Practitioner Pro Pro Pro", page_icon="🧭", layout="wide")

BASE_DIR = Path(__file__).parent


def resolve_api_key() -> Optional[str]:
    manual = st.session_state.get("anthropic_key")
    if manual:
        return manual
    if "ANTHROPIC_API_KEY" in st.secrets:
        return st.secrets["ANTHROPIC_API_KEY"]
    return os.environ.get("ANTHROPIC_API_KEY")


def store_manual_key(default_value: str = "") -> None:
    saved = st.secrets.get("ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY", ""))
    with st.sidebar:
        st.markdown("### Settings")
        api_key_input = st.text_input(
            "Anthropic API Key",
            value=default_value,
            type="password",
            help="Stored only for this browser session. Leave blank to keep the saved key.",
        )
        if api_key_input:
            st.session_state["anthropic_key"] = api_key_input.strip()
        elif saved:
            st.session_state.setdefault("anthropic_key", saved)
            st.success("Using saved Anthropic key from secrets.")
        st.markdown("---")
        st.caption("Upload any LCP PDF to regenerate the 4G roadmap and the Definitions tab.")


def extract_text_from_pdf(uploaded_file) -> str:
    uploaded_file.seek(0)
    pdf_reader = PyPDF2.PdfReader(uploaded_file)
    text = "".join(page.extract_text() or "" for page in pdf_reader.pages)
    uploaded_file.seek(0)
    return text


def analyze_profile(text: str, api_key: str) -> str:
    client = anthropic.Anthropic(api_key=api_key)
    prompt = f"""You are the 'LCP Practitioner Pro Pro Pro', an expert Executive Coach specialized in debriefing Leadership Circle Profiles.

CRITICAL PRIVACY RULE: Instantly anonymize this client data. Replace any full names with single initials. Remove all company names and emails.

CRITICAL TONE RULE: Use very simple, friendly, and professional language. Write EXACTLY as Tünde would speak in a live debrief with a client. Do not use complicated, overly sophisticated, or academic jargon. Keep it conversational and accessible.

Analyze this LCP profile and generate TWO parts, separated by the exact string "===SPLIT===".

PART 1: The 4G Framework
Explicitly refer to specific sections of the report (e.g., "Looking at your Written Comments...", "On the top half of the circle...").

### 0. Pre-Session Awareness (For You)
- What's in this profile about me? What's the gift for me? Who do I want to be?

### 1. GREATNESS (The Secure Base)
- Highlight where they score high (>66%) in Creative or low (<33%) in Reactive.
- Give 2-3 simple, friendly open-ended questions to validate their strengths.

### 2. GAPS (Blind Spots)
- Highlight the biggest gaps between Self and Evaluators (25+ points) and tie to Written Comments.
- Give 2-3 simple, friendly exploration questions.

### 3. GIFTS (Reframing the Reactive)
- Reframe their highest Reactive score (e.g., Controlling) as an overdone strength.
- Give 2-3 friendly questions to explore the *cost* of this strength without triggering defensiveness.

### 4. GROWTH EDGE (The One Big Thing)
- Identify the single biggest lever (a Creative dimension to focus on).
- Give 2-3 simple commitment questions.

===SPLIT===

PART 2: Definitions & Trigger Questions
Identify the top 2 highest Reactive dimensions (e.g., Conservative, Controlling, Complying) and top 2 highest Creative dimensions from this specific profile.
For each of these 4 dimensions, provide:
1. A very simple, practical definition of what this behavior actually looks like day-to-day.
2. 2-3 "Triggering Questions" to help the client explore this specific behavior and how it impacts their leadership.

LCP Profile Data:
{text}
"""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def format_definitions(scores: dict) -> str:
    return render_definition_markdown(scores)


store_manual_key()

st.title("🦸‍♂️ LCP Practitioner Pro Pro Pro")
st.markdown("**The 4G Framework Debrief Optimizer**")

uploaded_file = st.file_uploader("Upload Client LCP PDF", type="pdf")

generate_clicked = st.button("Generate 4G Debrief & Definitions", type="primary") if uploaded_file else False

if generate_clicked and uploaded_file is not None:
    with st.spinner("Parsing the PDF..."):
        pdf_text = extract_text_from_pdf(uploaded_file)
        scores = extract_dimension_scores(pdf_text)
        st.session_state['pdf_text'] = pdf_text
        st.session_state['dimension_scores'] = scores
        st.session_state['definitions'] = format_definitions(scores)

    api_key = resolve_api_key()
    if not api_key:
        st.warning("Add an Anthropic API key in the sidebar to generate the 4G roadmap. Definitions tab is ready below.")
    else:
        with st.spinner("Analyzing profile and building your roadmap..."):
            try:
                full_response = analyze_profile(pdf_text, api_key)
                parts = full_response.split("===SPLIT===")
                st.session_state['roadmap'] = parts[0].strip() if parts else full_response
            except APIError as e:
                st.error(f"Anthropic API error: {e}")
            except Exception as e:
                st.error(f"Error generating analysis: {e}")

if 'roadmap' in st.session_state or 'definitions' in st.session_state:
    st.success("Analysis artifacts ready!")
    tab1, tab2 = st.tabs(["📊 4G Debrief Guide", "📖 Definitions & Triggers"])

    with tab1:
        if 'roadmap' in st.session_state:
            st.markdown(st.session_state['roadmap'])
        else:
            st.info("Upload a PDF and add your Anthropic key to generate the 4G roadmap.")

    with tab2:
        if st.session_state.get('definitions'):
            st.markdown(st.session_state['definitions'])
        else:
            st.info("Upload a PDF to auto-fill this tab with the textbook statements.")

    st.markdown("---")
    st.markdown("### 💬 Pop Question Feature")
    st.markdown("Ask a quick question mid-session (e.g., *'Client is defensive about their Reactive score. How do I pivot?'*)")

    user_q = st.text_input("Ask the Pro:")
    if user_q:
        api_key = resolve_api_key()
        if not api_key:
            st.warning("Add your Anthropic API key to use the Pop Question feature.")
        else:
            with st.spinner("Consulting the LCP framework..."):
                q_prompt = (
                    "The coach is debriefing this LCP profile. Tone MUST be simple, friendly, and professional (spoken language).\n\n"
                    f"Question: {user_q}\n\n"
                    f"Profile Context: {st.session_state.get('pdf_text', '')}\n\n"
                    "Give a highly concise, practical script or reframe."
                )
                client = anthropic.Anthropic(api_key=api_key)
                response = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=500,
                    temperature=0.3,
                    messages=[{"role": "user", "content": q_prompt}],
                )
                st.info(f"**Pro Tip:** {response.content[0].text}")
else:
    if uploaded_file:
        st.info("Upload complete. Click the button above to generate the roadmap and dictionary.")
    else:
        st.info("Upload an LCP PDF to begin.")
