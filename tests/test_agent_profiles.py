from acp_bridge.agent_profiles import AgentProfile, default_agent_profiles


def test_codex_default_command_renders_cwd_and_prompt() -> None:
    profile = default_agent_profiles()["codex"]

    command = profile.render_command(cwd=r"C:\repo", prompt="fix tests")

    assert command == [
        "codex",
        "exec",
        "--cd",
        r"C:\repo",
        "--ask-for-approval",
        "never",
        "--sandbox",
        "danger-full-access",
        "fix tests",
    ]


def test_claude_default_command_renders_prompt() -> None:
    profile = default_agent_profiles()["claude"]

    assert profile.render_command(cwd=r"C:\repo", prompt="summarize") == [
        "claude",
        "--print",
        "--permission-mode",
        "bypassPermissions",
        "summarize",
    ]


def test_profile_adds_extra_flags_before_prompt_placeholder() -> None:
    profile = AgentProfile(
        executable="tool",
        args=["run", "{extra_flags}", "{prompt}"],
        extra_flags=["--json"],
    )

    assert profile.render_command(cwd="/repo", prompt="hello") == ["tool", "run", "--json", "hello"]


def test_profile_env_merges_over_base_environment() -> None:
    profile = AgentProfile(executable="tool", env={"A": "override", "B": "2"})

    env = profile.render_env({"A": "1"})

    assert env["A"] == "override"
    assert env["B"] == "2"
