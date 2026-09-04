import os
from pathlib import Path, PurePosixPath

from castero import constants
from castero import helpers
from castero.config import Config
from castero.datafile import DataFile
from castero.paths import download_path


class Episode:
    """A single episode from a podcast feed."""

    PROGRESS_INDICATOR = "*"

    def __init__(
        self,
        feed,
        ep_id=None,
        title=None,
        description=None,
        link=None,
        pubdate=None,
        copyright=None,
        enclosure=None,
        guid=None,
        played=False,
        progress=None,
        download_path=None,
        download_checksum=None,
    ) -> None:
        """
        At least one of a title or description must be specified.

        :param feed the feed that this episode is a part of
        :param title (optional) the title of the episode
        :param description (optional) the description of the episode
        :param link (optional) a link to the episode
        :param pubdate (optional) the date the episode was published, as a string
        :param copyright (optional) the copyright notice of the episode
        :param enclosure (optional) a url to a media file
        :param guid (optional) the opaque RSS identifier for the episode
        :param played (optional) whether the episode has been played
        :param download_path (optional) normalized path relative to the download root
        :param download_checksum (optional) trusted SHA-256 digest of the download
        """
        assert title is not None or description is not None

        self._feed = feed
        self._ep_id = ep_id
        self._title = title
        self._description = description
        self._link = link
        self._pubdate = pubdate
        self._copyright = copyright
        self._enclosure = enclosure
        self._guid = guid
        self._played = played
        self._progress = progress
        self._download_path = download_path
        self._download_checksum = download_checksum
        self._downloaded = None

    def __str__(self) -> str:
        """Represent this object as a single-line string.

        :returns string: this episode's title, if it exists, else its description
        """
        if self._title is not None:
            representation = str(self._title)
        else:
            representation = str(self._description)

        representation = representation.split("\n")[0]

        return representation

    def _download_root(self) -> Path:
        """Return the active root directory for downloaded episodes."""
        configured_path = "" if Config is None else Config["custom_download_dir"]
        return Path(download_path(configured_path, default=DataFile.DEFAULT_DOWNLOADED_DIR))

    def _feed_directory(self) -> str:
        """Gets the path to the downloaded episode's feed directory.

        This method does not ensure whether the directory exists -- it simply
        acts as a single definition of where it _should_ be.

        :returns str: a path to the feed directory
        """
        feed_dirname = helpers.sanitize_path(str(self._feed))
        return os.path.join(str(self._download_root()), feed_dirname)

    def _stored_download_file(self):
        """Return the absolute recorded download path, if one is available."""
        if self._download_path is None:
            return None
        if not isinstance(self._download_path, str) or "\\" in self._download_path:
            return None
        relative = PurePosixPath(self._download_path)
        if (
            relative.is_absolute()
            or not relative.parts
            or ".." in relative.parts
            or relative.name.endswith(".part")
        ):
            return None
        root = self._download_root().resolve()
        candidate = root.joinpath(*relative.parts)
        try:
            candidate.resolve().relative_to(root)
        except ValueError:
            return None
        return candidate

    def _legacy_download_files(self, feed_directory):
        """Yield completed files matching the legacy episode naming scheme."""
        prefix = str(self.ep_id) + "-"
        for filename in os.listdir(feed_directory):
            path = os.path.join(feed_directory, filename)
            if (
                filename.startswith(prefix)
                and not filename.endswith(".part")
                and os.path.isfile(path)
            ):
                yield path

    def get_playable(self) -> str:
        """Gets a playable path for this episode.

        This method checks whether the episode is available on the disk, giving
        the path to that file if so. Otherwise, simply return the episode's
        enclosure, which is probably a URL.

        :returns str: a path to a playable file for this episode
        """
        playable = self.enclosure

        stored_file = self._stored_download_file()
        if stored_file is not None and stored_file.is_file():
            return str(stored_file)

        feed_directory = self._feed_directory()
        if self._download_path is None and os.path.exists(feed_directory):
            for path in self._legacy_download_files(feed_directory):
                playable = path

        return playable

    def download(self, download_queue, display=None):
        """Downloads this episode to the file system.

        This method currently only supports downloading from an external URL.
        In the future, it may be worthwhile to determine whether the episode's
        source is a local file and simply copy it instead.

        :param download_queue the download_queue overseeing this download
        :param display (optional) the display to write status updates to
        """
        if self._enclosure is None:
            if display is not None:
                display.change_status("Download failed: episode does not have" " a valid media source")
            download_queue.next()
            return

        feed_directory = self._feed_directory()
        filename = "%s-%s%s" % (
            self.ep_id,
            helpers.sanitize_path(str(self)),
            str(os.path.splitext(self._enclosure)[1].split("?")[0]),
        )
        output_path = os.path.join(feed_directory, filename)
        DataFile.ensure_path(output_path)

        def on_complete(path, checksum):
            relative = Path(path).resolve().relative_to(self._download_root().resolve())
            normalized = PurePosixPath(*relative.parts).as_posix()
            self._download_path = normalized
            self._download_checksum = checksum
            self._downloaded = True
            database = None if display is None else getattr(display, "database", None)
            if database is not None:
                database.replace_download(self, normalized, checksum)

        if display is not None:
            display.change_status("Starting episode download...")

        DataFile.download_to_file(
            self._enclosure,
            output_path,
            str(self),
            download_queue,
            display,
            on_complete,
        )

    def delete(self, display=None):
        """Deletes the episode file from the file system.

        :param display (optional) the display to write status updates to
        """
        if self.downloaded:
            stored_file = self._stored_download_file()
            feed_directory = self._feed_directory()
            if stored_file is not None:
                if stored_file.exists():
                    stored_file.unlink()
                directory = stored_file.parent
                if directory.is_dir() and len(os.listdir(str(directory))) == 0:
                    directory.rmdir()
                self._downloaded = False
            elif os.path.exists(feed_directory):
                for path in self._legacy_download_files(feed_directory):
                    os.remove(path)
                    self._downloaded = False
                    if display is not None:
                        display.change_status("Successfully deleted the downloaded episode")

                # if there are no more files in the feed directory, delete it
                if len(os.listdir(feed_directory)) == 0:
                    os.rmdir(feed_directory)

            database = None if display is None else getattr(display, "database", None)
            if database is not None and self._download_path is not None:
                database.delete_download(self)

    def check_downloaded(self) -> bool:
        """Check whether the episode is downloaded.

        This method updates the downloaded property.

        :returns bool: whether or not the episode is downloaded
        """
        self._downloaded = False
        stored_file = self._stored_download_file()
        if stored_file is not None:
            self._downloaded = stored_file.is_file()
            return self._downloaded
        if self._download_path is not None:
            return self._downloaded

        feed_directory = self._feed_directory()
        if os.path.exists(feed_directory):
            self._downloaded = next(self._legacy_download_files(feed_directory), None) is not None
        return self._downloaded

    def replace_from(self, episode) -> None:
        """Replace metadata from the given episode.

        :param episode the source Episode
        """
        self._ep_id = episode._ep_id
        self._played = episode._played
        self._progress = episode._progress
        self._download_path = episode._download_path
        self._download_checksum = episode._download_checksum

    @property
    def downloaded(self) -> bool:
        """Determines whether the episode is downloaded.

        This method does not guarantee the episode exists, but it determines
        whether it "probably" does. If the download status has not been checked
        since the client started, we check it here and return the result.
        Some methods also update the download status. However, if a file is
        removed externally while the client is still running, the status may
        not be properly updated.

        :returns bool: whether or not the episode is downloaded
        """
        if self._downloaded is None:
            self.check_downloaded()
        return self._downloaded

    @property
    def ep_id(self) -> int:
        """int: the database id of the episode"""
        return self._ep_id

    @ep_id.setter
    def ep_id(self, ep_id) -> None:
        self._ep_id = ep_id

    @property
    def download_path(self):
        """str: normalized path relative to the active download directory."""
        return self._download_path

    @download_path.setter
    def download_path(self, path) -> None:
        self._download_path = path
        self._downloaded = None

    @property
    def download_checksum(self):
        """str: trusted SHA-256 digest for the downloaded episode."""
        return self._download_checksum

    @download_checksum.setter
    def download_checksum(self, checksum) -> None:
        self._download_checksum = checksum

    @property
    def feed_str(self) -> str:
        """str: the string representation of this episode's feed"""
        return str(self._feed)

    @property
    def title(self) -> str:
        """str: the title of the episode"""
        result = self._title
        if result is None:
            result = "Title not available."
        return result

    @property
    def description(self) -> str:
        """str: the description of the episode"""
        result = self._description
        if result is None:
            result = "Description not available."
        return result

    @property
    def link(self) -> str:
        """str: the link of/for the episode"""
        result = self._link
        if result is None:
            result = "Link not available."
        return result

    @property
    def pubdate(self) -> str:
        """str: the publish date of the episode"""
        result = self._pubdate
        if result is None:
            result = "Publish date not available."
        return result

    @property
    def copyright(self) -> str:
        """str: the copyright of the episode"""
        result = self._copyright
        if result is None:
            result = "No copyright specified."
        return result

    @property
    def enclosure(self) -> str:
        """str: the enclosure of the episode"""
        result = self._enclosure
        if result is None:
            result = "Enclosure not available."
        return result

    @property
    def guid(self):
        """str: the opaque RSS identifier for the episode, or None"""
        return self._guid

    @property
    def played(self) -> bool:
        """bool: whether the episode has been played"""
        return self._played

    @played.setter
    def played(self, played) -> None:
        self._played = played

    @property
    def progress(self) -> int:
        """int: progress in milliseconds gathered from database"""
        progress = self._progress
        if progress is None:
            progress = 0
        return progress

    @progress.setter
    def progress(self, progress) -> None:
        self._progress = progress

    @property
    def metadata(self) -> str:
        """str: the user-displayed metadata of the episode"""
        description = (
            helpers.html_to_plain(self.description)
            if helpers.is_true(Config["clean_html_descriptions"])
            else self.description
        )
        description = description.replace("\n", "")
        progress = helpers.seconds_to_time(self.progress / constants.MILLISECONDS_IN_SECOND)
        downloaded = (
            "Episode downloaded and available for offline playback."
            if self.downloaded
            else "Episode not downloaded."
        )
        metadata = (
            "!cb{title}\n"
            "{pubdate}\n\n"
            "{link}\n\n"
            "!cbCopyright:\n"
            "{copyright}\n\n"
            "!cbDownloaded:\n"
            "{downloaded}\n\n"
            "!cbDescription:\n"
            "{description}\n\n"
            "!cbTime Played:\n"
            "{progress}\n".format(
                title=self.title,
                pubdate=self.pubdate,
                link=self.link,
                copyright=self.copyright,
                downloaded=downloaded,
                description=description,
                progress=progress,
            )
        )

        return metadata
