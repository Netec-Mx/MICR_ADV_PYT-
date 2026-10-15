"""Read Docker sizes and actual Trivy JSON; fail missing/incomplete evidence."""
import argparse,json
from pathlib import Path
SERVICES=('order-service','inventory-service','users-service')
def reduction(baseline,optimized):
    if baseline<=0 or optimized<=0:raise ValueError('Image sizes must be positive')
    return 100*(baseline-optimized)/baseline

def vulnerabilities(report):
    if not isinstance(report,dict) or report.get('SchemaVersion')!=2 or not isinstance(report.get('Results'),list) or not report.get('Results'):
        raise ValueError('Incomplete Trivy JSON: SchemaVersion 2 and Results required')
    if not report.get('Metadata'):raise ValueError('Trivy image metadata missing')
    findings={}
    for result in report['Results']:
        for v in result.get('Vulnerabilities') or []:
            if v['Severity'] not in ('HIGH','CRITICAL'):continue
            key=(result.get('Target',''),v['PkgName'],v.get('InstalledVersion',''),v['VulnerabilityID'])
            findings[key]=v
    return {'high_critical':len(findings),'fixable':sum(bool(v.get('FixedVersion')) for v in findings.values()),
        'findings':[{'target':k[0],'package':k[1],'installed':k[2],'id':k[3],
                     'severity':v['Severity'],'fixed':v.get('FixedVersion','')} for k,v in sorted(findings.items())]}

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['sizes','cves']);p.add_argument('directory',type=Path);a=p.parse_args();rows=[]
    for svc in SERVICES:
        values=[]
        for kind in ('baseline','optimized'):
            suffix='inspect' if a.mode=='sizes' else 'trivy'
            data=json.loads((a.directory/f'{svc}-{kind}-{suffix}.json').read_text())
            values.append(data[0]['Size'] if a.mode=='sizes' else vulnerabilities(data))
        row={'service':svc,'baseline':values[0],'optimized':values[1]}
        if a.mode=='sizes':row.update(reduction_percent=round(reduction(*values),2),passes_40_percent=reduction(*values)>=40)
        rows.append(row)
    (a.directory/f'{a.mode}-summary.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(rows,indent=2))
    if a.mode=='sizes' and not all(row['passes_40_percent'] for row in rows):raise SystemExit('Reduction target >=40% not achieved for every service')
if __name__=='__main__':main()
