import os
import re
import json
import urllib.request

APIFY_TOKEN = os.environ.get("APIFY_API_TOKEN")

# Keywords weighted to your profile
KEYWORDS = {
    "PMP": 5, "CSPO": 5, "SAFe": 4, "POPM": 4, "PSM": 3,
    "Public Trust": 6, "Agile": 3, "AWS": 4, "Federal": 5,
    "Modernization": 4, "Grants": 4, "Backlog": 3, "Six Sigma": 3
}

def score_job(text):
    base_score = 72
    text_lower = text.lower()
    for kw, pts in KEYWORDS.items():
        if kw.lower() in text_lower:
            base_score += pts
    return min(base_score, 99)

def fetch_apify_actor(actor_id, payload):
    if not APIFY_TOKEN:
        print("No APIFY_API_TOKEN found. Using fallback mock verification.")
        return []
    url = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items?token={APIFY_TOKEN}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Error calling {actor_id}: {e}")
        return []

def main():
    # 1. Fetch HiringCafe & LinkedIn jobs via Apify
    hc_payload = {
        "searchQueries": ["Technical Project Manager", "Product Manager", "IT Program Manager"],
        "locations": ["Virginia", "Washington, DC", "Maryland", "Remote"],
        "maxItems": 100
    }
    raw_jobs = fetch_apify_actor("ocrad~hiringcafe-jobs-scraper", hc_payload)

    normalized_jobs = []
    for item in raw_jobs:
        title = item.get("title") or "Senior Technical Project Manager"
        company = item.get("companyName") or "Enterprise Partner"
        desc = item.get("description") or ""
        location = item.get("location") or "Northern Virginia / Hybrid"
        url = item.get("url") or "https://hiringcafe.com"

        match_score = score_job(f"{title} {desc}")
        normalized_jobs.append({
            "title": title,
            "company": company,
            "source": "HiringCafe",
            "ats": item.get("ats", "Workday"),
            "match": match_score,
            "tags": [location, "PMP / Agile", "Full-Time"],
            "desc": desc[:240] + "..." if len(desc) > 240 else desc,
            "url": url
        })

    if not normalized_jobs:
        print("No new jobs returned from API; keeping existing board state.")
        return

    # 2. Inject into index.html between marker comments
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()

    pattern = r"(// <!-- JOBS_DATA_START -->).*?(// <!-- JOBS_DATA_END -->)"
    replacement = f"\\1\nconst initialJobs = {json.dumps(normalized_jobs, indent=2)};\n\\2"

    if re.search(pattern, html, flags=re.DOTALL):
        updated_html = re.sub(pattern, replacement, html, flags=re.DOTALL)
        with open("index.html", "w", encoding="utf-8") as f:
            f.write(updated_html)
        print(f"Successfully injected {len(normalized_jobs)} jobs into index.html.")
    else:
        print("Markers // <!-- JOBS_DATA_START --> not found in index.html.")

if __name__ == "__main__":
    main()
