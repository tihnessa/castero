import os
from unittest import mock

from castero.datafile import DataFile
from castero.downloadqueue import DownloadQueue


def test_datafile_download(display, tmp_path):
    display.change_status = mock.MagicMock(name="change_status")
    mydownloadqueue = DownloadQueue()
    destination = tmp_path / "download.mp3"
    response = mock.MagicMock()
    response.iter_content.return_value = [b"podcast data"]

    with mock.patch("castero.datafile.Net.Get", return_value=response):
        DataFile.download_to_file(
            "https://example.invalid/episode.mp3",
            str(destination),
            "datafile download name",
            mydownloadqueue,
            display=display,
        )

    while mydownloadqueue.length > 0:
        pass

    assert display.change_status.call_count > 0
    assert destination.read_bytes() == b"podcast data"


def test_datafile_download_bad_url(display):
    display.change_status = mock.MagicMock(name="change_status")
    mydownloadqueue = DownloadQueue()
    url = "https://bad"
    DataFile.download_to_file(
        url, "datafile_download_temp", "datafile download name", mydownloadqueue, display=display
    )
    while mydownloadqueue.length > 0:
        pass
    assert display.change_status.call_count > 0
    assert not os.path.exists("datafile_download_temp")
