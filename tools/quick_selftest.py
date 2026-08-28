#!/usr/bin/env python3
"""A ~200-cycle 6502 self-test that names the first thing that is broken.

WHY. The decimal and functional suites take hours, and the wifi panel can only
show the last 32 bus cycles -- so a failure deep inside them is expensive to
reach and hard to read. This runs in well under a second and encodes its verdict
in the ADDRESS it ends up looping at, which is the one thing a 32-cycle window
always shows.

Each subtest jumps to its own distinct self-loop on failure. Success has its own
loop. So the trace address IS the result: no memory read-back needed, which the
panel cannot do anyway.

Usage:  python3 tools/quick_selftest.py [--host IP] [--clock US] [--hex]
"""
import argparse, json, http.client, time

PASS_ADDR = 0x0480
FAIL_BASE = 0x0400          # fail N loops at FAIL_BASE + 3*(N-1)

# opcode helpers
def imm(op, v): return [op, v & 0xFF]
LDAi=lambda v: imm(0xA9,v); LDXi=lambda v: imm(0xA2,v); LDYi=lambda v: imm(0xA0,v)
CMPi=lambda v: imm(0xC9,v); CPXi=lambda v: imm(0xE0,v); CPYi=lambda v: imm(0xC0,v)
ADCi=lambda v: imm(0x69,v); SBCi=lambda v: imm(0xE9,v); ANDi=lambda v: imm(0x29,v)
ORAi=lambda v: imm(0x09,v); EORi=lambda v: imm(0x49,v)
TAX=[0xAA]; TXA=[0x8A]; TAY=[0xA8]; TYA=[0x98]; TXS=[0x9A]; TSX=[0xBA]
INX=[0xE8]; DEX=[0xCA]; INY=[0xC8]; DEY=[0x88]
CLC=[0x18]; SEC=[0x38]; ASLA=[0x0A]; LSRA=[0x4A]; PHA=[0x48]; PLA=[0x68]
PHP=[0x08]; PLP=[0x28]; RTS=[0x60]
def STAzp(a): return [0x85,a]
def LDAzp(a): return [0xA5,a]
def STAax(a): return [0x9D,a&0xFF,a>>8]
def LDAax(a): return [0xBD,a&0xFF,a>>8]
def JMP(a):   return [0x4C,a&0xFF,a>>8]
def JSR(a):   return [0x20,a&0xFF,a>>8]

# "if not equal, fail N"  ->  BEQ +3 ; JMP failN     (branch range never an issue)
def need_eq(n): return [0xF0,0x03] + JMP(FAIL_BASE + 3*(n-1))
def need_ne(n): return [0xD0,0x03] + JMP(FAIL_BASE + 3*(n-1))

TESTS = [
 ("TXS / TSX",        LDXi(0xFF)+TXS+TSX+CPXi(0xFF),                 need_eq),
 ("TAX",              LDAi(0x5A)+TAX+CPXi(0x5A),                     need_eq),
 ("TXA",              LDXi(0x3C)+TXA+CMPi(0x3C),                     need_eq),
 ("TAY / TYA",        LDAi(0xA5)+TAY+LDAi(0x00)+TYA+CMPi(0xA5),      need_eq),
 ("INX",              LDXi(0x00)+INX+INX+CPXi(0x02),                 need_eq),
 ("DEX",              DEX+CPXi(0x01),                                need_eq),
 ("INY / DEY wrap",   LDYi(0x00)+INY+DEY+DEY+CPYi(0xFF),             need_eq),
 ("ADC",              LDAi(0x0F)+CLC+ADCi(0xF0)+CMPi(0xFF),          need_eq),
 ("SBC",              SEC+SBCi(0x0F)+CMPi(0xF0),                     need_eq),
 ("AND",              LDAi(0xCC)+ANDi(0x0F)+CMPi(0x0C),              need_eq),
 ("ORA",              LDAi(0xC0)+ORAi(0x0C)+CMPi(0xCC),              need_eq),
 ("EOR",              LDAi(0xFF)+EORi(0x0F)+CMPi(0xF0),              need_eq),
 ("ASL",              LDAi(0x81)+ASLA+CMPi(0x02),                    need_eq),
 ("LSR",              LDAi(0x81)+LSRA+CMPi(0x40),                    need_eq),
 ("PHA / PLA",        LDAi(0x3C)+PHA+LDAi(0x00)+PLA+CMPi(0x3C),      need_eq),
 ("S decrements x2",  LDXi(0xFF)+TXS+PHA+PHA+TSX+CPXi(0xFD),         need_eq),
 ("S restored by PLA",PLA+PLA+TSX+CPXi(0xFF),                        need_eq),
 ("PHP / PLP",        SEC+PHP+CLC+PLP+LDAi(0x00)+ADCi(0x00)+CMPi(0x01), need_eq),
 ("zero page",        LDAi(0x77)+STAzp(0x10)+LDAi(0x00)+LDAzp(0x10)+CMPi(0x77), need_eq),
 ("abs,X",            LDXi(0x05)+LDAi(0x99)+STAax(0x0500)+LDAi(0x00)+LDAax(0x0500)+CMPi(0x99), need_eq),
 ("Z flag set",       LDAi(0x00)+CMPi(0x00),                         need_eq),
 ("Z flag clear",     LDAi(0xFF)+CMPi(0x00),                         need_ne),
]

