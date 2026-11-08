import contextlib
import io
import json
import unittest

from composition_sensor import EventHandler


class SensorTests(unittest.TestCase):
    def test_only_finalized_event_is_reported_without_payload(self):
        handler = EventHandler()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            handler.changed(None, None, 2, None)
            handler.changed(None, None, 3, None)
        self.assertEqual(json.loads(output.getvalue()),
                         {'event': 'composition_finalized', 'change_type': 3})


if __name__ == '__main__': unittest.main()
