import os
import time
import re
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain, SequentialChain
from langchain.text_splitter import RecursiveCharacterTextSplitter
from summarization_service.summary_types import (
    bullet_points_summary as bps,
    narrative_summary as ns,
    takeaway_summary as ts
)

load_dotenv()

ENV = os.getenv("ENV", "dev")
# Use ChatGroq as the OpenAI-compatible backend
CHATGROQ_API_KEY = os.getenv("CHATGROQ_API_KEY")
CHATGROQ_API_URL = os.getenv("CHATGROQ_API_URL", "https://api.chatgroq.com/v1")

# Rate limiting: ensure at least 60 seconds between calls
_t_last_request_time = 0.0

def _rate_limit():
    global _t_last_request_time
    now = time.time()
    elapsed = now - _t_last_request_time
    if elapsed < 60:
        wait = 60 - elapsed
        print(f"[Summarizer] Rate limit in effect, sleeping for {wait:.1f}s...")
        time.sleep(wait)
    _t_last_request_time = time.time()

# Step 1: Speaker Role Identification
speaker_id_prompt = PromptTemplate(
    input_variables=["transcript"],
    template="""
Given the following podcast transcript with speakers labeled as [Speaker 1], [Speaker 2], etc., infer the likely roles or identities of each speaker. Output a mapping like:
Speaker 1: Host (Name if available)
Speaker 2: Guest (Name if available)
If names are not available, use roles only.
Transcript:
{transcript}
"""
)

# Step 2: Transcript Validation and Correction
transcript_validation_prompt = PromptTemplate(
    input_variables=["transcript", "episode_title", "show_title", "episode_summary", "show_summary", "duration"],
    template="""
You are a transcript validation expert. Review the podcast transcript and compare it with the provided metadata to ensure accuracy and consistency.

TRANSCRIPT:
{transcript}

METADATA:
- Episode Title: {episode_title}
- Show Title: {show_title}
- Episode Summary: {episode_summary}
- Show Summary: {show_summary}
- Podcast Duration (seconds): {duration}

TASK:
1. Check for spelling errors, especially for:
   - Names mentioned in the episode
   - Technical terms
   - Place names
   - Company names
   - Any terms that appear in the metadata

2. Verify the transcript aligns with the episode metadata:
   - Does the content match the episode title?
   - Are the topics discussed consistent with the episode summary?
   - Are there any obvious transcription errors?
   - Does the transcript length seem reasonable for the given duration? (e.g., a 60-minute podcast should have a much longer transcript than a 5-minute one)

3. If you find issues, provide corrections in this format:
   CORRECTIONS:
   - [Original text] → [Corrected text]
   - [Another error] → [Correction]

4. If no corrections are needed, respond with:
   CORRECTIONS: None needed

5. Provide a brief validation summary:
   VALIDATION: [Brief assessment of transcript quality and alignment with metadata]

IMPORTANT:
- Do NOT invent or hallucinate content. Only validate and correct what is present in the transcript.
- If the transcript is incomplete or inaccurate, do NOT generate hypothetical summaries or takeaways.
- If the transcript is inconsistent with the metadata, suggest only minimal updates to the summary, do not rewrite it completely.
"""
)

