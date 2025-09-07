import json, requests, time
url = "http://127.0.0.1:8000/predict"
payload = {
  "vendor_name":"Northwind Traders","invoice_number":"BATCH-0000",
  "date":"2025-07-20","tax_id":"DE99887766",
  "items":[{"description":"Keyboard","quantity":3,"unit_price":35.0,"category":"product"}],
  "currency":"EUR","raw_text":"Hardware order keyboard"
}
t0=time.time()
for i in range(50):
    p = payload.copy()
    p["invoice_number"] = f"BATCH-{i:04d}"
    r = requests.post(url, json=p, timeout=10)
    assert r.status_code==200, r.text
print("OK, 50 req in", round(time.time()-t0,2), "sec")
