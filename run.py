"""Start FinTrack using regular dependencies or the optional local .runtime folder."""
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
if (BASE / '.runtime').is_dir():
    sys.path.insert(0, str(BASE / '.runtime'))
os.chdir(BASE)
if __name__ == '__main__':
    import uvicorn
    uvicorn.run('app:app', host=os.getenv('HOST', '127.0.0.1'), port=int(os.getenv('PORT', '8010')))