def get_summary(summary_type: str, transcript: str, episode_summary: str, show_title: str, show_summary: str, episode_title: str = None, duration: int = None) -> str:
    print("[Summarizer] Generating summary with LangChain (ChatGroq backend)...")
    _rate_limit()

    # Initialize LLM
    llm = ChatOpenAI(
        openai_api_key=CHATGROQ_API_KEY,
        openai_api_base=CHATGROQ_API_URL,
        temperature=0.2,
        model_name="llama3-70b-8192"  # Use a ChatGroq-supported model
    )

    # Step 1: Speaker Role Identification
    speaker_chain = LLMChain(llm=llm, prompt=speaker_id_prompt, output_key="speaker_roles")
    speaker_roles = speaker_chain.run({"transcript": transcript})

    # Step 2: Transcript Validation and Correction
    print("[Summarizer] Validating transcript against metadata...")
    validation_chain = LLMChain(llm=llm, prompt=transcript_validation_prompt, output_key="validation_result")
    validation_result = validation_chain.run({
        "transcript": transcript,
        "episode_title": episode_title or "Unknown Episode",
        "show_title": show_title,
        "episode_summary": episode_summary,
        "show_summary": show_summary,
        "duration": duration or 0
    })

    # Parse validation result
    corrections = []
    validation_summary = ""
    
    # Extract corrections and validation summary from the result
    lines = validation_result.split('\n')
    in_corrections = False
    in_validation = False
    
    for line in lines:
        line = line.strip()
        if line.startswith("CORRECTIONS:"):
            in_corrections = True
            in_validation = False
            if "None needed" in line:
                corrections = []
            continue
        elif line.startswith("VALIDATION:"):
            in_corrections = False
            in_validation = True
            validation_summary = line.replace("VALIDATION:", "").strip()
            continue
        elif line == "":
            in_corrections = False
            in_validation = False
            continue
        
        if in_corrections and "→" in line:
            corrections.append(line)
        elif in_validation and validation_summary == "":
            validation_summary = line

    print(f"[Summarizer] Validation complete: {validation_summary}")
    if corrections:
        print(f"[Summarizer] Found {len(corrections)} corrections needed")
        for correction in corrections:
            print(f"  {correction}")

    # Step 3: Apply corrections to transcript if needed
    corrected_transcript = transcript
    if corrections:
        print("[Summarizer] Applying corrections to transcript...")
        for correction in corrections:
            if "→" in correction:
                original, corrected = correction.split("→")
                original = original.strip()
                corrected = corrected.strip()
                # Use regex to replace the original text with corrected text
                corrected_transcript = re.sub(re.escape(original), corrected, corrected_transcript, flags=re.IGNORECASE)
    else:
        corrected_transcript = transcript

    # Step 4: Preprocess transcript to add speaker roles mapping and metadata context
    processed_transcript = f"""METADATA CONTEXT:
Episode: {episode_title or "Unknown Episode"}
Show: {show_title}
Episode Summary: {episode_summary}
Show Summary: {show_summary}
Podcast Duration (seconds): {duration or 0}

SPEAKER ROLES:
{speaker_roles}

TRANSCRIPT:
{corrected_transcript}

VALIDATION SUMMARY:
{validation_summary}

IMPORTANT:
- Only summarize the provided transcript. Do NOT generate hypothetical summaries or takeaways if the transcript is incomplete or inaccurate.
- If the transcript is inconsistent with the metadata, update the summary minimally, do not invent or rewrite it completely.
"""

    # Step 5: Select summary prompt with enhanced metadata usage
    if summary_type == 'ts':
        prompt = PromptTemplate(
            input_variables=["transcript", "episode_summary", "show_title", "show_summary", "episode_title", "duration"],
            template=ts.get_prompt("{transcript}", "{episode_summary}", "{show_title}", "{show_summary}", "{episode_title}", "{duration}")
        )
    elif summary_type == 'ns':
        prompt = PromptTemplate(
            input_variables=["transcript", "episode_summary", "show_title", "show_summary", "episode_title", "duration"],
            template=ns.get_prompt("{transcript}", "{episode_summary}", "{show_title}", "{show_summary}", "{episode_title}", "{duration}")
        )
    else:
        prompt = PromptTemplate(
            input_variables=["transcript", "episode_summary", "show_title", "show_summary", "episode_title", "duration"],
            template=bps.get_prompt("{transcript}", "{episode_summary}", "{show_title}", "{show_summary}", "{episode_title}", "{duration}")
        )

    # Step 6: Chunk transcript if too long
    splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
    docs = splitter.create_documents([processed_transcript])
    # For simplicity, concatenate all chunks for now (can use map-reduce/refine for large docs)
    full_text = "\n".join([d.page_content for d in docs])

    # Step 7: Run summary chain with enhanced metadata
    summary_chain = LLMChain(
        llm=llm,
        prompt=prompt,
        output_key="summary"
    )
    summary = summary_chain.run({
        "transcript": full_text,
        "episode_summary": episode_summary,
        "show_title": show_title,
        "show_summary": show_summary,
        "episode_title": episode_title or "Unknown Episode",
        "duration": duration or 0
    })

    return summary
