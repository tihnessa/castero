from pathlib import Path


WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "ci.yml"


def test_ci_covers_all_supported_operating_systems():
    workflow = WORKFLOW.read_text()

    assert "ubuntu-latest" in workflow
    assert "macos-latest" in workflow
    assert "windows-latest" in workflow


def test_ci_has_required_native_player_matrix():
    workflow = WORKFLOW.read_text()

    assert "native-player" in workflow
    assert "player: [vlc, mpv]" in workflow
    assert "CASTERO_NATIVE_PLAYER" in workflow
    assert "continue-on-error" not in workflow


def test_ci_exports_nonstandard_mpv_library_locations():
    workflow = WORKFLOW.read_text()

    assert 'DYLD_LIBRARY_PATH=$(brew --prefix mpv)/lib' in workflow
    assert 'lib\\mpvio.install\\tools' in workflow
    assert "$env:GITHUB_PATH" in workflow
