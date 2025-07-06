import os

def get_system_message():
    return """You are an expert podcast summarizer specializing in narrative-style summaries.

Your task is to transform podcast transcripts into engaging, story-like summaries that read like well-crafted blog posts.

Core Guidelines:
- Write in a flowing, narrative style (200-300 words)
- Create a compelling title that captures the episode's essence
- Maintain the show's tone and voice throughout
- Focus on the main story arc and key insights
- Use clear, engaging language that flows naturally
- Structure as a cohesive narrative, not a list of points
- Avoid repetition of provided metadata
- Use markdown formatting with prominent headings

Output Format:
1. **Title** - Engaging, descriptive headline (use ## for larger heading)
2. **Narrative Summary** - Flowing story-style content (200-300 words)

Formatting Requirements:
- Use ## for main headings (Title, Narrative Summary)
- Use ### for subheadings if needed
- Ensure proper spacing between sections
- Format for direct use in web applications
- Use clean paragraph breaks for readability

Remember: Your goal is to make the reader feel like they've experienced the episode through your summary."""


def get_prompt(transcript: str, summary: str, show_title: str, show_summary: str, episode_title: str = None, duration: int = None):
    episode_context = f"Episode: {episode_title}" if episode_title else "Episode: [From transcript content]"
    duration_context = f"Podcast Duration (seconds): {duration}" if duration is not None else ""
    
    return f"""Create a narrative summary of this podcast episode.

TRANSCRIPT:
{transcript}

CONTEXT:
- {episode_context}
- Episode Description: {summary}
- Show: {show_title}
- Show Description: {show_summary}
- {duration_context}

IMPORTANT:
- Only summarize the provided transcript. Do NOT generate hypothetical summaries or takeaways if the transcript is incomplete or inaccurate.
- If the transcript is inconsistent with the metadata, update the summary minimally, do not invent or rewrite it completely.

TASK:
Write a compelling narrative summary that:
- Opens with an engaging title (use ## heading)
- Tells the episode's story in 200-300 words
- Flows naturally like a blog post
- Captures the main insights and takeaways
- Maintains the show's authentic voice

Format the output with:
- ## for main headings (larger than normal text)
- Proper spacing between sections
- Clean markdown formatting ready for direct use
- Well-structured paragraphs for readability

Focus on storytelling, not bullet points."""