import re
from pathlib import Path

from legalrag.web import build

NGINX = Path(__file__).parents[2] / "deploy/nginx.conf"


def test_a_failing_model_call_ends_before_the_proxy_gives_up():
    proxy_wait = int(re.search(r"proxy_read_timeout\s+(\d+)s", NGINX.read_text()).group(1))
    assert build.LLM_TIMEOUT * (build.LLM_RETRIES + 1) + 10 < proxy_wait  # 10 s for the pause between attempts and the search