def build():
    code=[]
    for i,(name,body,chk) in enumerate(TESTS,1):
        code += body + chk(i)
    code += JSR(0x0490) + CMPi(0x42) + need_eq(len(TESTS)+1)   # JSR/RTS
    code += JMP(PASS_ADDR)
    return code

def ihex(recs):
    """Intel hex, 32 bytes per record -- a record cannot exceed 255 bytes and
    the firmware's line buffer is modest."""
    out=[]
    for addr,data in recs:
        for off in range(0,len(data),32):
            chunk=data[off:off+32]; a=addr+off
            b=bytes([len(chunk),a>>8,a&0xFF,0])+bytes(chunk)
            out.append(":"+b.hex().upper()+"%02X"%((-sum(b))&0xFF))
    out.append(":00000001FF")
    return "\n".join(out)+"\n"

def image():
    code=build()
    assert len(code) <= 0x1F0, "code %d bytes, would run past $03F0"%len(code)
    recs=[(0x0200,code)]
    recs.append((PASS_ADDR, JMP(PASS_ADDR)))
    for i in range(1,len(TESTS)+2):
        a=FAIL_BASE+3*(i-1); recs.append((a, JMP(a)))
    recs.append((0x0490, LDAi(0x42)+RTS))          # the JSR target
    recs.append((0x0600, JMP(0x0600)))             # interrupt trap, clear of code
    recs.append((0x3FFA,[0x00,0x06, 0x00,0x02, 0x00,0x06]))
    return ihex(recs), code

def verdict(addr, ntests):
    if addr==PASS_ADDR: return "*** ALL %d TESTS PASSED ***"%(ntests+1)
    if addr==0x0600:    return "int_trap - BRK or spurious interrupt"
    if FAIL_BASE <= addr < FAIL_BASE+3*(ntests+1):
        n=(addr-FAIL_BASE)//3 + 1
        names=[t[0] for t in TESTS]+["JSR / RTS"]
        return "FAILED test %d: %s"%(n,names[n-1])
    return "unexpected address $%04X"%addr

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--host",default="192.168.68.60")
    ap.add_argument("--clock",type=int,default=50)
    ap.add_argument("--trials",type=int,default=3)
    ap.add_argument("--hex",action="store_true",help="just print the Intel hex")
    a=ap.parse_args()
    img,code=image()
    if a.hex:
        print("; %d tests, %d bytes of code"%(len(TESTS)+1,len(code)))
        print(img); return
    H=a.host
    def get(p,t=12):
        c=http.client.HTTPConnection(H,80,timeout=t)
        c.request("GET",p); d=json.loads(c.getresponse().read()); c.close(); return d
    def post(b):
        c=http.client.HTTPConnection(H,80,timeout=15)
        c.request("POST","/load",body=b.encode(),headers={"Content-Length":str(len(b))})
        d=json.loads(c.getresponse().read()); c.close(); return d
    print("%d subtests, %d bytes of code\n"%(len(TESTS)+1,len(code)))
    # stop is queued to core 1, so poll until it has actually taken effect --
    # /load returns 409 while the CPU is still running.
    for _ in range(20):
        get("/cmd?op=stop"); time.sleep(0.5)
        try:
            if not get("/status")["run"]: break
        except Exception: pass
    else:
        raise SystemExit("CPU would not stop")
    get("/cmd?op=ft&v=0"); time.sleep(0.6)
    r=post(img)
    if not r.get("ok") or r.get("bad"): raise SystemExit("load failed: %r"%r)
    get("/cmd?op=clock&v=%d"%a.clock); time.sleep(0.6)
    for i in range(1,a.trials+1):
        get("/cmd?op=resetrun&v=600"); time.sleep(2.5)
        t=get("/trace?n=32")["t"]
        addrs=[x[1] for x in t]
        loop=max(set(addrs),key=addrs.count)
        print("  trial %d: settled at $%04X   %s"%(i,loop,verdict(loop,len(TESTS))))
        time.sleep(0.6)

if __name__=="__main__":
    main()
