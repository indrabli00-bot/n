from __future__ import annotations
import base64, hashlib, hmac, json, time, uuid
import aiohttp
import database
from config import BELMO_PUBLIC_URL, PLAN_IDS, WHOP_API_KEY, WHOP_COMPANY_ID, WHOP_WEBHOOK_SECRET

BASE = 'https://api.whop.com/api/v1'

def verify_webhook(payload: bytes, headers) -> dict:
    h = {str(k).lower(): str(v) for k,v in headers.items()}
    wid, ts, sig = h.get('webhook-id',''), h.get('webhook-timestamp',''), h.get('webhook-signature','')
    if not wid or not ts or not sig: raise ValueError('missing_webhook_headers')
    if abs(time.time()-int(ts)) > 300: raise ValueError('webhook_timestamp_expired')
    secret = WHOP_WEBHOOK_SECRET
    key = secret[6:] if secret.startswith('whsec_') else secret
    try: key = base64.b64decode(key + '='*((4-len(key)%4)%4))
    except Exception: key = key.encode()
    signed = f'{wid}.{ts}.'.encode()+payload
    digest = base64.b64encode(hmac.new(key,signed,hashlib.sha256).digest()).decode()
    if not any(x.startswith('v1,') and hmac.compare_digest(x[3:],digest) for x in sig.split()): raise ValueError('invalid_webhook_signature')
    return json.loads(payload)

async def create_checkout(telegram_id: int, days: int) -> tuple[str,str]:
    plan_id = PLAN_IDS.get(days)
    if not plan_id: raise ValueError('unsupported_plan')
    order_id = 'ng_' + uuid.uuid4().hex
    database.create_order(order_id, telegram_id, plan_id, days)
    payload = {'plan_id': plan_id, 'mode':'payment', 'metadata': {'neural_order_id':order_id,'telegram_id':str(telegram_id),'plan_days':str(days),'source':'neural_gold'}}
    if BELMO_PUBLIC_URL: payload['redirect_url'] = f'{BELMO_PUBLIC_URL}/?checkout_status=success'
    headers={'Authorization':f'Bearer {WHOP_API_KEY}','Content-Type':'application/json','Idempotency-Key':f'checkout-{order_id}'}
    timeout=aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.post(f'{BASE}/checkout_configurations',json=payload,headers=headers) as r:
            body=await r.json(content_type=None)
            if r.status >= 300: raise RuntimeError(f'whop_http_{r.status}')
    url=str(body.get('purchase_url') or '')
    if not url: raise RuntimeError('whop_missing_purchase_url')
    database.update_order(order_id, checkout_id=str(body.get('id') or ''), status='checkout_created')
    return url, order_id
