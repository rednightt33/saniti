"""ERRORS M322 live check: a job that prints no finish marker of its own; the runner's wrapper must print JOB_EXIT 0."""
import json
print('OUT ' + json.dumps({'q': 'm322_probe', 'note': 'no JOB_DONE printed by the job'}), flush=True)
