"""Every plugin here conforms to the class contract (plugin API 2.2): liminal_libs.sources.conformance, read from the
plugin alone (nothing runs)."""
from __future__ import annotations

import re

import plugin_platform_docker as module
from liminal_libs.sources.conformance import assert_module_conforms
from liminal_libs.ui import STATIC


def test_every_plugin_here_conforms_to_the_class_contract():
    found = assert_module_conforms(module)
    assert found and all(p.api == "2.2" and not p.is_record for p in found)
    assert {p.SYSTEM for p in found} == {"platform"} and {p.KIND for p in found} == {"machine"}
    assert {p.name for p in found} == {"docker"} and {p.ICON for p in found} == {"docker"}


def test_its_icon_is_one_the_platforms_page_draws():
    """The tray draws the icon by its name in the library's icons.js: a name it does not have draws nothing."""
    drawn = set(re.findall(r"^\s*([a-z]+):\s*'", (STATIC / "icons.js").read_text(encoding="utf-8"), re.M))
    assert module.MACHINE.ICON in drawn  # Docker's whale with its containers, by the user's ask


def test_it_is_drawn_under_the_platforms_virtualization_plugins():
    """Its section of the platform's list (liminal-platform 0.26.0; the user, 2026-11-15: "platform needs a virtualization
    plugins section"; "just like cloud plugins"): Virtualization plugins, beside the machine's own, the OS and the cloud
    plugins."""
    assert {p.SECTION for p in assert_module_conforms(module)} == {"virtualization"}
