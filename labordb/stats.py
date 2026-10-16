"""Small-sample methods, implemented with the standard library."""
import math
from statistics import NormalDist

def wilson(x,n,confidence=.95):
    if not n: return (None,None)
    z=NormalDist().inv_cdf((1+confidence)/2);p=x/n;den=1+z*z/n
    mid=(p+z*z/(2*n))/den
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return max(0,mid-half),min(1,mid+half)

def difference_ci(a,n1,c,n0,confidence=.95):
    if not n1 or not n0: return (None,None)
    p=a/n1;q=c/n0;lo1,hi1=wilson(a,n1,confidence);lo0,hi0=wilson(c,n0,confidence)
    return max(-1,p-q-math.hypot(p-lo1,hi0-q)),min(1,p-q+math.hypot(hi1-p,q-lo0))

def hypergeom(n,k,draw):
    den=math.comb(n,draw)
    return {a:math.comb(k,a)*math.comb(n-k,draw-a)/den
            for a in range(max(0,draw-(n-k)),min(draw,k)+1)}

def fisher(a,b,c,d):
    dist=hypergeom(a+b+c+d,a+c,a+b);p0=dist[a]
    return min(1.,sum(p for p in dist.values() if p<=p0*(1+1e-10)))

def compare(a,n1,c,n0):
    if not n1 or not n0:
        return dict(a=a,n1=n1,c=c,n0=n0,rd=None,ci95=[None,None],ci90=[None,None],p=None,rr=None,odds_ratio=None)
    b=n1-a;d=n0-c
    return dict(a=a,n1=n1,c=c,n0=n0,rd=a/n1-c/n0,
                ci95=difference_ci(a,n1,c,n0),ci90=difference_ci(a,n1,c,n0,.90),
                p=fisher(a,b,c,d),rr=(a/n1)/(c/n0) if c else None,
                odds_ratio=a*d/(b*c) if b*c else None)

def holm(ps):
    out=[None]*len(ps);valid=sorted((p,i) for i,p in enumerate(ps) if p is not None);last=0
    for rank,(p,i) in enumerate(valid):
        last=max(last,min(1,p*(len(valid)-rank)));out[i]=last
    return out

def stratified(tables):
    """Exact conditional two-sided test of sum of exposed events; MH point OR.
    Two-sided tail uses absolute distance from its conditional expectation.
    Only strata with both exposure groups contribute to adjusted estimation.
    """
    dist={0:1.};obs=0;mean=0.;num=den=0.;overlap_n=0;informative=0
    for a,b,c,d in tables:
        n=a+b+c+d
        if not (a+b and c+d): continue
        overlap_n+=n
        h=hypergeom(n,a+c,a+b)
        informative+=len(h)>1
        nd={}
        for old,p in dist.items():
            for new,q in h.items(): nd[old+new]=nd.get(old+new,0)+p*q
        dist=nd;obs+=a;mean+=(a+b)*(a+c)/n
        num+=a*d/n;den+=b*c/n
    p=min(1.,sum(p for k,p in dist.items() if abs(k-mean)>=abs(obs-mean)-1e-10)) if informative else None
    return dict(mh_or=num/den if den else None,p=p,overlap_n=overlap_n,informative_strata=informative)
