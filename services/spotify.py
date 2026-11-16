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
        track_match = re.search(r'spotify\.com/(?:intl-[\w-]+/)?track/([a-zA-Z0-9]+)', query)
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

    def fetch_collection(self, url: str) -> list[tuple[str, str]] | None:
        """
        Lists the songs of a Spotify album or playlist link.

        :param url: A Spotify album or playlist URL.
        :return: A list of (yt-dlp search query, 'Artist - Title') tuples, or None when the URL
            is not an album or playlist link.
        :raises spotipy.SpotifyBaseException: When Spotify refuses the link (private, removed, blocked)
            or the credentials.
        :raises requests.RequestException: When Spotify cannot be reached.
        """
        # Old share links look like spotify.com/user/<name>/playlist/<id>.
        match = re.search(r'spotify\.com/(?:intl-[\w-]+/)?(?:user/[^/]+/)?(album|playlist)/([a-zA-Z0-9]+)', url)
        if not match:
            return None
        kind, collection_id = match.groups()
        # shortcut: one page of 50 only, which equals the queue's PLAYLIST_CAP; page through
        # 'next' if that cap is ever raised.
        if kind == 'album':
            tracks = self._sp.album_tracks(collection_id, limit = 50)['items']
        else:
            # A playlist wraps each song; the key is 'item' on Spotify's newer endpoint, 'track' on the old one.
            entries = self._sp.playlist_items(collection_id, limit = 50)['items']
            tracks = [entry.get('item') or entry.get('track') for entry in entries]

        songs = []
        for track in tracks:
            # Removed songs are None; podcast episodes and local files have no artist to search YouTube with.
            if not track or track.get('type') != 'track' or track.get('is_local') or not track.get('artists'):
                continue
            title = f"{track['artists'][0]['name']} - {track['name']}"
            songs.append((f'ytsearch:{title}', title))
        return songs
