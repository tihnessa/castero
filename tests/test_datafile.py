import hashlib
from pathlib import Path
from unittest import mock

import requests

from castero.datafile import DataFile
from castero.downloadqueue import DownloadQueue
from castero.episode import Episode
from castero.feed import Feed


def response_with_chunks(*chunks):
    response = mock.MagicMock()
    response.iter_content.return_value = chunks
    return response


@mock.patch("castero.datafile.Net.Get")
def test_datafile_download(get, tmp_path):
    response = response_with_chunks(b"some ", b"", b"audio")
    get.return_value = response
    display = mock.MagicMock()
    display.menus_valid = True
    download_queue = mock.MagicMock()
    download_queue.length = 1
    output_path = tmp_path / "episode.mp3"
    completed = mock.MagicMock()

    DataFile.download_to_file(
        "https://example.com/episode.mp3",
        output_path,
        "episode name",
        download_queue,
        display=display,
        on_complete=completed,
    )

    get.assert_called_once_with("https://example.com/episode.mp3", stream=True)
    response.raise_for_status.assert_called_once_with()
    assert output_path.read_bytes() == b"some audio"
    completed.assert_called_once_with(
        output_path, hashlib.sha256(b"some audio").hexdigest()
    )
    display.change_status.assert_any_call("Episode successfully downloaded.")
    assert display.menus_valid is False
    download_queue.next.assert_called_once_with()


@mock.patch("castero.datafile.Net.Get")
def test_datafile_download_http_error(get, tmp_path):
    response = response_with_chunks(b"not audio")
    response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Client Error")
    get.return_value = response
    display = mock.MagicMock()
    download_queue = mock.MagicMock()
    output_path = tmp_path / "episode.mp3"

    DataFile.download_to_file(
        "https://example.com/missing.mp3",
        output_path,
        "missing episode",
        download_queue,
        display=display,
    )

    assert not output_path.exists()
    response.iter_content.assert_not_called()
    display.change_status.assert_called_once_with("RequestException: 404 Client Error")
    download_queue.next.assert_called_once_with()


@mock.patch("castero.datafile.Net.Get")
def test_datafile_download_removes_partial_file(get, tmp_path):
    def interrupted_chunks():
        yield b"partial audio"
        raise requests.exceptions.ConnectionError("stream interrupted")

    response = response_with_chunks()
    response.iter_content.return_value = interrupted_chunks()
    get.return_value = response
    display = mock.MagicMock()
    download_queue = mock.MagicMock()
    download_queue.length = 1
    output_path = tmp_path / "episode.mp3"
    completed = mock.MagicMock()

    DataFile.download_to_file(
        "https://example.com/episode.mp3",
        output_path,
        "episode name",
        download_queue,
        display=display,
        on_complete=completed,
    )

    assert not output_path.exists()
    assert not Path(str(output_path) + ".part").exists()
    completed.assert_not_called()
    display.change_status.assert_called_with("RequestException: stream interrupted")
    assert mock.call("Episode successfully downloaded.") not in display.change_status.call_args_list
    download_queue.next.assert_called_once_with()


@mock.patch("castero.datafile.Net.Get")
def test_datafile_download_request_error_advances_queue(get, tmp_path):
    get.side_effect = requests.exceptions.ConnectionError("connection failed")
    display = mock.MagicMock()
    download_queue = mock.MagicMock()
    output_path = tmp_path / "episode.mp3"

    DataFile.download_to_file(
        "https://example.com/episode.mp3",
        output_path,
        "episode name",
        download_queue,
        display=display,
    )

    assert not output_path.exists()
    display.change_status.assert_called_once_with("RequestException: connection failed")
    download_queue.next.assert_called_once_with()


@mock.patch("castero.datafile.Net.Get")
def test_datafile_download_without_display(get, tmp_path):
    get.return_value = response_with_chunks(b"audio")
    download_queue = mock.MagicMock()
    output_path = tmp_path / "episode.mp3"

    DataFile.download_to_file(
        "https://example.com/episode.mp3",
        output_path,
        "episode name",
        download_queue,
    )

    assert output_path.read_bytes() == b"audio"
    download_queue.next.assert_called_once_with()


@mock.patch("castero.datafile.Net.Get")
def test_datafile_cancelled_download_removes_partial_file(get, tmp_path):
    feed = Feed(url="feed url", title="feed title")
    episode = Episode(feed, ep_id=1, title="episode")
    next_episode = Episode(feed, ep_id=2, title="next episode")
    download_queue = DownloadQueue()
    episode.download = mock.MagicMock()
    next_episode.download = mock.MagicMock()
    download_queue.add(episode)
    download_queue.add(next_episode)
    download_queue.start()

    def cancelled_chunks():
        yield b"partial audio"
        download_queue.remove(episode)
        yield b"cancelled audio"

    response = response_with_chunks()
    response.iter_content.return_value = cancelled_chunks()
    get.return_value = response
    output_path = tmp_path / "feed" / "episode.mp3"
    DataFile.ensure_path(output_path)
    completed = mock.MagicMock()

    DataFile.download_to_file(
        "https://example.com/episode.mp3",
        output_path,
        "episode name",
        download_queue,
        on_complete=completed,
    )

    assert not output_path.exists()
    assert not output_path.parent.exists()
    completed.assert_not_called()
    assert download_queue.length == 1
    next_episode.download.assert_called_once_with(download_queue, None)


@mock.patch("castero.datafile.Net.Get")
def test_datafile_cancellation_prevents_final_promotion(get, tmp_path):
    feed = Feed(url="feed url", title="feed title")
    episode = Episode(feed, ep_id=1, title="episode")
    download_queue = DownloadQueue()
    episode.download = mock.MagicMock()
    download_queue.add(episode)
    download_queue.start()

    def chunks_cancelled_at_completion():
        yield b"apparently complete audio"
        download_queue.remove(episode)

    response = response_with_chunks()
    response.iter_content.return_value = chunks_cancelled_at_completion()
    get.return_value = response
    output_path = tmp_path / "feed" / "episode.mp3"
    DataFile.ensure_path(output_path)
    completed = mock.MagicMock()

    DataFile.download_to_file(
        "https://example.com/episode.mp3",
        output_path,
        "episode name",
        download_queue,
        on_complete=completed,
    )

    assert not output_path.exists()
    assert not Path(str(output_path) + ".part").exists()
    completed.assert_not_called()
