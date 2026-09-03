"""Audited SMC signal components merged from the uploaded XAU/USD bot."""
from __future__ import annotations
from typing import Any
MIN_FVG_SIZE=1.50
EQUAL_LEVEL_TOL=0.30
MIN_CONFIDENCE=65

def find_swing_highs(candles:list[dict[str,Any]],lookback:int=3):
    return [(i,float(candles[i]["high"])) for i in range(lookback,len(candles)-lookback) if all(candles[i]["high"]>=candles[i-j]["high"] and candles[i]["high"]>=candles[i+j]["high"] for j in range(1,lookback+1))]

def find_swing_lows(candles:list[dict[str,Any]],lookback:int=3):
    return [(i,float(candles[i]["low"])) for i in range(lookback,len(candles)-lookback) if all(candles[i]["low"]<=candles[i-j]["low"] and candles[i]["low"]<=candles[i+j]["low"] for j in range(1,lookback+1))]

def _ema(values:list[float],period:int)->float:
    if not values:return 0.0
    a=2/(period+1); result=values[0]
    for v in values[1:]: result=a*v+(1-a)*result
    return result

def analyze_structure_bos(candles:list[dict[str,Any]]):
    if len(candles)<20:return "NEUTRAL",None,False
    sample=candles[-60:]; sh=find_swing_highs(sample); sl=find_swing_lows(sample)
    if len(sh)<2 or len(sl)<2:return "NEUTRAL",None,False
    curr=float(candles[-1]["close"]); last_sh,prev_sh=sh[-1][1],sh[-2][1]; last_sl,prev_sl=sl[-1][1],sl[-2][1]
    closes=[float(c["close"]) for c in candles]; bias="BULLISH" if _ema(closes[-30:],10)>_ema(closes[-60:],30) else "BEARISH"
    bull=curr>last_sh; bear=curr<last_sl; was_bear=last_sh<prev_sh and last_sl<prev_sl; was_bull=last_sh>prev_sh and last_sl>prev_sl
    if was_bear and bull:return "BULLISH","CHoCH",True
    if was_bull and bear:return "BEARISH","CHoCH",True
    if bull and bias=="BULLISH" and last_sh>prev_sh:return "BULLISH","BOS",False
    if bear and bias=="BEARISH" and last_sl<prev_sl:return "BEARISH","BOS",False
    if bias=="BULLISH" and last_sh>prev_sh and last_sl>prev_sl:return "BULLISH",None,False
    if bias=="BEARISH" and last_sh<prev_sh and last_sl<prev_sl:return "BEARISH",None,False
    return "NEUTRAL",None,False

def detect_order_block(candles,bias):
    if len(candles)<10:return None,None,False
    price=float(candles[-1]["close"]); start=max(len(candles)-20,3)
    for i in range(len(candles)-3,start-1,-1):
        c=candles[i]
        if (bias=="BULLISH" and c["close"]<c["open"]) or (bias=="BEARISH" and c["close"]>c["open"]):
            nxt=[candles[i+j]["close"] for j in (1,2)]
            if (bias=="BULLISH" and max(nxt)>c["high"]) or (bias=="BEARISH" and min(nxt)<c["low"]):
                hi,lo=float(c["high"]),float(c["low"]); return hi,lo,lo<=price<=hi
    return None,None,False

def detect_liquidity_zones(candles):
    if len(candles)<10:return False,False,False,False
    recent=candles[-30:]; hs=[float(c["high"]) for c in recent[:-1]]; ls=[float(c["low"]) for c in recent[:-1]]; lh=float(candles[-1]["high"]); ll=float(candles[-1]["low"])
    hlev=[h for i,h in enumerate(hs) if any(abs(h-o)<=EQUAL_LEVEL_TOL for o in hs[i+1:])]; llev=[l for i,l in enumerate(ls) if any(abs(l-o)<=EQUAL_LEVEL_TOL for o in ls[i+1:])]
    return bool(hlev),bool(llev),bool(hlev and any(lh>h for h in hlev)),bool(llev and any(ll<l for l in llev))

def detect_fvg(candles):
    if len(candles)<3:return None,0
    last=len(candles)-1
    for i in range(max(0,len(candles)-12),len(candles)-2):
        c1,c2,c3=candles[i:i+3]
        if c1["high"]<c3["low"] and float(c3["low"]-c1["high"])>=MIN_FVG_SIZE:
            lo,hi=float(c1["high"]),float(c3["low"])
            if not any(float(c["low"])<=hi and float(c["high"])>=lo for c in candles[i+3:last+1]):return "BULLISH_FVG",1
        if c1["low"]>c3["high"] and float(c1["low"]-c3["high"])>=MIN_FVG_SIZE:
            lo,hi=float(c3["high"]),float(c1["low"])
            if not any(float(c["high"])>=lo and float(c["low"])<=hi for c in candles[i+3:last+1]):return "BEARISH_FVG",1
    return None,0

def detect_liquidity_grab(candles):
    if len(candles)<10:return None,0
    r=candles[-10:]; prev,curr=r[-2:]; mh=max(float(c["high"]) for c in r[:-2]); ml=min(float(c["low"]) for c in r[:-2])
    if float(prev["high"])>mh and float(prev["high"])-max(float(prev["open"]),float(prev["close"]))>=1 and curr["close"]<curr["open"]:return "BEARISH_GRAB",2
    if float(prev["low"])<ml and min(float(prev["open"]),float(prev["close"]))-float(prev["low"])>=1 and curr["close"]>curr["open"]:return "BULLISH_GRAB",2
    return None,0

