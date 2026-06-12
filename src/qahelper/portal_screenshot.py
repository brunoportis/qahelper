"""GNOME screenshot portal integration."""

from __future__ import annotations

import argparse
import shutil
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import unquote, urlparse

from gi.repository import Gio, GLib


def capture(
    destination: Path, timeout_seconds: int = 30, interactive: bool = False
) -> None:
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    sender = connection.get_unique_name().lstrip(":").replace(".", "_")
    token = f"qahelper_{uuid.uuid4().hex}"
    expected_handle = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
    loop = GLib.MainLoop()
    result: dict[str, object] = {}

    def on_response(
        _connection,
        _sender_name,
        _object_path,
        _interface_name,
        _signal_name,
        parameters,
        _user_data,
    ) -> None:
        response_code, response_data = parameters.unpack()
        result["response_code"] = response_code
        result["uri"] = response_data.get("uri")
        loop.quit()

    subscription = connection.signal_subscribe(
        "org.freedesktop.portal.Desktop",
        "org.freedesktop.portal.Request",
        "Response",
        expected_handle,
        None,
        Gio.DBusSignalFlags.NONE,
        on_response,
        None,
    )

    def on_timeout() -> bool:
        result["timed_out"] = True
        loop.quit()
        return GLib.SOURCE_REMOVE

    timeout = GLib.timeout_add_seconds(timeout_seconds, on_timeout)
    try:
        options = {
            "interactive": GLib.Variant("b", interactive),
            "handle_token": GLib.Variant("s", token),
        }
        reply = connection.call_sync(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Screenshot",
            "Screenshot",
            GLib.Variant("(sa{sv})", ("", options)),
            GLib.VariantType("(o)"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )
        returned_handle = reply.unpack()[0]
        if returned_handle != expected_handle:
            raise RuntimeError(f"Portal retornou um identificador inesperado: {returned_handle}")

        loop.run()
    finally:
        connection.signal_unsubscribe(subscription)
        GLib.source_remove(timeout)

    if result.get("timed_out"):
        raise RuntimeError("O portal não respondeu dentro do tempo limite.")
    if result.get("response_code") != 0:
        raise RuntimeError("A captura de tela foi cancelada.")

    uri = result.get("uri")
    if not isinstance(uri, str):
        raise RuntimeError("O portal não retornou a imagem capturada.")
    parsed_uri = urlparse(uri)
    if parsed_uri.scheme != "file":
        raise RuntimeError(f"O portal retornou uma URI não suportada: {uri}")
    shutil.copyfile(unquote(parsed_uri.path), destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--delay", type=float, default=0)
    args = parser.parse_args()
    try:
        if args.delay:
            print(f"Captura em {args.delay:g} segundos...", flush=True)
            time.sleep(args.delay)
        capture(args.destination, interactive=args.interactive)
    except Exception as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
