#!/usr/bin/env python3
"""The sixteen un-reworked precharge sites: idb0-7 and sb0-7.

WHY. `cclk` gates 32 VCC-side precharge FETs. Sixteen of them (adh0-7, adl0-7)
already carry the 10k series rework; these sixteen do not, so every time the
clock goes high they contend at full strength -- amps in 40 us bursts, which is
what collapses the supply before the self-test can finish. See
docs/clk0-pulldown.md section 5.

HAZARD, and it is the same one that smoked board #1: on every one of these
parts pin 1 is `cclk` itself, 1.89 mm from the pin 3 being lifted. A bridge
between them shorts the CPU's clock to VCC and stops the whole machine.

Usage: python3 tools/mark_precharge_rework.py
"""
import os, re, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw
from mark_leds import fit_mapping, load_font

RED=(255,70,70); YEL=(255,215,60); CYAN=(90,210,255); WHITE=(255,255,255)
DIM=(150,160,172); BLACK=(0,0,0)
PIN={1:(-0.89,-0.65),2:(-0.89,0.65),3:(0.89,0.0)}

NETLIST="gen/netlist.json"; PCB="gen/board_routed_golden.kicad_pcb"

def load():
    C=json.load(open(NETLIST))["components"]
    want={"idb%d"%i for i in range(8)} | {"sb%d"%i for i in range(8)}
    sites={}
    for c in C:
        if c.get("role")!="vcc_side": continue
        net=c["pins"]["3"] if c["pins"]["2"]=="vcc" else c["pins"]["2"]
        if net in want:
            assert c["pins"]["1"]=="cclk", "%s gate is %s"%(c["ref"],c["pins"]["1"])
            sites[c["ref"]]=net
    assert len(sites)==16, len(sites)
    src=open(PCB,encoding="utf-8",errors="replace").read()
    st=[m.start() for m in re.finditer(r"\(footprint ",src)]
    pos={}
    for i,s0 in enumerate(st):
        seg=src[s0:st[i+1] if i+1<len(st) else len(src)]
        r=re.search(r'"Reference"\s+"([A-Z]+\d+)"',seg)
        a=re.search(r"\(at ([-\d.]+) ([-\d.]+)",seg)
        l=re.search(r'\(layer "([^"]+)"',seg)
        if r and a and l: pos[r.group(1)]=(float(a.group(1)),float(a.group(2)),l.group(1))
    return sites,pos,src,st

def panel(img,px,cap,sites,pos,src,st,title,scale_to=900):
    c0=px(cap[0],cap[1]); c1=px(cap[2],cap[3]); pad=26
    crop=img.crop((int(c0[0])-pad,int(c0[1])-pad,int(c1[0])+pad,int(c1[1])+pad))
    sc=min(5.0, scale_to/crop.width)
    z=crop.resize((int(crop.width*sc),int(crop.height*sc)),Image.LANCZOS)
    zd=ImageDraw.Draw(z); zf=load_font(26); zt=load_font(15,bold=False); zh=load_font(30)
    zpx=lambda x,y:((px(x,y)[0]-(int(c0[0])-pad))*sc,(px(x,y)[1]-(int(c0[1])-pad))*sc)
    mine=set(sites)
    for i,s0 in enumerate(st):
        seg=src[s0:st[i+1] if i+1<len(st) else len(src)]
        r=re.search(r'"Reference"\s+"([A-Z]+\d+)"',seg)
        a=re.search(r"\(at ([-\d.]+) ([-\d.]+)",seg)
        l=re.search(r'\(layer "([^"]+)"',seg)
        if not(r and a and l) or l.group(1)!="F.Cu" or r.group(1) in mine: continue
        x,y=float(a.group(1)),float(a.group(2))
        if not(cap[0]<=x<=cap[2] and cap[1]<=y<=cap[3]): continue
        qx,qy=zpx(x,y); zd.text((qx+5,qy-7),r.group(1),font=zt,fill=DIM)
    for ref,net in sorted(sites.items(), key=lambda kv: kv[1]):
        x,y,_=pos[ref]
        if not(cap[0]<=x<=cap[2] and cap[1]<=y<=cap[3]): continue
        p1=zpx(x+PIN[1][0],y+PIN[1][1]); p3=zpx(x+PIN[3][0],y+PIN[3][1])
        zd.line([p1[0],p1[1],p3[0],p3[1]],fill=(255,150,150),width=4)
        zd.ellipse([p1[0]-11,p1[1]-11,p1[0]+11,p1[1]+11],outline=YEL,width=5)
        zd.ellipse([p3[0]-11,p3[1]-11,p3[0]+11,p3[1]+11],outline=RED,width=5)
        lab="%s %s"%(net,ref)
        # label on whichever side has room -- parts near the crop's right edge
        # would otherwise run their text off the panel
        if x > cap[2]-7.0:
            w=zd.textlength(lab,font=zf)
            zd.text((p1[0]-18-w,p1[1]-14),lab,font=zf,fill=WHITE)
        else:
            zd.text((p3[0]+18,p3[1]-14),lab,font=zf,fill=WHITE)
    hdr=Image.new("RGB",(z.width,z.height+44),BLACK); hdr.paste(z,(0,44))
    ImageDraw.Draw(hdr).text((8,6),title,font=zh,fill=CYAN)
    return hdr

