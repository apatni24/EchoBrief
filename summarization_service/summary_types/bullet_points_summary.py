import os
from dotenv import load_dotenv

load_dotenv()

RANDOM_STRING = os.getenv("RANDOM_STRING")

def get_system_message():
    return f"""You are a professional podcast summarizer specializing in bullet-point style digests.

You are provided with:
- The full transcript of a podcast episode.
- The episode's short summary.
- The title and description of the podcast show.

Your task is to generate a clear, structured summary for quick reading.

Follow these rules:

1. Begin with a clear and engaging **Title** that reflects the core idea of the episode.
2. Use the provided **episode summary** and **show description** to understand tone and context.
3. Write a short **Episode Overview** (1–2 lines) in your own words — don’t copy the `summary` verbatim.
4. List the **Key Insights** as concise bullet points. Avoid filler, small talk, or generic phrases.
5. Include a **Guest Speakers** section (don't include if none are mentioned).
6. Include a **Notable Quotes** section with up to 2 impactful quotes from the transcript (or don't include if none).
7. Keep the tone neutral and professional.
8. Format using markdown with proper headings and bullet styles.

"""


def get_prompt(transcript: str, summary: str, show_title: str, show_summary: str):
    return f"""Please summarize the following podcast transcript using the metadata provided.

Transcript:
{transcript}

Metadata:
- Episode summary: {summary}
- Show title: {show_title}
- Show summary: {show_summary}

Generate:
- A clear and relevant **Title**.
- A 1–2 sentence **Episode Summary**.
- A bullet-point list of **Key Insights**.
- A **Guest Speakers** section (only if one is there).
- A **Notable Quotes** section (only if at least one is there).

Present the output using markdown formatting with proper headings and bullet points.
"""