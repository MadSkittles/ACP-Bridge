from acp_bridge.workspace import is_path_allowed


def test_posix_path_allowed_only_under_configured_root() -> None:
    assert is_path_allowed("/Users/dev/repo/sub", ["/Users/dev/repo"])
    assert not is_path_allowed("/Users/dev/repo-other", ["/Users/dev/repo"])


def test_windows_path_allowed_only_under_configured_root() -> None:
    assert is_path_allowed(
        r"C:\Users\dev\repo\subdir",
        [r"C:\Users\dev\repo"],
        platform="windows",
    )
    assert not is_path_allowed(
        r"C:\Users\dev\repo-other",
        [r"C:\Users\dev\repo"],
        platform="windows",
    )


def test_windows_path_check_is_case_insensitive() -> None:
    assert is_path_allowed(
        r"c:\users\DEV\repo",
        [r"C:\Users\dev\repo"],
        platform="windows",
    )


def test_relative_paths_are_rejected() -> None:
    assert not is_path_allowed("repo", ["/Users/dev/repo"])
