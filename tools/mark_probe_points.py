import os,re,sys,math
sys.path.insert(0,'tools')
from PIL import Image, ImageDraw
from mark_leds import fit_mapping, load_font

# probe pads: (label, ref, part x, part y, pin) -- pin1 pad = (-0.89,-0.65)
PROBES=[("cclk","Q3659",237.85,133.00),("cclk","Q1038",126.85,135.80),
        ("cp1","Q690",126.85,113.40),("cp1","Q2502",34.35,175.00)]
PADS=[("VCC  TP36",None),("VSS  TP35",None)]
RED=(255,70,70); CYAN=(90,210,255); YEL=(255,215,60); WHITE=(255,255,255); BLACK=(0,0,0); DIM=(150,160,172)

img=Image.open("gen/board_top.png").convert("RGB")
(X0,Y0,sx,sy),_=fit_mapping(img)
px=lambda x,y:(X0+x*sx, Y0+y*sy)

# locate the VCC/VSS bond pads from the board file
src=open("gen/board_routed_golden.kicad_pcb",encoding="utf-8",errors="replace").read()
starts=[m.start() for m in re.finditer(r"\(footprint ",src)]
tp={}
for i,st in enumerate(starts):
    seg=src[st:starts[i+1] if i+1<len(starts) else len(src)]
    r=re.search(r'"Reference"\s+"(TP\d+)"',seg); a=re.search(r"\(at ([-\d.]+) ([-\d.]+)",seg)
    if r and a: tp[r.group(1)]=(float(a.group(1)),float(a.group(2)))

ov=img.copy(); d=ImageDraw.Draw(ov)
f=load_font(max(34,int(img.width/62))); fs=load_font(max(26,int(img.width/85)))
R=max(26,int(img.width/78))
for net,ref,x,y in PROBES:
    pxp,pyp=px(x-0.89,y-0.65)                    # pin 1 pad
    col = RED if net=="cclk" else CYAN
    d.ellipse([pxp-R,pyp-R,pxp+R,pyp+R],outline=col,width=9)
    # label on whichever side has room, so nothing runs off the edge
    if x < 110:
        d.line([pxp+R*0.7,pyp+R*2.4,pxp+R*2.4,pyp+R*0.7],fill=col,width=6)
        d.text((pxp+R*2.6,pyp+R*1.6),"%s\n%s pin1"%(net,ref),font=f,fill=col)
    else:
        d.line([pxp-R*2.4,pyp-R*2.4,pxp-R*0.7,pyp-R*0.7],fill=col,width=6)
        d.text((pxp-R*2.4-330,pyp-R*2.4-46),"%s\n%s pin1"%(net,ref),font=f,fill=col)
for name,ref in (("VCC",'TP36'),("VSS",'TP35')):
    if ref not in tp: continue
    x,y=tp[ref]; ex,ey=px(x,y)
    d.ellipse([ex-R*1.6,ey-R*1.6,ex+R*1.6,ey+R*1.6],outline=YEL,width=9)
    d.text((ex-R*1.2,ey-R*1.6-f.size-16),"%s (%s)"%(name,ref),font=f,fill=YEL)

lg=["WHERE TO PROBE cclk AND cp1   (board POWERED OFF)","",
    "RED    cclk  - Q3659 pin 1  and  Q1038 pin 1",
    "CYAN   cp1   - Q690  pin 1  and  Q2502 pin 1",
    "YELLOW VCC = TP36 bond pad,  VSS = TP35 bond pad","",
    "Pin 1 is the UPPER of the two pins on the two-pin side.",
    "Each circled part has no neighbour within 4.6 mm, so there",
    "is room for a probe tip. Do NOT probe the vias - they are",
    "epoxy filled and covered with soldermask, no bare copper.","",
    "MEASURE: pad -> TP36, and pad -> TP35.",
    "  under ~1 ohm, or same on every range  = SHORTED, that is",
    "     the damage",
    "  hundreds of ohms to kohm, CHANGING with range = normal","",
    "CONTROLS: the two cclk points are the same net at opposite",
    "ends of the board - they must agree. cclk and cp1 should",
    "also read in the same ballpark as each other.","",
    "All four are far from Q3841 on purpose: a short there is",
    "still visible here, without probing the burnt area."]
lh=fs.size+11; bh=lh*len(lg)+34
probe=ImageDraw.Draw(Image.new("RGB",(8,8)))
need=int(max(probe.textlength(l,font=f if i==0 else fs) for i,l in enumerate(lg))+64)
W=max(ov.width,need)
ov2=ov if ov.width==W else ov.resize((W,int(ov.height*W/ov.width)),Image.LANCZOS)
final=Image.new("RGB",(W,ov2.height+bh),BLACK)
final.paste(ov2,(0,0))
fd=ImageDraw.Draw(final)
for i,line in enumerate(lg):
    col=WHITE if i==0 else (RED if line.startswith("RED") else CYAN if line.startswith("CYAN")
         else YEL if line.startswith("YELLOW") else DIM)
    fd.text((28,ov2.height+18+i*lh),line,font=f if i==0 else fs,fill=col)
final.save("docs/probe-cclk-cp1.jpg",quality=88)
print("wrote docs/probe-cclk-cp1.jpg (%dx%d)"%final.size)
for net,ref,x,y in PROBES:
    print("  %-5s %-7s pin1 pad at x=%.2f y=%.2f"%(net,ref,x-0.89,y-0.65))
for name,ref in (("VCC",'TP36'),("VSS",'TP35')):
    if ref in tp: print("  %-5s %-7s at x=%.2f y=%.2f"%(name,ref,tp[ref][0],tp[ref][1]))
