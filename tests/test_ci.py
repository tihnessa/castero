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
    assert "mpv-dev-x86_64-20260607-git-71ebd08.7z" in workflow
    assert "faa0be46643cd889a1d816696f60b9962d7bb70e9d9d6e619da368d0b22211d6" in workflow
    assert "curl.exe --fail --location --retry 3" in workflow
    assert "Get-FileHash -Algorithm SHA256" in workflow
    assert "Invoke-WebRequest -Uri" not in workflow
    assert "libmpv-2.dll" in workflow
    assert "$env:GITHUB_PATH" in workflow


def test_ci_does_not_use_retired_code_climate_reporter():
    workflow = WORKFLOW.read_text()

    assert "codeclimate.com/downloads/test-reporter" not in workflow
    assert "cc-test-reporter" not in workflow
