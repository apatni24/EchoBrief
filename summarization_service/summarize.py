import os
import time
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

def get_summary(summary_type: str, transcript: str, episode_summary: str, show_title: str, show_summary: str) -> str:
    print("[Summarizer] Generating summary with LangChain (ChatGroq backend)...")
    _rate_limit()

    # 1. Speaker Role Identification
    llm = ChatOpenAI(
        openai_api_key=CHATGROQ_API_KEY,
        openai_api_base=CHATGROQ_API_URL,
        temperature=0.2,
        model_name="llama3-70b-8192"  # Use a ChatGroq-supported model
    )
    speaker_chain = LLMChain(llm=llm, prompt=speaker_id_prompt, output_key="speaker_roles")
    speaker_roles = speaker_chain.run({"transcript": transcript})

    # 2. (Optional) Preprocess transcript to add speaker roles mapping at the top
    processed_transcript = f"SPEAKER ROLES:\n{speaker_roles}\n\n{transcript}"

    # 3. Select summary prompt
    if summary_type == 'ts':
        prompt = PromptTemplate(
            input_variables=["transcript", "episode_summary", "show_title", "show_summary"],
            template=ts.get_prompt("{transcript}", "{episode_summary}", "{show_title}", "{show_summary}")
        )
    elif summary_type == 'ns':
        prompt = PromptTemplate(
            input_variables=["transcript", "episode_summary", "show_title", "show_summary"],
            template=ns.get_prompt("{transcript}", "{episode_summary}", "{show_title}", "{show_summary}")
        )
    else:
        prompt = PromptTemplate(
            input_variables=["transcript", "episode_summary", "show_title", "show_summary"],
            template=bps.get_prompt("{transcript}", "{episode_summary}", "{show_title}", "{show_summary}")
        )

    # 4. Chunk transcript if too long
    splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
    docs = splitter.create_documents([processed_transcript])
    # For simplicity, concatenate all chunks for now (can use map-reduce/refine for large docs)
    full_text = "\n".join([d.page_content for d in docs])

    # 5. Run summary chain
    summary_chain = LLMChain(
        llm=llm,
        prompt=prompt,
        output_key="summary"
    )
    summary = summary_chain.run({
        "transcript": full_text,
        "episode_summary": episode_summary,
        "show_title": show_title,
        "show_summary": show_summary
    })

    return summary
