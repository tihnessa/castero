import os

from castero.player import Player, PlayerDependencyError, dependency_install_hint
from castero import helpers, constants


class MPVPlayer(Player):
    """Interface for the mpv media player."""

    NAME = "mpv"

    def __init__(self, title, path, episode) -> None:
        super().__init__(title, path, episode)

        import mpv

        self.mpv = mpv

    @staticmethod
    def check_dependencies():
        """Checks whether dependencies are met for playing a player."""
        try:
            import mpv
        except ImportError as error:
            raise PlayerDependencyError(
                "The python-mpv package is not installed. %s" % dependency_install_hint("mpv")
            ) from error
        except (NameError, OSError, AttributeError) as error:
            raise PlayerDependencyError(
                "The mpv Python binding was found, but libmpv could not be loaded: %s. %s"
                % (error, dependency_install_hint("mpv"))
            ) from error

        try:
            instance = mpv.MPV()
            instance.terminate()
        except (NameError, OSError, AttributeError) as error:
            raise PlayerDependencyError(
                "The mpv Python binding was found, but libmpv could not be loaded: %s. %s"
                % (error, dependency_install_hint("mpv"))
            ) from error

    def _create_player(self) -> None:
        """Creates the player object while making sure it is a valid file."""
        options = {"ao": "null"} if os.getenv("CASTERO_NATIVE_SMOKE") else {}
        self._player = self.mpv.MPV(**options)
        self._player.vid = False
        self._player.pause = False

        self._duration = 5

    def play(self) -> None:
        """Plays the media."""
        if self._player is None:
            self._create_player()

        self._player.play(self._path)

        self._player.pause = False
        self._state = 1

    def play_from(self, seconds) -> None:
        """play media from point."""
        if self._player is None:
            self._create_player()

        timestamp = helpers.seconds_to_time(seconds)
        self._player.start = timestamp

        self.play()

    def stop(self) -> None:
        """Stops the media."""
        if self._player is not None:
            self._player.terminate()
            self._state = 0

    def pause(self) -> None:
        """Pauses the media."""
        if self._player is not None:
            self._player.pause = True
            self._state = 2

    def seek(self, direction, amount) -> None:
        """Seek forward or backward in the media."""
        assert direction == 1 or direction == -1
        if self._player is not None:
            self._player.seek(direction * amount)

    def set_rate(self, rate) -> None:
        """Set the playback speed."""
        if self._player is not None:
            self._player.speed = rate

    def set_volume(self, volume) -> None:
        """Set the player volume."""
        if self._player is not None:
            self._player.volume = volume

    @property
    def duration(self) -> int:
        """int: the duration of the player"""
        result = 0
        if self._player is not None:
            d = self._player.duration
            result = 5000 if d is None else d * constants.MILLISECONDS_IN_SECOND
        return result

    @property
    def volume(self) -> int:
        """int: the volume of the player"""
        if self._player is not None:
            return self._player.volume

    @property
    def time(self) -> int:
        """int: the current time of the player"""
        if self._player is not None:
            t = self._player.time_pos
            return 0 if t is None else t * constants.MILLISECONDS_IN_SECOND

    @property
    def time_str(self) -> str:
        """str: the formatted time and duration of the player"""
        result = "00:00:00/00:00:00"
        if self._player is not None:
            time_seconds = int(self.time / constants.MILLISECONDS_IN_SECOND)
            length_seconds = int(self.duration / constants.MILLISECONDS_IN_SECOND)
            t = helpers.seconds_to_time(time_seconds)
            d = helpers.seconds_to_time(length_seconds)
            result = "%s/%s" % (t, d)
        return result
