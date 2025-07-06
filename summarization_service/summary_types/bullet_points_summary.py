import os

def get_system_message():
    return """You are an expert podcast summarizer specializing in clear, structured bullet-point summaries.

Your task is to transform podcast transcripts into concise, scannable summaries that highlight key insights.

Core Guidelines:
- Create a compelling title that captures the episode's essence
- Write a brief episode overview (1-2 sentences) in your own words
- Extract key insights as concise bullet points
- Focus on actionable information and main ideas
- Avoid filler content, small talk, or generic statements
- Maintain professional, neutral tone
- Use clear markdown formatting with prominent headings

Output Format:
1. **Title** - Clear, engaging headline (use ## for larger heading)
2. **Episode Overview** - Brief context (1-2 sentences)
3. **Key Insights** - Bullet-point list of main takeaways

Formatting Requirements:
- Use ## for main headings (Title, Episode Overview, Key Insights)
- Use ### for subheadings if needed
- Ensure proper spacing between sections
- Format for direct use in web applications
- Use standard markdown bullet points (- or *)

Remember: Your goal is to help readers quickly grasp the episode's core content and insights."""


def get_prompt(transcript: str, summary: str, show_title: str, show_summary: str, episode_title: str = None, duration: int = None):
    episode_context = f"Episode: {episode_title}" if episode_title else "Episode: [From transcript content]"
    duration_context = f"Podcast Duration (seconds): {duration}" if duration is not None else ""
    
    return f"""Create a bullet-point summary of this podcast episode.

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
Generate a structured summary with:
- An engaging title (use ## heading)
- A brief episode overview (1-2 sentences)
- Key insights as bullet points

Format the output with:
- ## for main headings (larger than normal text)
- Proper spacing between sections
- Clean markdown formatting ready for direct use
- Standard bullet points for key insights

Focus on extracting the most important information and insights."""