"""CLI entry point: ``deepecohab-app [--host --port --debug --no-browser]``."""

import argparse
import logging
import webbrowser
from threading import Timer

from deepecohab.app import create_app
from deepecohab.plotting.export import ensure_chrome_available

logger = logging.getLogger(__name__)


def main() -> None:
	"""Parse CLI args and run the app."""
	parser = argparse.ArgumentParser(prog="deepecohab-app")
	parser.add_argument("--host", default="127.0.0.1")
	parser.add_argument("--port", type=int, default=8050)
	parser.add_argument("--debug", action="store_true")
	parser.add_argument("--no-browser", action="store_true")
	args = parser.parse_args()

	if not ensure_chrome_available():
		logger.warning("kaleido has no Chrome binary; plot export will be disabled.")

	app = create_app()

	if not args.no_browser:
		url = f"http://{args.host}:{args.port}"
		Timer(1, lambda: webbrowser.open(url)).start()

	app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
	main()
