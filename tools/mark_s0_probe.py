import os,re,sys
sys.path.insert(0,'tools')
from PIL import Image, ImageDraw
from mark_leds import fit_mapping, load_font
RED=(255,70,70); GRN=(80,230,140); CYAN=(90,210,255); YEL=(255,215,60)
WHITE=(255,255,255); DIM=(150,160,172); BLACK=(0,0,0)

# ref, part x, part y, which pins to circle, colour, label
SITES=[
 ("Q269", 78.75,191.80,[1,3], RED,  "-> dpc7_SS   pin3 = s0 PROBE"),
 ("Q362", 78.75,203.00,[1,3], GRN,  "control      pin3 = s1 PROBE"),
 ("Q1099",71.35,183.40,[1,3], RED,  "-> dpc6_SBS"),
 ("Q311", 75.05,200.20,[1,3], GRN,  "control"),
 ("Q2577",75.05,183.40,[1,3], RED,  "-> n983"),
 ("Q3793",78.75,180.60,[1,3], GRN,  "control"),
]
CAP=(68.0,177.0,84.0,207.0)
PINOFF={1:(-0.89,-0.65),2:(-0.89,0.65),3:(0.89,0.0)}

img=Image.open("gen/board_top.png").convert("RGB")
(X0,Y0,sx,sy),_=fit_mapping(img)
px=lambda x,y:(X0+x*sx, Y0+y*sy)
c0=px(CAP[0],CAP[1]); c1=px(CAP[2],CAP[3])
ov=img.copy(); d=ImageDraw.Draw(ov); f=load_font(max(30,int(img.width/70)))
d.rectangle([c0[0],c0[1],c1[0],c1[1]],outline=YEL,width=8)
d.text((c1[0]+22,c0[1]),"S REGISTER\nbit 0 vs bit 1",font=f,fill=YEL)

pad=28
crop=img.crop((int(c0[0])-pad,int(c0[1])-pad,int(c1[0])+pad,int(c1[1])+pad))
sc=min(4.5,1800/crop.width)
z=crop.resize((int(crop.width*sc),int(crop.height*sc)),Image.LANCZOS)
zd=ImageDraw.Draw(z); zf=load_font(29); zs=load_font(23); zt=load_font(17,bold=False)
zpx=lambda x,y:((px(x,y)[0]-(int(c0[0])-pad))*sc,(px(x,y)[1]-(int(c0[1])-pad))*sc)

src=open("gen/board_routed_golden.kicad_pcb",encoding="utf-8",errors="replace").read()
starts=[m.start() for m in re.finditer(r"\(footprint ",src)]
mine={s[0] for s in SITES}
for i,st in enumerate(starts):
    seg=src[st:starts[i+1] if i+1<len(starts) else len(src)]
    r=re.search(r'"Reference"\s+"([A-Z]+\d+)"',seg); a=re.search(r"\(at ([-\d.]+) ([-\d.]+)",seg)
    l=re.search(r'\(layer "([^"]+)"',seg)
    if not(r and a and l) or l.group(1)!="F.Cu" or r.group(1) in mine: continue
    x,y=float(a.group(1)),float(a.group(2))
    if not(CAP[0]<=x<=CAP[2] and CAP[1]<=y<=CAP[3]): continue
    zx,zy=zpx(x,y); zd.text((zx+6,zy-8),r.group(1),font=zt,fill=DIM)

for ref,x,y,pins,col,label in SITES:
    pts={p:zpx(x+PINOFF[p][0], y+PINOFF[p][1]) for p in pins}
    if 1 in pts and 3 in pts:
        zd.line([pts[1][0],pts[1][1],pts[3][0],pts[3][1]],fill=col,width=5)
    for p,(qx,qy) in pts.items():
        zd.ellipse([qx-13,qy-13,qx+13,qy+13],outline=col,width=6)
        zd.text((qx-7,qy-44 if p==1 else qy+16),str(p),font=zs,fill=WHITE)
    if x < 73.0:                      # left-hand parts label to the LEFT
        ax,ay=pts[min(pts)]
        w=max(zd.textlength(ref,font=zf), zd.textlength(label,font=zs))
        zd.text((ax-30-w,ay-30),ref,font=zf,fill=col)
        zd.text((ax-30-w,ay+2),label,font=zs,fill=col)
    else:
        ax,ay=pts[max(pts)]
        zd.text((ax+26,ay-30),ref,font=zf,fill=col)
        zd.text((ax+26,ay+2),label,font=zs,fill=col)

lg=["S BIT 0 IS STUCK HIGH - WHAT TO MEASURE (board OFF)","",
    "STEP 1 - is s0 tied to a rail?  Compare these two:",
    "CYAN/RED  Q269 pin 3  = the s0 net",
    "GREEN     Q362 pin 3  = the s1 net (healthy control)",
    "   measure each to TP36 (VCC) and to TP35 (VSS), same range.",
    "   s0 much lower than s1 to VCC  =>  s0 is tied to the rail.",
    "   both alike  =>  no rail short, go to step 2.","",
    "STEP 2 - pin 1 to pin 3 on each RED part, compared with its",
    "GREEN twin. A gate-to-drain leak there holds s0 high:",
    "   Q1099 vs Q311    would tie s0 to dpc6_SBS",
    "   Q269  vs Q362    would tie s0 to dpc7_SS",
    "   Q2577 vs Q3793   would tie s0 to n983",
    "Both control lines go high in normal operation, so either",
    "leak would hold s0 up exactly as observed.","",
    "RED = on s0 (suspect).  GREEN = the matching part on s1.",
    "Compare the pair - absolute values mean nothing on this board.","",
    "Already excluded: Q4024 (removed, no change), sb0 and the ALU",
    "(DEX decrements correctly), and the address bus (all 14 bits)."]
lh=zs.size+9; bh=lh*len(lg)+30
prb=ImageDraw.Draw(Image.new("RGB",(8,8)))
need=int(max(prb.textlength(l,font=zf if i==0 else zs) for i,l in enumerate(lg))+56)
W=max(z.width,need)
panel=Image.new("RGB",(W,z.height+bh),BLACK); panel.paste(z,((W-z.width)//2,0))
pd=ImageDraw.Draw(panel)
for i,line in enumerate(lg):
    col=WHITE if i==0 else (CYAN if line.startswith("CYAN") else GRN if line.startswith("GREEN")
         else YEL if line.startswith("STEP") else DIM)
    pd.text((26,z.height+16+i*lh),line,font=zf if i==0 else zs,fill=col)
ov2=ov.resize((W,int(ov.height*W/ov.width)),Image.LANCZOS)
final=Image.new("RGB",(W,ov2.height+panel.height+14),BLACK)
final.paste(ov2,(0,0)); final.paste(panel,(0,ov2.height+14))
final.save("docs/s0-stuck-probe-map.jpg",quality=88)
print("wrote docs/s0-stuck-probe-map.jpg (%dx%d)"%final.size)
