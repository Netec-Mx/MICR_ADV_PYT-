"""Desde la raíz: python scripts/validate.py; cada servicio usa su venv."""
from pathlib import Path
import argparse
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--python', help='Intérprete común explícito, solo si tiene todas las dependencias')
args = parser.parse_args()
for service in ('order-service', 'inventory-service'):
    venv = root / service / '.venv312'
    executable = Path(args.python).absolute() if args.python else (
        venv / 'Scripts/python.exe' if sys.platform == 'win32' else venv / 'bin/python')
    if not executable.is_file():
        raise SystemExit(f'Falta el intérprete de {service}: {executable}. Completa el paso 3.')
    print(f'Validando {service}', flush=True)
    result = subprocess.run([str(executable), '-m', 'pytest', 'tests/', '-q'], cwd=root/service)
    if result.returncode:
        raise SystemExit(result.returncode)
print('CÓDIGO Y CONTRATOS APROBADOS. Compose/HTTP se verifica por separado.')
