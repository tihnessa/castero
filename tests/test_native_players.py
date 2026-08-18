"""Opt-in smoke checks that must be selected by native-player CI jobs."""

import os
import time
import wave

import pytest

from castero.players.mpvplayer import MPVPlayer
from castero.players.vlcplayer import VLCPlayer
from castero.episode import Episode
from castero.feed import Feed


BACKENDS = {"mpv": MPVPlayer, "vlc": VLCPlayer}


@pytest.mark.native_player
def test_selected_native_player_can_play_audio(tmp_path, monkeypatch):
    selected = os.environ.get("CASTERO_NATIVE_PLAYER")
    if selected is None:
        pytest.skip("set CASTERO_NATIVE_PLAYER in a designated native-player job")

    assert selected in BACKENDS, "CASTERO_NATIVE_PLAYER must select mpv or vlc"
    backend = BACKENDS[selected]
    backend.check_dependencies()

    audio_path = tmp_path / "silence.wav"
    with wave.open(str(audio_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8000)

    monkeypatch.setenv("CASTERO_NATIVE_SMOKE", "1")
    episode = Episode(Feed(url="https://example.com/feed", title="Smoke"), title="Silence")
    player = backend("Silence", str(audio_path), episode)
    player.play()
    time.sleep(0.1)
    assert player.state == 1
    assert player._player is not None
    player.stop()
