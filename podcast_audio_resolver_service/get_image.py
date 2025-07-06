def get_image_url_from_episode(episode):
    """
    Extract image URL from episode with multiple fallbacks.
    Returns a default placeholder image if no image is found.
    """
    try:
        # Try episode-specific image first
        if episode.get("image"):
            return episode.get("image")
        
        # Try feed image as fallback
        if episode.get("feedImage"):
            return episode.get("feedImage")
        
        # Try iTunes image
        if hasattr(episode, 'itunes_image') and episode.itunes_image:
            return episode.itunes_image.get('href', None)
        
        # Try media content
        if hasattr(episode, 'media_content') and episode.media_content:
            for media in episode.media_content:
                if media.get('medium') == 'image':
                    return media.get('url', None)
        
        # Default placeholder image
        return "https://via.placeholder.com/300x300/6B7280/FFFFFF?text=Podcast"
        
    except Exception as e:
        print(f"Error extracting image URL: {e}")
        # Return default image on any error
        return "https://via.placeholder.com/300x300/6B7280/FFFFFF?text=Podcast"