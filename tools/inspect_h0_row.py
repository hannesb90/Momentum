import sys
sys.path.insert(0, 'tools')
import h0_v3_production as p
p.load_engine()
x=p.V2.CTX['W1']['base'][20]
print(x.keys())
print(x['date'])
print(list(x['weights'].items())[:5])
