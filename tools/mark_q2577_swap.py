import os,re,sys
sys.path.insert(0,'tools')
from PIL import Image, ImageDraw
from mark_leds import fit_mapping, load_font
GRN=(80,230,140); RED=(255,70,70); YEL=(255,215,60); WHITE=(255,255,255); DIM=(150,160,172); BLACK=(0,0,0)

# (ref, x, y, colour, title, subtitle)
TAKE=("Q4050",200.85,119.00,GRN,"TAKE THIS ONE","P2 flag LED driver - spare part")
PUT =("Q2577", 75.05,183.40,RED,"PUT IT HERE","the faulty part - replace it")
ALT =[("Q4049",245.25,163.80,"alt: P1 LED"),("Q4023",63.95,273.00,"alt: Y7 LED")]

img=Image.open("gen/board_top.png").convert("RGB")
(X0,Y0,sx,sy),_=fit_mapping(img)
px=lambda x,y:(X0+x*sx, Y0+y*sy)
ov=img.copy(); d=ImageDraw.Draw(ov)
f=load_font(max(40,int(img.width/52))); fs=load_font(max(30,int(img.width/72)))
R=max(34,int(img.width/62))
for ref,x,y,col,title,sub in (TAKE,PUT):
    ex,ey=px(x,y)
    d.ellipse([ex-R,ey-R,ex+R,ey+R],outline=col,width=11)
    d.ellipse([ex-R*2.0,ey-R*2.0,ex+R*2.0,ey+R*2.0],outline=col,width=4)
    tx = ex+R*2.4 if x < 150 else ex-R*2.4
    anch = "la" if x < 150 else "ra"
    d.text((tx,ey-R*2.4-f.size-8),title,font=f,fill=col,anchor=anch)
    d.text((tx,ey-R*2.4+4),"%s   %s"%(ref,sub),font=fs,fill=WHITE,anchor=anch)
for ref,x,y,lab in ALT:
    ex,ey=px(x,y)
    d.ellipse([ex-R*0.7,ey-R*0.7,ex+R*0.7,ey+R*0.7],outline=YEL,width=6)
    d.text((ex+R,ey-14),"%s  %s"%(ref,lab),font=fs,fill=YEL)
# arrow from take -> put
ax,ay=px(TAKE[1],TAKE[2]); bx,by=px(PUT[1],PUT[2])
d.line([ax,ay,bx,by],fill=(255,255,255),width=5)
mx,my=(ax+bx)/2,(ay+by)/2
d.text((mx,my-46),"transplant",font=f,fill=WHITE,anchor="ma")

lg=["ONE TRANSISTOR TO MOVE","",
    "GREEN  Q4050  x 200.85  y 119.00   -- TAKE this one",
    "       It only drives the P2 flag LED. Cosmetic; the CPU",
    "       does not use it. Nearest neighbour 2.80 mm.",
    "RED    Q2577  x  75.05  y 183.40   -- PUT it here",
    "       Gate-drain leak, 20k against a healthy 177k. It ties",
    "       s0 to n983, which R585 holds at VCC through 10k, so",
    "       S bit 0 can never fall and PHA cannot decrement S.",
    "YELLOW alternatives if Q4050 is awkward to reach.",
    "       Avoid Q4025/Q4029/Q4031 - those are S-register bits.",
    "",
    "Same part both ends: BSS138K, SOT-323, rotation 0, and the",
    "pin roles match exactly (1 gate, 2 source, 3 drain).",
    "",
    "REMOVING IT INTACT - the last one shed a pin:",
    "  hot air is far safer than an iron. Flux it, 300-330 C,",
    "  keep the nozzle moving, lift only when all three joints",
    "  are molten. Iron only: add FRESH solder to all three pins",
    "  first, flux well, alternate quickly, lift a fraction at a",
    "  time. Never lever against one pin.",
    "",
    "CHECK BEFORE FITTING: gate to drain must read OL out of",
    "circuit. Then Q2577 in place should read like its twin",
    "Q3793 - about 177k, not 20k."]
lh=fs.size+11; bh=lh*len(lg)+34
prb=ImageDraw.Draw(Image.new("RGB",(8,8)))
need=int(max(prb.textlength(l,font=f if i==0 else fs) for i,l in enumerate(lg))+64)
W=max(ov.width,need)
ov2=ov if ov.width==W else ov.resize((W,int(ov.height*W/ov.width)),Image.LANCZOS)
final=Image.new("RGB",(W,ov2.height+bh),BLACK); final.paste(ov2,(0,0))
fd=ImageDraw.Draw(final)
for i,line in enumerate(lg):
    col=WHITE if i==0 else (GRN if line.startswith("GREEN") else RED if line.startswith("RED")
         else YEL if line.startswith("YELLOW") else DIM)
    fd.text((30,ov2.height+18+i*lh),line,font=f if i==0 else fs,fill=col)
final.save("docs/q2577-transplant.jpg",quality=88)
print("wrote docs/q2577-transplant.jpg (%dx%d)"%final.size)
