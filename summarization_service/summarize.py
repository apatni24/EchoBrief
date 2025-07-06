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
CHATGROQ_API_KEY2 = os.getenv("CHATGROQ_API_KEY2")  # Second API key for load distribution
CHATGROQ_API_URL = os.getenv("CHATGROQ_API_URL", "https://api.chatgroq.com/v1")

# Rate limiting: ensure at least 60 seconds between calls
_t_last_request_time = 0.0
_api_key_usage_counter = 0  # Track which API key to use next

def _rate_limit():
    global _t_last_request_time
    now = time.time()
    elapsed = now - _t_last_request_time
    if elapsed < 60:
        wait = 60 - elapsed
        print(f"[Summarizer] Rate limit in effect, sleeping for {wait:.1f}s...")
        time.sleep(wait)
    _t_last_request_time = time.time()

def _get_next_api_key():
    """Alternate between API keys to distribute load"""
    global _api_key_usage_counter
    _api_key_usage_counter += 1
    
    # Use CHATGROQ_API_KEY2 if available, otherwise fall back to primary key
    if CHATGROQ_API_KEY2 and _api_key_usage_counter % 2 == 0:
        print(f"[Summarizer] Using secondary API key (call #{_api_key_usage_counter})")
        return CHATGROQ_API_KEY2
    else:
        print(f"[Summarizer] Using primary API key (call #{_api_key_usage_counter})")
        return CHATGROQ_API_KEY

def _create_llm(model_name, temperature=0.2):
    """Create LLM instance with the next available API key"""
    api_key = _get_next_api_key()
    return ChatOpenAI(
        openai_api_key=api_key,
        openai_api_base=CHATGROQ_API_URL,
        temperature=temperature,
        model_name=model_name
    )

def safe_llm_run(chain, input_data, max_retries=3, initial_chunk_size=2000):
    """Safely run LLM chain with automatic retry and chunking for token limit errors"""
    chunk_size = initial_chunk_size
    
    for attempt in range(max_retries):
        try:
            return chain.run(input_data)
        except Exception as e:
            error_msg = str(e).lower()
            
            # Check for token limit or request too large errors
            if any(keyword in error_msg for keyword in ["request too large", "rate_limit_exceeded", "413", "tokens per minute"]):
                print(f"[Summarizer] Token limit error on attempt {attempt + 1}: {e}")
                
                if attempt < max_retries - 1 and chunk_size > 500:
                    # Reduce chunk size and retry
                    chunk_size = chunk_size // 2
                    print(f"[Summarizer] Retrying with smaller chunk size: {chunk_size}")
                    
                    # Re-chunk the transcript if it's in the input data
                    if "transcript" in input_data:
                        splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=200)
                        docs = splitter.create_documents([input_data["transcript"]])
                        
                        if len(docs) > 1:
                            # Process chunks and combine results
                            results = []
                            for i, doc in enumerate(docs):
                                print(f"[Summarizer] Processing chunk {i+1}/{len(docs)}")
                                chunk_input = input_data.copy()
                                chunk_input["transcript"] = doc.page_content
                                results.append(chain.run(chunk_input))
                            
                            # Combine results (for validation, we might want to merge differently)
                            if "validation" in str(chain.prompt).lower():
                                # For validation, combine all corrections and summaries
                                combined_result = ""
                                for result in results:
                                    if "CORRECTIONS:" in result:
                                        combined_result += result + "\n"
                                    elif "VALIDATION:" in result:
                                        combined_result += result + "\n"
                                return combined_result
                            else:
                                return "\n".join(results)
                        else:
                            # Single chunk, just retry with smaller size
                            continue
                    else:
                        # No transcript to chunk, just retry
                        continue
                else:
                    raise RuntimeError(f"Failed to process after {max_retries} attempts. Last error: {e}")
            else:
                # Non-token-limit error, re-raise
                raise

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

    # Step 1: Speaker Role Identification (use cheaper model)
    print("[Summarizer] Step 1: Identifying speaker roles...")
    cheap_llm = _create_llm("llama3-8b-8192", temperature=0.2)  # Cheaper model for less critical task
    speaker_chain = LLMChain(llm=cheap_llm, prompt=speaker_id_prompt, output_key="speaker_roles")
    speaker_roles = safe_llm_run(speaker_chain, {"transcript": transcript})

    # Step 2: Transcript Validation and Correction (use cheaper model)
    print("[Summarizer] Step 2: Validating transcript against metadata...")
    validation_chain = LLMChain(llm=cheap_llm, prompt=transcript_validation_prompt, output_key="validation_result")
    validation_result = safe_llm_run(validation_chain, {
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

    # Step 7: Run summary chain with enhanced metadata (use best quality model)
    print("[Summarizer] Step 3: Generating final summary...")
    main_llm = _create_llm("llama3-70b-8192", temperature=0.2)  # Best quality model for final summary
    summary_chain = LLMChain(
        llm=main_llm,
        prompt=prompt,
        output_key="summary"
    )
    summary = safe_llm_run(summary_chain, {
        "transcript": full_text,
        "episode_summary": episode_summary,
        "show_title": show_title,
        "show_summary": show_summary,
        "episode_title": episode_title or "Unknown Episode",
        "duration": duration or 0
    })

    return summary
