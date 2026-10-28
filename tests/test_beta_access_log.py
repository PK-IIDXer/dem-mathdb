"""Incident-tool unit tests contain only documentation IP addresses."""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("access_log", Path(__file__).resolve().parents[1]/"deploy/beta/access_log.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


@pytest.mark.parametrize("value", ["198.51.100.1/32", "localhost", "::1", "1.2.3.4;id", " 1.2.3.4", "1.2.3.4\n", "01.2.3.4"])
def test_block_argv_rejects_non_ipv4(value):
    with pytest.raises(ValueError):
        tool.firewall_argv(value, "eth0")


def test_block_argv_is_an_argument_list_not_a_shell_string():
    commands = tool.firewall_argv("198.51.100.1", "eth0")
    assert commands["block"] == ["iptables", "-I", "DOCKER-USER", "1", "-i", "eth0", "-s", "198.51.100.1/32", "-j", "DROP"]
    assert commands["check"][1] == "-C" and commands["unblock"][1] == "-D"
    with pytest.raises(ValueError):
        tool.firewall_argv("198.51.100.1", "eth0;id")


def test_summary_filters_time_and_never_exposes_urls():
    def line(stamp, ip, status):
        return json.dumps({"ts":stamp, "status":status, "request":{"remote_ip":ip,"uri":"/private-url?secret=1"}})
    result = tool.summarize([line(100,"198.51.100.1",200),line(130,"198.51.100.1",429),
                             line(130,"198.51.100.2",503),line(1,"198.51.100.2",200),
                             line(201,"198.51.100.2",200),"broken",line(130,"hostname",200)],2,200)
    assert result["sources"][0] == {"remote_ip":"198.51.100.1","total":2,"statuses":{200:1,429:1}}
    assert result["sources"][1]["statuses"] == {503:1}
    assert result["ignored_invalid_rows"] == 2
    assert "private-url" not in json.dumps(result) and "secret" not in json.dumps(result)


def test_non_terminal_output_is_refused(monkeypatch):
    monkeypatch.setattr(tool.os,"geteuid",lambda:0,raising=False)
    monkeypatch.setattr(tool.sys.stdout,"isatty",lambda:False)
    with pytest.raises(PermissionError):
        tool.require_root_terminal()
