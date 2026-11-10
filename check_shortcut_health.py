"""Show the latest JARVIS shortcut diagnostics without opening private transcripts."""
import json
from datetime import datetime
from pathlib import Path

folder = Path(__file__).resolve().parent / 'diagnostic_results'
logs = sorted(folder.glob('shortcut_health_*.jsonl'), key=lambda p: p.stat().st_mtime, reverse=True)
print('JARVIS shortcut diagnostic (local metadata only)\n')
if not logs:
    print('No health log yet. Restart the updated JARVIS and try the shortcut.')
else:
    path = logs[0]
    print('Latest log:', path.name)
    events = []
    for line in path.read_text(encoding='utf-8').splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            print('A damaged log entry was skipped.')
    if events:
        for event in events[-25:]:
            print(json.dumps(event, ensure_ascii=False))
        try:
            age = (datetime.now().astimezone() - datetime.fromisoformat(events[-1]['time'])).total_seconds()
            print('\nLast recorded activity: approximately %d seconds ago.' % max(0, age))
            if age > 120:
                print('No recent heartbeat: JARVIS may be closed, frozen, or logging may have failed.')
        except (KeyError, TypeError, ValueError):
            print('Could not determine last activity time.')
    else:
        print('The latest health log is empty.')
print('\nNo audio, transcript, clipboard contents, or other app keystrokes are collected here.')
print('A missing hotkey event alone cannot identify why Windows did not deliver it.')
