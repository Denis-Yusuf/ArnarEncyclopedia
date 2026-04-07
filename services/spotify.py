import re

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials


class SpotifyService:
    """Resolves Spotify URLs and search queries into 'Artist - Title' strings for YouTube lookup."""

    def __init__(self, client_id: str, client_secret: str) -> None:
        """
        :param client_id: The Spotify application client ID.
        :param client_secret: The Spotify application client secret.
        """
        self._sp = spotipy.Spotify(auth_manager = SpotifyClientCredentials(
            client_id = client_id,
            client_secret = client_secret,
        ))

    def resolve_query(self, query: str) -> str | None:
        """
        Takes a Spotify URL or plain search string and returns an 'Artist - Title' string
        suitable for passing to a YouTube search.

        :param query: A Spotify track URL or plain-text search query.
        :return: A formatted 'Artist - Title' string, or None if nothing was found.
        """
        track_match = re.search(r'spotify\.com/track/([a-zA-Z0-9]+)', query)
        if track_match:
            # Fetch the track directly by ID extracted from the URL
            track = self._sp.track(track_match.group(1))
        else:
            # Fall back to a keyword search and take the top result
            results = self._sp.search(q = query, type = 'track', limit = 1)
            items = results['tracks']['items']
            if not items:
                return None
            track = items[0]

        artist = track['artists'][0]['name']
        title = track['name']
        return f"{artist} - {title}"
