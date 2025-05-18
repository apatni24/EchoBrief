def get_image_url_from_episode(episode):
    if episode.get("image"):
        return episode.get("image")
    else :
        return episode.get("feedImage")