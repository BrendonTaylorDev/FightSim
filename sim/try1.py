import sys, json
sys.path.insert(0, __import__("os").path.dirname(__file__))
from harness import *
s = session(7, settings=["/scale 5", "/resscale 0.75", "/healthloss 0.2", "/numb off"])
log=[]
out, caps = beat(s, [{"action":"strike","attacker":"Ripples","defender":"Nocturne","move":"Aqua Jet","part":"Chest",
                      "charge_into":"a fallen boulder","flavor":"Aqua Jet straight into the Absol's chest"}], log)
print(out[-4000:])
print(len(caps))
allp = "\n=====\n".join(m["content"] for msgs in caps for m in msgs if m["role"]=="user")
i = allp.find("CONTACT NEVER")
print(allp[i-1500:i+2500])
