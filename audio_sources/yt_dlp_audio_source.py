from __future__ import annotations

from asyncio import to_thread
from datetime import timedelta
from pathlib import Path
from sys import stderr

from typing import Callable, Any

from yt_dlp import YoutubeDL

from audio_sources import AudioSource
from gadt import GADT
from resource_handler import ResourceHandler


class Query(metaclass=GADT):
    URL: Callable[[str], Query]
    YTSearch: Callable[[str], Query]
    # DabneyVictory: YoutubeDLAudioSource.Query
    # RealDabneyVictory: YoutubeDLAudioSource.Query


class YtDLPAudioSource(AudioSource):
    _author_types: list[str] = ["composer", "artist", "uploader"]

    metadata: dict[str, Any]
    output_path: str | None

    class YTDLException(Exception):
        pass

    def __init__(self, query: Query):
        self.output_path = None

        ydl_opts = {}

        with YoutubeDL(ydl_opts) as ydl:
            match query:
                case Query.URL(url):
                    self.metadata = ydl.extract_info(url, download=False)
                case Query.YTSearch(search_query):
                    self.metadata = ydl.extract_info(f"ytsearch:{search_query}", download=False)["entries"][0]

    async def download(self, resource: ResourceHandler.Resource) -> Path:
        print("Starting download thread")
        result = await to_thread(self._download_thread, self.metadata, self.url, resource)
        print("Ended download thread")
        return result

    @staticmethod
    def _download_thread(metadata: dict[str, Any], url: str, resource: ResourceHandler.Resource) -> Path:
        print("Entered download thread")
        ydl_opts = {
            "format": "m4a/bestaudio/best",
            "outtmpl": str(resource.path / "%(uploader)s_%(title)s.%(ext)s"),
            # ℹ️ See help(yt_dlp.postprocessor) for a list of available Postprocessors and their arguments
            "postprocessors": [{  # Extract audio using ffmpeg
                "key": "FFmpegExtractAudio",
                # "preferredcodec": "m4a",
            }]
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
    def duration(self) -> timedelta:
        return timedelta(seconds=self.metadata["duration"])

    @property
    def url(self) -> str:
        return self.metadata["webpage_url"]