def check_candle_pattern(candles):
    if len(candles)<2:return None,0
    a,b=candles[-2:]
    if a["open"]<a["close"] and b["open"]>b["close"] and b["open"]>=a["close"] and b["close"]<=a["open"]:return "BEARISH_ENGULF",2
    if a["open"]>a["close"] and b["open"]<b["close"] and b["open"]<=a["close"] and b["close"]>=a["open"]:return "BULLISH_ENGULF",2
    body=abs(float(b["open"])-float(b["close"]))
    if body and float(b["high"])-max(float(b["open"]),float(b["close"]))>2*body:return "SHOOTING_STAR",1
    if body and min(float(b["open"]),float(b["close"]))-float(b["low"])>2*body:return "HAMMER",1
    return None,0

def calculate_rsi(candles,period=14):
    if len(candles)<period+1:return 50.0
    closes=[float(c["close"]) for c in candles[-period-1:]]; gains=[]; losses=[]
    for a,b in zip(closes,closes[1:]):
        d=b-a; gains.append(max(d,0)); losses.append(max(-d,0))
    ag=sum(gains)/period; al=sum(losses)/period
    return 100.0 if al==0 else round(100-100/(1+ag/al),2)

def generate_signal(candles_5m,candles_15m,min_confidence=MIN_CONFIDENCE):
    if not candles_5m or not candles_15m:return None
    price=float(candles_5m[-1]["close"]); tf,bos,choch=analyze_structure_bos(candles_15m)
    if tf=="NEUTRAL":
        return {"direction":"HOLD","confidence":0,"entry_low":0.0,"entry_high":0.0,"tp1":0.0,"tp2":0.0,"tp3":0.0,"sl":0.0,"reasons":["15M structure is neutral","WAIT FOR 15M BIAS CONFIRMATION"],"rsi":calculate_rsi(candles_5m),"tf_bias":"NEUTRAL","bos_type":"None","choch":False}
    m5,m5bos,_=analyze_structure_bos(candles_5m); oh,ol,inob=detect_order_block(candles_5m,tf); eh,el,sh,sl=detect_liquidity_zones(candles_5m); grab,gs=detect_liquidity_grab(candles_5m); fvg,fs=detect_fvg(candles_5m); pat,ps=check_candle_pattern(candles_5m); rsi=calculate_rsi(candles_5m)
    long=30 if tf=="BULLISH" else 0; short=30 if tf=="BEARISH" else 0; lr=[]; sr=[]
    (lr if tf=="BULLISH" else sr).append(f"15M {tf.title()} ({bos or 'trend'}{' + CHoCH' if choch else ''})")
    if tf=="BULLISH" and choch:long+=10;lr.append("15M CHoCH Reversal")
    if tf=="BEARISH" and choch:short+=10;sr.append("15M CHoCH Reversal")
    if m5=="BULLISH":long+=15;lr.append(f"M5 Bullish{' BOS' if m5bos else ''}")
    if m5=="BEARISH":short+=15;sr.append(f"M5 Bearish{' BOS' if m5bos else ''}")
    if inob and tf=="BULLISH":long+=20;lr.append("Price in Bullish Order Block")
    if inob and tf=="BEARISH":short+=20;sr.append("Price in Bearish Order Block")
    if sl and tf=="BULLISH":long+=15;lr.append("Equal Lows Swept")
    if sh and tf=="BEARISH":short+=15;sr.append("Equal Highs Swept")
    if grab=="BULLISH_GRAB":long+=10;lr.append("Bullish Liquidity Grab")
    if grab=="BEARISH_GRAB":short+=10;sr.append("Bearish Liquidity Grab")
    if fvg=="BULLISH_FVG":long+=10;lr.append(f"Bullish FVG (≥${MIN_FVG_SIZE})")
    if fvg=="BEARISH_FVG":short+=10;sr.append(f"Bearish FVG (≥${MIN_FVG_SIZE})")
    if pat in ("BULLISH_ENGULF","HAMMER"):long+=ps*5;lr.append(f"Pattern: {pat}")
    if pat in ("BEARISH_ENGULF","SHOOTING_STAR"):short+=ps*5;sr.append(f"Pattern: {pat}")
    if rsi<35:long+=8;lr.append(f"RSI Oversold ({rsi})")
    elif rsi>65:short+=8;sr.append(f"RSI Overbought ({rsi})")
    if long>short and long>=min_confidence and tf=="BULLISH":sig,score,reasons="BUY",min(long,99),lr
    elif short>long and short>=min_confidence and tf=="BEARISH":sig,score,reasons="SELL",min(short,99),sr
    else:
        sig,score="HOLD",max(long,short)
        active=lr if tf=="BULLISH" else sr
        reasons=active[:2] or [f"15M {tf.title()} bias present","M5 entry confirmation not detected"]
        reasons.append(f"WAIT FOR M5 CONFIRMATION ({score}/{min_confidence})")
    d=1 if sig=="BUY" else -1
    return {"direction":sig,"confidence":score,"entry_low":round(price-.30,2) if sig!="HOLD" else 0.0,"entry_high":round(price+.30,2) if sig!="HOLD" else 0.0,"tp1":round(price+d*5,2) if sig!="HOLD" else 0.0,"tp2":round(price+d*10,2) if sig!="HOLD" else 0.0,"tp3":round(price+d*16,2) if sig!="HOLD" else 0.0,"sl":round(price-5,2) if sig=="BUY" else round(price+5,2) if sig=="SELL" else 0.0,"reasons":reasons,"rsi":rsi,"tf_bias":tf,"bos_type":bos or "None","choch":choch,"ob_high":oh,"ob_low":ol,"price_in_ob":inob,"eq_highs":eh,"eq_lows":el,"swept_high":sh,"swept_low":sl,"liquidity_grab":grab,"fvg":fvg,"pattern":pat}
