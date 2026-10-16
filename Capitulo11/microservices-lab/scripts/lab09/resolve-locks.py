"""Refresh exact locks explicitly, using the lab's Python 3.12/Linux environment.
Review the resulting diff and rerun regression/Trivy before publishing a new version.
"""
import argparse,json,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
    if sys.version_info[:2]!=(3,12) or not sys.platform.startswith('linux'):
        raise SystemExit('Resolve locks on Python 3.12/Linux, as in the image')
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',action='store_true');a=parser.parse_args()
    source='requirements-baseline.txt' if a.baseline else 'requirements.txt'
    target='requirements-baseline-lock.txt' if a.baseline else 'requirements-lock.txt'
    with tempfile.TemporaryDirectory() as temp:
        for svc in ['order-service','inventory-service','users-service']:
            report=Path(temp)/f'{svc}.json'
            subprocess.run([sys.executable,'-m','pip','install','--dry-run','--ignore-installed','--only-binary=:all:',
                '--report',str(report),'-r',str(ROOT/svc/source)],check=True)
            data=json.loads(report.read_text())
            lines=sorted(x['metadata']['name']+'=='+x['metadata']['version'] for x in data['install'])
            (ROOT/svc/target).write_text('# Exact resolution for Python 3.12/Linux; review changes before release.\n'+'\n'.join(lines)+'\n')
if __name__=='__main__':main()
