
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
    # 1. Fetch HiringCafe jobs via Apify
    hc_payload = {
        "maxItems": 50,
        "searchQueries": [
            "Technical Project Manager", 
            "Product Manager", 
            "IT Program Manager", 
            "IT Delivery Lead", 
            "Deputy Program Manager"
        ],
        "locations": ["Virginia", "Washington, DC", "Maryland", "Remote"]
    }
    raw_jobs = fetch_apify_actor("blackfalcondata/hiringcafe-scraper", hc_payload)

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

    # 2. Inject and Append into index.html
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        print("Error: index.html not found.")
        return

    pattern = r"(// <!-- JOBS_DATA_START -->\s*const initialJobs = )(\[.*?\])(;\s*// <!-- JOBS_DATA_END -->)"
    match = re.search(pattern, html, flags=re.DOTALL)

    if not match:
        print("Error: Markers '// <!-- JOBS_DATA_START -->' and '// <!-- JOBS_DATA_END -->' not found in index.html.")
        return

    existing_jobs_json = match.group(2)
    try:
        existing_jobs = json.loads(existing_jobs_json)
    except Exception:
        existing_jobs = []

    # Merge and deduplicate by Title + Company
    seen = {f"{job.get('title')}{job.get('company')}" for job in existing_jobs}
    added_count = 0
    
    for job in normalized_jobs:
        key = f"{job.get('title')}{job.get('company')}"
        if key not in seen:
            existing_jobs.insert(0, job)  # Prepend newest jobs to top
            seen.add(key)
            added_count += 1

    print(f"Added {added_count} new jobs. Total jobs on board: {len(existing_jobs)}")

    # Construct new content and write back to index.html
    updated_jobs_json = json.dumps(existing_jobs, indent=2)
    new_html = re.sub(
        pattern,
        rf"\g<1>{updated_jobs_json}\g<3>",
        html,
        flags=re.DOTALL
    )

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(new_html)
    print("Successfully updated index.html with new jobs.")

if __name__ == "__main__":
    main()
