import collections
import os
import requests
from shutil import copyfile

import castero
from castero.net import Net


class DataFile:
    """Extendable class for objects with filesystem data.

    Used when handling files with data that can reasonably be stored in a
    dictionary. Particularly used in the Config class and the Feeds class.

    Extended by classes which are based on a data file.
    """

    PACKAGE = os.path.dirname(__file__)
    HOME = os.path.expanduser("~")
    XDG_CONFIG_HOME = os.getenv("XDG_CONFIG_HOME", os.path.join(HOME, ".config"))
    XDG_DATA_HOME = os.getenv("XDG_DATA_HOME", os.path.join(HOME, ".local", "share"))
    CONFIG_DIR = os.path.join(XDG_CONFIG_HOME, castero.__title__)
    DATA_DIR = os.path.join(XDG_DATA_HOME, castero.__title__)
    DEFAULT_DOWNLOADED_DIR = os.path.join(DATA_DIR, "downloaded")

    def __init__(self, path, default_path) -> None:
        """
        :param path the path to the data file
        :param default_path the path to the default data file
        """
        assert os.path.exists(default_path)

        self.data = collections.OrderedDict()
        self._path = path
        self._default_path = default_path

        # if path doesn't exit, create it based on default_path
        if not os.path.exists(self._path):
            DataFile.ensure_path(self._path)
            copyfile(self._default_path, self._path)

    def __iter__(self) -> iter:
        """Iterator for the keys of self.data

        In order to iterate over data values, you should use something like:
        for key in file_instance:
            value = file_instance[key]
        """
        return self.data.__iter__()

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, item):
        if item in self.data:
            return self.data[item]

    def __setitem__(self, key, value):
        self.data[key] = value

    def __delitem__(self, key):
        self.data.pop(key, None)

    @staticmethod
    def ensure_path(filename):
        """Ensure that the path to the filename exists, creating it if needed."""
        path = os.path.dirname(filename)
        if not os.path.exists(path):
            os.makedirs(path)

    @staticmethod
    def download_to_file(url, file, name, download_queue, display=None):
        """Downloads a URL to a local file.

        :param url: the source url
        :param file the destination path
        :param name the user-friendly name of the content
        :param download_queue the download_queue overseeing this download
        :param display (optional) the display to write status updates to
        """
        chunk_size = 1024
        chunk_size_label = "KB"
        download_started = False
        download_completed = False

        try:
            if getattr(download_queue, "cancelled", False) is True:
                return

            response = Net.Get(url, stream=True)
            response.raise_for_status()

            with open(file, "wb") as handle:
                download_started = True
                downloaded = 0
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if getattr(download_queue, "cancelled", False) is True:
                        break
                    if display is not None:
                        status_str = 'Downloading "%s": %d%s' % (
                            name,
                            downloaded / chunk_size,
                            chunk_size_label,
                        )
                        if download_queue.length > 1:
                            status_str += " (+%d downloads in queue)" % (download_queue.length - 1)

                        display.change_status(status_str)
                    if chunk:
                        handle.write(chunk)
                    downloaded += len(chunk)

            download_completed = getattr(download_queue, "cancelled", False) is not True
            if download_completed and display is not None:
                display.change_status("Episode successfully downloaded.")
                display.menus_valid = False
        except requests.exceptions.RequestException as e:
            if display is not None:
                display.change_status("RequestException: %s" % str(e))
        finally:
            try:
                cancelled = getattr(download_queue, "cancelled", False) is True
                should_remove = cancelled or (download_started and not download_completed)
                if should_remove and os.path.exists(file):
                    os.remove(file)
                if cancelled:
                    directory = os.path.dirname(file)
                    if os.path.isdir(directory) and len(os.listdir(directory)) == 0:
                        os.rmdir(directory)
            finally:
                download_queue.next()

    def load(self) -> None:
        """Loads the data file."""
        pass

    def write(self) -> None:
        """Writes to the data file."""
        pass
