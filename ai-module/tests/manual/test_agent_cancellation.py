import os
import sys
import unittest
from unittest.mock import patch

_MANUAL_DIR = os.path.dirname(os.path.abspath(__file__))
_AI_ROOT = os.path.dirname(os.path.dirname(_MANUAL_DIR))
if _AI_ROOT not in sys.path:
    sys.path.insert(0, _AI_ROOT)

from core.agent import Agent
from core.cancellation import CancellationToken, StreamCancelled


class AgentCancellationTest(unittest.TestCase):
    def test_cancelled_stream_does_not_start_another_model_request(self):
        token = CancellationToken()
        token.cancel()
        agent = Agent("report", "system", [], "http://model", "key")

        with patch("core.agent.requests.post") as post:
            with self.assertRaises(StreamCancelled):
                list(agent.run_stream("prompt", cancellation=token))

        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
