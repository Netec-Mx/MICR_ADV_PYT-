import json,subprocess,sys
from pathlib import Path
import pytest
from report import reduction,vulnerabilities,SERVICES
REPORT=Path(__file__).resolve().parents[1]/'scripts/lab09/report.py'
@pytest.mark.parametrize('baseline,optimized,expected',[(1000,600,40),(1000,1200,-20),(1000,100,90)])
def test_size_percentage_from_bytes(baseline,optimized,expected):assert reduction(baseline,optimized)==expected
@pytest.mark.parametrize('size',[0,-1])
def test_invalid_baseline_is_rejected(size):
    with pytest.raises(ValueError):reduction(size,100)
def test_scan_deduplicates_package_findings_and_keeps_unfixed():
    v={'VulnerabilityID':'CVE-X','PkgName':'a','InstalledVersion':'1','Severity':'HIGH','FixedVersion':'2'}
    d={'SchemaVersion':2,'Metadata':{'OS':{'Family':'debian'}},'Results':[{'Target':'root','Vulnerabilities':[v,v,dict(v,VulnerabilityID='CVE-Y',Severity='CRITICAL',FixedVersion=''),dict(v,Severity='LOW')]}]}
    result=vulnerabilities(d)
    # LOW record has a separate severity and must not overwrite the HIGH finding.
    assert result['high_critical']==2 and result['fixable']==1
@pytest.mark.parametrize('doc',[{}, {'SchemaVersion':2,'Metadata':{},'Results':[]},{'SchemaVersion':2,'Metadata':{'OS':'debian'}}])
def test_incomplete_scan_cannot_be_reported_as_zero(doc):
    with pytest.raises(ValueError):vulnerabilities(doc)
def test_threshold_fails_after_writing_real_summary(tmp_path):
    for svc in SERVICES:
        for kind,size in [('baseline',1000),('optimized',700)]:
            (tmp_path/f'{svc}-{kind}-inspect.json').write_text(json.dumps([{'Size':size}]))
    result=subprocess.run([sys.executable,str(REPORT),'sizes',str(tmp_path)],capture_output=True,text=True)
    assert result.returncode!=0 and 'not achieved' in result.stderr
    summary=json.loads((tmp_path/'sizes-summary.json').read_text())
    assert len(summary)==3 and all(s['passes_40_percent'] is False for s in summary)
def test_missing_evidence_fails(tmp_path):
    result=subprocess.run([sys.executable,str(REPORT),'cves',str(tmp_path)],capture_output=True,text=True)
    assert result.returncode!=0 and not (tmp_path/'cves-summary.json').exists()