def main():
    sites,pos,src,st=load()
    img=Image.open("gen/board_top.png").convert("RGB")
    (X0,Y0,sx,sy),_=fit_mapping(img)
    px=lambda x,y:(X0+x*sx, Y0+y*sy)
    SB=(38.0,187.0,80.0,284.0); IDB=(204.0,187.0,220.0,284.0)
    ov=img.copy(); d=ImageDraw.Draw(ov); f=load_font(max(30,int(img.width/70)))
    for cap,lab in ((SB,"sb0-7"),(IDB,"idb0-7")):
        a=px(cap[0],cap[1]); b=px(cap[2],cap[3])
        d.rectangle([a[0],a[1],b[0],b[1]],outline=CYAN,width=8)
        d.text((a[0],a[1]-f.size-10),lab,font=f,fill=CYAN)
    pa=panel(img,px,SB,sites,pos,src,st,"sb0-7   (left edge)")
    pb=panel(img,px,IDB,sites,pos,src,st,"idb0-7  (right, one column)")
    gap=20; zw=pa.width+gap+pb.width; zh=max(pa.height,pb.height)
    zoom=Image.new("RGB",(zw,zh),BLACK); zoom.paste(pa,(0,0)); zoom.paste(pb,(pa.width+gap,0))
    lg=["THE OTHER SIXTEEN PRECHARGE SITES - idb0-7 and sb0-7","",
        "cclk gates 32 precharge FETs. adh0-7 and adl0-7 already have the",
        "10k series rework; these sixteen do not, so they contend at full",
        "strength every time the clock goes high - amps in 40 us bursts.",
        "That is what collapses the supply before the self-test finishes.","",
        "RED    pin 3 - the VCC pin to lift, 10k in series (C25744, in BOM)",
        "YELLOW pin 1 - cclk. DO NOT BRIDGE TO IT.","",
        "*** THE HAZARD THAT SMOKED BOARD #1 ***",
        "On every one of these, pin 1 is cclk itself, only 1.89 mm from the",
        "pin 3 you are lifting. A bridge there shorts the CPU's clock to VCC:",
        "the machine stops, the site burns, and it reads 32 ohm to VCC where",
        "a healthy cclk reads kilohms. Check cclk-to-VCC after each site.","",
        "Lie the resistor FLAT and anchor both ends - one standing on a lifted",
        "pin came adrift during a wash on board #1.","",
        "All sixteen are top face, nearest neighbour 2.80 mm.",
        "Positions from gen/board_routed_golden.kicad_pcb, nets from",
        "gen/netlist.json. Regenerate: tools/mark_precharge_rework.py"]
    fs=load_font(23); ft=load_font(30)
    lh=fs.size+10; bh=lh*len(lg)+30
    probe=ImageDraw.Draw(Image.new("RGB",(8,8)))
    need=int(max(probe.textlength(l,font=ft if i==0 else fs) for i,l in enumerate(lg))+60)
    W=max(zoom.width,need,900)
    panel_img=Image.new("RGB",(W,zoom.height+bh),BLACK)
    panel_img.paste(zoom,((W-zoom.width)//2,0))
    pd=ImageDraw.Draw(panel_img)
    for i,line in enumerate(lg):
        col=WHITE if i==0 else (RED if line.startswith(("RED","***")) else
             YEL if line.startswith("YELLOW") else DIM)
        pd.text((26,zoom.height+16+i*lh),line,font=ft if i==0 else fs,fill=col)
    ov2=ov.resize((W,int(ov.height*W/ov.width)),Image.LANCZOS)
    out=Image.new("RGB",(W,ov2.height+panel_img.height+14),BLACK)
    out.paste(ov2,(0,0)); out.paste(panel_img,(0,ov2.height+14))
    out.save("docs/precharge-rework-idb-sb.jpg",quality=88)
    print("wrote docs/precharge-rework-idb-sb.jpg (%dx%d)"%out.size)
    for ref,net in sorted(sites.items(), key=lambda kv: kv[1]):
        x,y,_=pos[ref]
        print("  %-5s %-7s x=%7.2f y=%7.2f   pin3 x=%7.2f y=%7.2f"%(net,ref,x,y,x+0.89,y))

if __name__=="__main__": main()
