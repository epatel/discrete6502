import json,os,re,sys
sys.path.insert(0,'tools')
from PIL import Image, ImageDraw
from mark_leds import fit_mapping, load_font
SITES=[("adl7","Q3841",204.55,267.40)]
CAP=(193.0,254.0,217.0,281.0)
RED=(255,70,70); CYAN=(90,210,255); WHITE=(255,255,255); DIM=(150,160,172); BLACK=(0,0,0)
img=Image.open("gen/board_top.png").convert("RGB")
(X0,Y0,sx,sy),_=fit_mapping(img)
px=lambda x,y:(X0+x*sx, Y0+y*sy)
ov=img.copy(); d=ImageDraw.Draw(ov); f=load_font(max(30,int(img.width/70)))
c0=px(CAP[0],CAP[1]); c1=px(CAP[2],CAP[3])
d.rectangle([c0[0],c0[1],c1[0],c1[1]],outline=CYAN,width=8)
d.text((c0[0]-700,c0[1]),"adl7 HELD HIGH",font=f,fill=CYAN)
for net,ref,x,y in SITES:
    ex,ey=px(x,y); r=max(10,int(img.width/200))
    d.ellipse([ex-r,ey-r,ex+r,ey+r],outline=RED,width=5)
pad=40
crop=img.crop((int(c0[0])-pad,int(c0[1])-pad,int(c1[0])+pad,int(c1[1])+pad))
sc=min(3.0,2000/crop.width)
z=crop.resize((int(crop.width*sc),int(crop.height*sc)),Image.LANCZOS)
zd=ImageDraw.Draw(z); zf=load_font(34); zs=load_font(24); zt=load_font(19,bold=False)
zpx=lambda x,y:((px(x,y)[0]-(int(c0[0])-pad))*sc,(px(x,y)[1]-(int(c0[1])-pad))*sc)
src=open("gen/board_routed_golden.kicad_pcb",encoding="utf-8",errors="replace").read()
starts=[m.start() for m in re.finditer(r"\(footprint ",src)]
mine={r for _,r,_,_ in SITES}
for i,st in enumerate(starts):
    seg=src[st:starts[i+1] if i+1<len(starts) else len(src)]
    r=re.search(r'"Reference"\s+"([A-Z]+\d+)"',seg); a=re.search(r"\(at ([-\d.]+) ([-\d.]+)",seg)
    l=re.search(r'\(layer "([^"]+)"',seg)
    if not(r and a and l) or l.group(1)!="F.Cu" or r.group(1) in mine: continue
    x,y=float(a.group(1)),float(a.group(2))
    if not(CAP[0]<=x<=CAP[2] and CAP[1]<=y<=CAP[3]): continue
    zx,zy=zpx(x,y); zd.text((zx+7,zy-9),r.group(1),font=zt,fill=DIM)
for net,ref,x,y in SITES:
    zx,zy=zpx(x,y); r=26
    zd.ellipse([zx-r,zy-r,zx+r,zy+r],outline=RED,width=6)
    p2=zpx(x-0.89,y+0.65); zd.ellipse([p2[0]-7,p2[1]-7,p2[0]+7,p2[1]+7],outline=CYAN,width=3)
    zd.text((zx+r+12,zy-30),"%s  %s"%(net,ref),font=zf,fill=RED)
lg=["adl7 (Q3841) - HELD HIGH","",
    "Measured on the A7 bond pad: 4.15 V average, rail 4.98 V.",
    "The Pico reads ab7 HIGH on 19,000+ of 19,000+ sampled cycles,",
    "never once low. The other 13 address bits all toggle correctly.",
    "",
    "It is NOT frozen - it switches, but its LOW is about 3.3 V,",
    "which is an invalid low and well above the Pico threshold.",
    "Dragging a node only 4.98 -> 3.3 V needs a very low impedance",
    "pull-up: a solder bridge to VCC, not the 10k resistor.",
    "",
    "Reflowing the Pico GP15 joint changed nothing, so the fault is",
    "on the board, not on the link to the Pico.",
    "",
    "LOOK FOR: a bridge from pin 2 (the net) to pin 3 (VCC).",
    "CYAN dot = pin 2. Pin 3 is the lone pin on the opposite side.",
    "",
    "FREE CHECK FIRST: a bridge conducts whenever the pull-down",
    "turns on, so FLIR this part while free-running. Warm against its",
    "neighbours locates it with no magnifier, and total current",
    "should drop once it is cleared.",
    "",
    "The other 15 rework sites behave. ab2 was a separate fault,",
    "fixed by reflowing the Pico GP10 joint."]
lh=zs.size+9; bh=lh*len(lg)+26
# size the panel to the text, not the crop -- the zoom here is narrow and the
# legend was being clipped at the right edge.
probe=ImageDraw.Draw(Image.new("RGB",(8,8)))
need=max(probe.textlength(l, font=zf if i==0 else zs) for i,l in enumerate(lg))+56
pw=int(max(z.width, need))
panel=Image.new("RGB",(pw,z.height+bh),BLACK)
panel.paste(z,((pw-z.width)//2,0))
pd=ImageDraw.Draw(panel)
for i,line in enumerate(lg):
    col=WHITE if i==0 else (CYAN if line.startswith("CYAN") else DIM)
    pd.text((24,z.height+14+i*lh),line,font=zf if i==0 else zs,fill=col)
ow=panel.width
ov2=ov.resize((ow,int(ov.height*ow/ov.width)),Image.LANCZOS)
final=Image.new("RGB",(ow,ov2.height+panel.height+16),BLACK)
final.paste(ov2,(0,0)); final.paste(panel,(0,ov2.height+16))
final.save("docs/adl7-stuck-marked.jpg",quality=88)
print("wrote docs/adl7-stuck-marked.jpg (%dx%d)"%final.size)
