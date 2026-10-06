import logging

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(level: str) -> None:
    logging.basicConfig(level=level.upper(), format=LOG_FORMAT, force=True)
    # httpx logs every request URL at INFO; keep it quiet so the demo logs stay readable.
    logging.getLogger("httpx").setLevel(logging.WARNING)
