"""Optional bearer for validators retained from earlier labs."""
import os,json
from pathlib import Path
def auth_headers():
    token=os.getenv('LAB_API_TOKEN','')
    if os.getenv('LAB_API_TOKEN_FILE'):token=json.loads(Path(os.environ['LAB_API_TOKEN_FILE']).read_text())['access_token']
    return {'Authorization':'Bearer '+token} if token else {}
