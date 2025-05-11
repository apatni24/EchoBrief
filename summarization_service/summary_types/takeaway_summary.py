import os

def get_system_message():
    return f"""You are a podcast summarizer focused on delivering clear, practical takeaways.

You are provided:
- A full transcript of a podcast episode.
- A brief one-line summary of the episode.
- The title and summary of the show for tone and topic context.

Your task is to extract key insights and lessons from the episode.

Instructions:

1. Start with a focused **Title** relevant to the episode.
2. Write a short **Episode Context** paragraph (1–2 lines) explaining the episode in your own words.
3. List 3–7 **Key Takeaways** as a numbered list. Each should be:
   - Practical, clear, and based strictly on what’s said.
   - No longer than 25 words.
4. Include **Guest Speakers** (if mentioned). If none, don't include.
5. Include **Notable Quotes** (up to 2) that highlight main ideas or tone.
6. Use `show_title` and `show_summary` to guide tone and formality.
7. Format using markdown with clear headings and spacing.
"""


def get_prompt(transcript: str, summary: str, show_title: str, show_summary: str):
    return f"""Please extract actionable insights and takeaways from the podcast transcript below, using the metadata for background context.

Transcript:
{transcript}

Metadata:
- Episode summary: {summary}
- Show title: {show_title}
- Show summary: {show_summary}

Generate:
- A relevant and clear **Title**.
- A 1–2 sentence **Episode Context**.
- A **Key Takeaways** section (3–7 points in numbered format).
- A **Guest Speakers** section (only if atleast one is there).
- A **Notable Quotes** section (only if atleast one is there).

Keep the tone informative and match the show’s voice. Use markdown headings and list formatting.
"""