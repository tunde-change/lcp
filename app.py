import os
from pathlib import Path
from typing import Optional

import anthropic
from anthropic import APIError
import PyPDF2
import streamlit as st

from lcp_utils import (
    build_removal_terms,
    detect_client_name,
    dimension_collisions,
    extract_dimension_scores,
    remaining_identifiers,
    render_definition_markdown,
    scrub_text,
)

st.set_page_config(page_title="LCP Practitioner Pro Pro Pro", page_icon="🧭", layout="wide")

BASE_DIR = Path(__file__).parent


def secret_api_key() -> str:
    """Read the key from secrets if there are any. Streamlit raises when no secrets file exists,
    which is the normal case when the app runs locally, so this must not be allowed to escape."""
    try:
        return st.secrets.get("ANTHROPIC_API_KEY", "") or ""
    except Exception:
        return ""


def resolve_api_key() -> Optional[str]:
    manual = st.session_state.get("anthropic_key")
    if manual:
        return manual
    return secret_api_key() or os.environ.get("ANTHROPIC_API_KEY")


def store_manual_key(default_value: str = "") -> None:
    saved = secret_api_key() or os.environ.get("ANTHROPIC_API_KEY", "")
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
            st.info("No key entered, so this run uses the app owner's key and their Anthropic account.")
        st.markdown("---")
        st.caption("Upload any LCP PDF to regenerate the 4G roadmap and the Definitions tab.")
        st.markdown("---")
        st.markdown("### Privacy")
        st.caption(
            "The PDF is read in this app and is not stored. "
            "Names and email addresses are removed from the text before anything is sent to the "
            "Anthropic API, and you can see the exact text that will be sent before you generate. "
            "Percentile scores and the written comments are still sent, so they can be analysed."
        )


def extract_text_from_pdf(uploaded_file) -> str:
    uploaded_file.seek(0)
    pdf_reader = PyPDF2.PdfReader(uploaded_file)
    text = "".join(page.extract_text() or "" for page in pdf_reader.pages)
    uploaded_file.seek(0)
    return text


def analyze_profile(text: str, api_key: str) -> str:
    client = anthropic.Anthropic(api_key=api_key)
    prompt = f"""You are the 'LCP Practitioner Pro Pro Pro', an expert Executive Coach specialized in debriefing Leadership Circle Profiles.

CRITICAL PRIVACY RULE: This profile was pseudonymised before it reached you. The client's name appears as [CLIENT] and email addresses as [EMAIL]. Never invent or guess a name, always write "the client" or "they". If any identifying detail slipped through, such as a company name or a colleague named in the comments, do not repeat it in your answer.

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

st.caption("Upload the report exactly as Leadership Circle sent it. Names are removed here, before anything is sent on.")
uploaded_file = st.file_uploader("Upload Client LCP PDF", type="pdf")

raw_text = ""
scrubbed_text = ""
generate_clicked = False

if uploaded_file is not None:
    with st.spinner("Reading the PDF..."):
        raw_text = extract_text_from_pdf(uploaded_file)

    if len(raw_text.strip()) < 200:
        st.error(
            "This PDF has no readable text, so the report cannot be analysed. "
            "It is usually a file that was scanned, printed to image, or flattened while being anonymised. "
            "Upload the original PDF from Leadership Circle instead. "
            "Quick check: open the file and try to select a line of text with your mouse. "
            "If you cannot highlight it, this tool cannot read it either."
        )
    else:
        st.markdown("#### Step 1: remove the identifying details")
        detected = detect_client_name(raw_text)
        col_a, col_b = st.columns(2)
        with col_a:
            client_name = st.text_input(
                "Client name found in the report",
                value=detected,
                help="Every occurrence of this name is removed before anything is sent to the API.",
            )
        with col_b:
            extra_terms = st.text_area(
                "Anything else to remove",
                placeholder="Nickname, company, team, colleagues named in the Written Comments",
                height=68,
            )
        st.caption(
            "Accents and spacing are handled, so Tunde also catches Tünde. A nickname is not, "
            "so if the comments call the client Yas rather than Yasmin, add it in the second box."
        )

        if not detected:
            st.warning("No name detected automatically. Type the client name above before generating.")

        terms = build_removal_terms(client_name, extra_terms)
        scrubbed_text, removal_report = scrub_text(raw_text, terms)
        leftovers = remaining_identifiers(scrubbed_text, terms)

        # Scores are parsed from the original text and never leave this app,
        # so a client whose surname matches a dimension word cannot corrupt them.
        scores = extract_dimension_scores(raw_text)
        st.session_state['pdf_text'] = scrubbed_text
        st.session_state['dimension_scores'] = scores
        st.session_state['definitions'] = format_definitions(scores)

        if removal_report:
            summary = ", ".join(f"{term} ({count}x)" for term, count in removal_report.items())
            st.success(f"Removed before sending: {summary}")
        else:
            st.warning("Nothing was removed. Check the name above, unless this file is already anonymised.")

        if leftovers:
            st.error(f"Still present after cleaning, do not send: {', '.join(leftovers)}")

        collisions = dimension_collisions(terms)
        if collisions:
            st.info(
                f"Note: {', '.join(collisions)} is also an LCP dimension name. It is removed anyway, "
                "so the name cannot leak, which means that dimension will read as [CLIENT] in the "
                "text the model sees. Your scores and the Definitions tab are unaffected."
            )

        if not scores:
            st.warning(
                "The percentile table could not be read from this PDF, so the Definitions tab will be empty. "
                "The 4G roadmap can still be generated from the text."
            )

        with st.expander("Show exactly what will be sent to Anthropic"):
            st.text(scrubbed_text[:3000] + ("\n\n[...]" if len(scrubbed_text) > 3000 else ""))

        st.markdown("#### Step 2: generate")
        generate_clicked = st.button(
            "Generate 4G Debrief & Definitions",
            type="primary",
            disabled=bool(leftovers),
        )

if generate_clicked and uploaded_file is not None:
    pdf_text = scrubbed_text
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
                    "The profile was pseudonymised: the client appears as [CLIENT]. Never invent a name, "
                    "write \"the client\" or \"they\".\n\n"
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
elif uploaded_file is None:
    st.info("Upload an LCP PDF to begin.")
