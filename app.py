#!/usr/bin/env python3
"""EscrowLens — تحقق من ضمان الدفع على Solana قبل ما تشتغل.

MVP لفرصة Road to Colosseum ($8,000).
الخادم: stdlib فقط (بلا مكتبات) + Solana JSON-RPC حقيقي.
"""
import json
import os
import re
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get("PORT", 80))
RPC = os.environ.get("SOLANA_RPC", "https://api.devnet.solana.com")
RPC_MAIN = "https://api.mainnet-beta.solana.com"
HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
KNOWN_TOKENS = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
    "2u1tszSeqZ3qBWF3uNGPFc8TzMk2tdiwknnRMWGWjGWH": "USDG",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT",
    "So11111111111111111111111111111111111111112": "SOL (wrapped)",
}

_cache = {}


def rpc(method, params, main=False, timeout=25):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": params}).encode()
    req = urllib.request.Request(RPC_MAIN if main else RPC, data=body,
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "EscrowLens/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r).get("result")


def solscan(address, cluster=""):
    return f"https://solscan.io/account/{address}{'?cluster=devnet' if cluster else ''}"


def check_address(addr):
    """يفحص عنواناً: الرصيد، التوكنات، النشاط، والتقييم."""
    addr = addr.strip()
    if not re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}", addr):
        return {"ok": False, "error": "عنوان Solana غير صالح"}

    key = addr.lower()
    if key in _cache and time.time() - _cache[key][0] < 45:
        return _cache[key][1]

    out = {"ok": True, "address": addr, "checked_at": int(time.time())}
    try:
        # الرصيد على devnet و mainnet
        for tag, main in (("devnet", False), ("mainnet", True)):
            bal = rpc("getBalance", [addr], main=main) or {}
            out[f"lamports_{tag}"] = bal.get("value", 0)
        # التوكنات
        toks = []
        try:
            res = rpc("getTokenAccountsByOwner",
                      [addr, {"programId": TOKEN_PROGRAM},
                       {"encoding": "jsonParsed"}]) or {}
            for acc in res.get("value", []):
                info = acc["account"]["data"]["parsed"]["info"]
                ui = info["tokenAmount"]
                toks.append({
                    "mint": info["mint"],
                    "symbol": KNOWN_TOKENS.get(info["mint"], info["mint"][:6] + "…"),
                    "amount": float(ui.get("uiAmountString") or 0),
                    "decimals": ui.get("decimals"),
                    "account": acc["pubkey"],
                })
        except Exception:                            # noqa: BLE001
            pass
        out["tokens"] = sorted(toks, key=lambda x: -x["amount"])
        # النشاط
        sigs = rpc("getSignaturesForAddress", [addr, {"limit": 15}], main=True) or []
        out["tx_count"] = len(sigs)
        out["last_tx"] = (sigs[0].get("blockTime") if sigs else None)
        out["recent"] = [{"sig": s.get("signature"), "slot": s.get("slot"),
                          "time": s.get("blockTime"), "err": bool(s.get("err"))}
                         for s in sigs[:6]]

        # 📊 التقييم — منطق EscrowLens
        sol_dn = out["lamports_devnet"] / 1e9
        sol_mn = out["lamports_mainnet"] / 1e9
        stable = sum(t["amount"] for t in out["tokens"]
                     if t["symbol"] in ("USDC", "USDG", "USDT"))
        score, notes = 0, []
        if stable > 0:
            score += 45
            notes.append(f"يحمل {stable:,.2f} دولار مستقر (USDC/USDG/USDT) على السلسلة")
        else:
            notes.append("لا توجد عملات مستقرة في هذا العنوان")
        if sol_mn > 0.01:
            score += 20
            notes.append(f"رصيد {sol_mn:.4f} SOL على mainnet (عنوان مستخدم فعلاً)")
        if out["tx_count"] >= 5:
            score += 20
            notes.append(f"{out['tx_count']} معاملة حديثة — عنوان نشط")
        elif out["tx_count"] > 0:
            score += 8
            notes.append("نشاط قليل على السلسلة")
        else:
            notes.append("⚠️ لا نشاط على السلسلة — عنوان جديد أو وهمي")
        if out["last_tx"]:
            days = (time.time() - out["last_tx"]) / 86400
            if days < 30:
                score += 15
                notes.append(f"آخر معاملة قبل {days:.0f} يوم")
        out["score"] = min(score, 100)
        out["notes"] = notes
        out["verdict"] = ("مؤشر ثقة عالٍ" if score >= 70 else
                          "يحتاج تحقق يدوي" if score >= 40 else
                          "خطر مرتفع — لا تبدي شغلاً")
        out["explorer_devnet"] = solscan(addr, "devnet")
        out["explorer_mainnet"] = solscan(addr)
    except Exception as e:                           # noqa: BLE001
        out["ok"] = False
        out["error"] = f"تعذّر الوصول لشبكة Solana: {str(e)[:120]}"
    _cache[key] = (time.time(), out)
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "EscrowLens/1.0"

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/check":
            addr = (parse_qs(u.query).get("address") or [""])[0]
            self._send(200, json.dumps(check_address(addr), ensure_ascii=False))
            return
        if u.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "public", "index.html"), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
            return
        if u.path == "/health":
            self._send(200, json.dumps({"ok": True, "rpc": RPC}))
            return
        self._send(404, json.dumps({"error": "not found"}))

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"EscrowLens on :{PORT} (RPC={RPC})")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
