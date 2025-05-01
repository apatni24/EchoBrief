import os
from dotenv import load_dotenv

load_dotenv()

RANDOM_STRING = os.getenv("RANDOM_STRING")

def get_system_message():
    return f"""You are a professional podcast summarizer skilled in narrative-style summaries.

You are given:
- The transcript of a podcast episode.
- A brief summary of the episode.
- The show’s title and general description.

Your job is to craft a flowing story-style summary that gives a reader a blog-like understanding of the episode content.

Follow these instructions:

1. Start with a **descriptive, engaging Title**.
2. Use the **episode summary** and **show description** only for background tone — do not repeat them directly.
3. Write a **narrative summary** (200–300 words) that follows the structure of the episode naturally. It should feel like a mini-article.
4. Include a **Guest Speakers** section. If not present, don't include one.
5. Include up to 2 **Notable Quotes** at the end (or don't include if none).
6. Do not list key points or bullet anything in the main summary.
7. Keep the tone faithful to the show — use the `show_summary` to calibrate voice.
8. Output must be cleanly formatted with markdown headings and paragraphs.
"""


def get_prompt(transcript: str, summary: str, show_title: str, show_summary: str):
    return f"""Please write a narrative-style summary of the following podcast transcript, using the metadata provided for background context.

Transcript:
{transcript}

Metadata:
- Episode summary: {summary}
- Show title: {show_title}
- Show summary: {show_summary}

Generate:
- A descriptive **Title**.
- A 200–300 word **Narrative Summary** (flowing blog-style summary).
- A **Guest Speakers** section (only if atleast one is there).
- A **Notable Quotes** section (only if atleast one is there).

Do not use bullet points in the summary body. Use markdown formatting for headings and structure.
"""