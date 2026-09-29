import unittest
from unittest.mock import patch

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
