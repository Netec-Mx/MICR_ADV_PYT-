import pytest
from traffic import check_distribution
@pytest.mark.parametrize('counts,n,p',[({'v1':360,'v2':40},400,10),({'v1':200,'v2':200},400,50),({'v2':400},400,100),({'v1':400},400,0)])
def test_valid_distribution(counts,n,p):assert check_distribution(counts,n,p)==counts.get('v2',0)/n
@pytest.mark.parametrize('counts,n,p',[({'v1':400},400,10),({'v1':350,'v2':50},400,50),({'v1':1,'v2':399},400,100),({'v1':360,'bad':40},400,10),({'v1':350,'v2':40},400,10),({'v1':18,'v2':2},20,10)])
def test_wrong_empty_or_small_sample_fails(counts,n,p):
    with pytest.raises(AssertionError):check_distribution(counts,n,p)
