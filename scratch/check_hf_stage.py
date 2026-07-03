import subprocess
import json
import sys

try:
    out = subprocess.check_output(['hf', 'spaces', 'info', 'kkalra/vera-magicpin', '--json'])
    data = json.loads(out)
    print(json.dumps(data.get('runtime', {}), indent=2))
except Exception as e:
    print(f"Error: {e}")
