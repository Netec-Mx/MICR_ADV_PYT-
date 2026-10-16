"""Request-window SLOs from raw k6 samples; missing data is never success."""
import argparse,json,math
from pathlib import Path
from datetime import datetime

def instant(s):return datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()
def summarize(samples,timeline=None):
 groups={}
 for line in samples:
  x=json.loads(line)
  if x.get('type')!='Point' or x.get('metric') not in ('lab12_errors','lab12_latency','lab12_slow_requests'):continue
  d=x['data'];t=instant(d['time']);phase='whole-run'
  if timeline and 'injection_requested' in timeline and 'cleanup_confirmed' in timeline:
   phase='baseline' if t<instant(timeline['injection_requested']) else ('fault-window' if t<=instant(timeline['cleanup_confirmed']) else 'recovery')
  key=(d['tags']['service'],phase);g=groups.setdefault(key,{'requests':0,'bad':0,'latencies':[],'slow':0,'slow_samples':0})
  if x['metric']=='lab12_errors':g['requests']+=1;g['bad']+=int(d['value']!=0)
  elif x['metric']=='lab12_latency':g['latencies'].append(d['value'])
  else:g['slow']+=int(d['value']);g['slow_samples']+=1
 result=[]
 for (service,phase),g in sorted(groups.items()):
  n=g['requests'];values=sorted(g.pop('latencies'));b=g['bad'];slow=g.pop('slow');latency_complete=g.pop('slow_samples')==n and n>0
  result.append(dict(service=service,phase=phase,**g,availability=None if not n else 1-b/n,availability_budget_consumed=None if not n else b/(0.005*n),latency_budget_consumed=None if not latency_complete else slow/(0.01*n),p95_ms=None if not values else values[math.ceil(.95*len(values))-1],latency_good_fraction=None if not latency_complete else 1-slow/n))
 return result
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('directory',type=Path);args=a.parse_args();p=args.directory
 timeline=json.loads((p/'timeline.json').read_text()) if (p/'timeline.json').exists() else None
 result=summarize((p/'samples.json').read_text().splitlines(),timeline)
 (p/'slo-report.json').write_text(json.dumps(result,indent=2))
 text='# Postmortem · Lab 12\n\nEstado: completar con evidencias del clúster.\n\n## Ventanas y resultados\n\n```json\n'+json.dumps(result,indent=2)+'\n```\n\n## Línea de tiempo UTC\n\n```json\n'+json.dumps(timeline,indent=2)+'\n```\n\n## Impacto\n\nAnotar solicitudes afectadas y alcance observado. Estas muestras no prueban impacto mensual ni en producción.\n\n## Causa y factores\n\nSeparar evidencia (logs, traces, eventos, alertas) de hipótesis. El fallo inyectado no demuestra por sí solo la causa de todas las respuestas.\n\n## Recuperación\n\nAdjuntar smoke posterior, pods Ready y Argo Synced/Healthy. Medir tiempos reales; si faltan datos, escribir «por comprobar».\n\n## Acciones\n\n| Acción | Responsable | Fecha | Evidencia de cierre |\n|---|---|---|---|\n| Completar a partir del diagnóstico | Por asignar | Por definir | Por comprobar |\n'
 (p/'postmortem.md').write_text(text);print(json.dumps(result,indent=2))
