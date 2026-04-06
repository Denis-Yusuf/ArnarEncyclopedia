import asyncio

import yt_dlp

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}


class YouTubeService:
    """Talks to YouTube via yt-dlp to pull streamable audio URLs."""

    @staticmethod
    def build_query(query: str) -> str:
        """
        Passes URLs through as-is; wraps plain text in a ytsearch: prefix.

        :param query: A raw YouTube URL or plain-text search string.
        :return: The original URL if it starts with 'http', otherwise a 'ytsearch:' prefixed string.
        """
        return query if query.startswith('http') else f'ytsearch:{query}'

    async def fetch_audio(self, query: str) -> tuple[str, str, str]:
        """
        Asks yt-dlp for the best audio stream for a query.
        Runs in a thread executor so it doesn't block the event loop.

        :param query: A YouTube URL or yt-dlp search string (e.g. 'ytsearch:lofi hip hop').
        :return: A tuple of (stream_url, title, webpage_url).
        """
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(query, download = False))
            if 'entries' in info:
                info = info['entries'][0]
            return info['url'], info['title'], info['webpage_url']
