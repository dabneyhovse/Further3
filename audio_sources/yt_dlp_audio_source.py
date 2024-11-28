from __future__ import annotations

import re
from asyncio import to_thread, Future
from datetime import timedelta
from pathlib import Path
from sys import stderr

from typing import Callable, Any

import validators
from yt_dlp import YoutubeDL

from async_queue import AsyncQueue
from audio_sources import AudioSource
from duration import Duration
from gadt import GADT
from resource_handler import ResourceHandler


class Query(metaclass=GADT):
    URL: Callable[[str], Query]
    YTSearch: Callable[[str], Query]

    @staticmethod
    def from_query_text(query_text: str) -> Query:
        if not validators.url(query_text):
            return Query.YTSearch(query_text)
        elif any(re.fullmatch(pattern, query_text) for pattern in [
            r"https://youtube.com/playlist\?list=.*"
            r"https://music.youtube.com/playlist\?list=.*",
            r"https://www.youtube.com/watch\?v=\w+\&list\=\w+"
        ]):
            raise NotImplementedError("Playlists WIP")
        else:
            return Query.URL(query_text)


class YtDLPAudioSource(AudioSource):
    _author_types: list[str] = ["composer", "artist", "uploader"]

    metadata: dict[str, Any]
    output_path: Future[str]

    class YTDLException(Exception):
        pass

    def __init__(self, query: Query):
        self.output_path = Future()

        ydl_opts = {
            # "extract_flat": "in_playlist",
            # "noprogress": True
        }

        with YoutubeDL(ydl_opts) as ydl:
            match query:
                case Query.URL(url):
                    self.metadata = ydl.extract_info(url, download=False)
                case Query.YTSearch(search_query):
                    # TODO: Complain if nothing is found (extract_info()["entries"] is empty)
                    self.metadata = ydl.extract_info(f"ytsearch:{search_query}", download=False)["entries"][0]

    async def download(self, resource: ResourceHandler.Resource) -> Path:
        # download_queue: AsyncQueue =
        result = await to_thread(self._download_thread, self.metadata, self.url, resource)
        return result

    @staticmethod
    def _download_progress_callback(update):
        # print(type(update))
        pass  # TODO

    @staticmethod
    def _download_thread(metadata: dict[str, Any], url: str, resource: ResourceHandler.Resource) -> Path:
        ydl_opts = {
            "format": "m4a/bestaudio/best",
            "outtmpl": str(resource.path / "%(uploader)s_%(title)s.%(ext)s"),
            # "noplaylist": True,
            # ℹ️ See help(yt_dlp.postprocessor) for a list of available Postprocessors and their arguments
            "postprocessors": [{  # Extract audio using ffmpeg
                "key": "FFmpegExtractAudio",
                # "preferredcodec": "m4a",
            }],
            "progress_hooks": [YtDLPAudioSource._download_progress_callback]
        }

        with YoutubeDL(ydl_opts) as ydl:
            error_code: int = ydl.download([url])
            if error_code:
                raise YtDLPAudioSource.YTDLException(f"yt-dl error code: {error_code}")
            output_path_guess: Path = Path(ydl.prepare_filename(metadata))

        output_path_stem: str = output_path_guess.stem

        download_contents: list[Path] = [
            path for path in resource.path.iterdir()
            if path.is_file() and not (path.name.startswith('.') or path.stat().st_mode & 0x0400)
        ]
        correct_stem_contents: list[Path] = [path for path in download_contents if path.stem == output_path_stem]

        if correct_stem_contents:
            if len(correct_stem_contents) > 1:
                print(
                    "Warning: ambiguous download — found multiple matching files in resource folder:" +
                    "".join(f"\n\t- {path}" for path in correct_stem_contents),
                    file=stderr
                )
            return correct_stem_contents[0]
        elif download_contents:
            print(
                f"Warning: expected file stem ({output_path_stem}) not found. Defaulting to all non-hidden files."
            )
            if len(download_contents) > 1:
                print(
                    "Warning: ambiguous download — found multiple files in resource folder:" +
                    "".join(f"\n\t- {path}" for path in download_contents),
                    file=stderr
                )
            return download_contents[0]
        else:
            raise YtDLPAudioSource.YTDLException("Download failed: no downloaded file found")

    @property
    def title(self) -> str:
        return self.metadata["title"]

    @property
    def author_and_author_type(self) -> tuple[str, str]:
        for author_type in self._author_types:
            author: str = self.metadata.get(author_type, "")
            if author:
                return author_type, author

    @property
    def duration(self) -> Duration:
        return Duration.from_timedelta(timedelta(seconds=self.metadata["duration"]))

    @property
    def url(self) -> str:
        return self.metadata["webpage_url"] if "webpage_url" in self.metadata else "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # TODO
