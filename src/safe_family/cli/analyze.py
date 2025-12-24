# CLI wrapper with __main__
# python -m safe_family.cli.analyze --range last_5min
"""CLI for URL analysis."""

import argparse
import logging
import sys

from src.safe_family.urls.analyzer import get_time_range, log_analysis

logger = logging.getLogger(__name__)


def main(args: list[str] = None) -> int:
    """Analize URL."""
    parser = argparse.ArgumentParser(
        description="Analyze URLs for safety and metadata",
    )
    parser.add_argument(
        "--range",
        choices=["yesterday", "last_hour", "last_5min"],
        help="Predefined time range",
    )
    parser.add_argument(
        "--custom",
        nargs=2,
        metavar=("START", "END"),
        help="Custom time range: start_time end_time (format: 'YYYY-MM-DD HH:MM:SS')",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    parsed_args = parser.parse_args(args)
    if parsed_args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    # Get URLs from args or file
    start_time, end_time = get_time_range(
        range=parsed_args.range,
        custom=parsed_args.custom,
    )
    logger.debug("Analyzing URLs from %s to %s", start_time, end_time)
    log_analysis(start_time, end_time)


if __name__ == "__main__":
    sys.exit(main())
