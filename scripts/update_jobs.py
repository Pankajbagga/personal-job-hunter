import os
import re
import json
import time
import urllib.request
import urllib.error

APIFY_TOKEN = os.environ.get("APIFY_API_TOKEN")

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
        print("No APIFY_API_TOKEN found in environment variables.")
        return []

    formatted_actor_id = actor_id.replace("/", "~")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {APIFY_TOKEN.strip()}"
    }

    start_url = f"https://api.apify.com/v2/acts/{formatted_actor_id}/runs"
    req = urllib.request.Request(
        start_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            run_data = json.loads(resp.read().decode("utf-8"))
            run_id = run_data["data"]["id"]
            dataset_id = run_data["data"]["defaultDatasetId"]
            print(f"Started Apify Actor run: {run_id}")
    except urllib.error.HTTPError as e:
        print(f"Apify HTTP {e.code} Error starting {actor_id}: {e.read().decode('utf-8')}")
        return []
    except Exception as e:
        print(f"Error starting {actor_id}: {e}")
        return []

    poll_url = f"https://api.apify.com/v2/actor-runs/{run_id}"
    max_wait = 100
    elapsed = 0
    poll_interval = 10

    while elapsed < max_wait:
        time.sleep(poll_interval)
        elapsed += poll_interval

        try:
            poll_req = urllib.request.Request(poll_url, headers=headers)
            with urllib.request.urlopen(poll_req, timeout=30) as resp:
                status_data = json.loads(resp.read().decode("utf-8"))
                status = status_data["data"]["status"]
                print(f"Actor status: {status} ({elapsed}s elapsed)")

                if status == "SUCCEEDED":
                    break
                elif status in ["FAILED", "ABORTED", "TIMED-OUT"]:
                    print(f"Actor run failed with status: {status}")
                    return []
        except Exception as e:
            print(f"Polling error: {e}")

    data_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?clean=true&format=json"
    try:
        data_req = urllib.request.Request(data_url, headers=headers)
        with urllib.request.urlopen(data_req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Error fetching dataset items: {e}")
        return []

def main():
    payload = {
        "queries": [
            "Technical Project Manager",
            "IT Program Manager",
            "Deputy Program Manager"
        ],
        "locations": ["Virginia", "Washington DC", "Remote"],
        "maxItems": 10,
        "datePosted": "past-week"
    }

    print("Fetching jobs via Apify (bebity/linkedin-jobs-scraper)...")
    raw_jobs = fetch_apify_actor("bebity/linkedin-jobs-scraper", payload)

    normalized_jobs = []
    if isinstance(raw_jobs, list):
        for item in raw_jobs:
            title = item.get("title") or item.get("jobTitle") or "Technical Project Manager"
            company = item.get("companyName") or item.get("company") or "Enterprise Partner"
            desc = item.get("description") or item.get("jobDescription") or ""
            location = item.get("location") or "Virginia / Remote"
            url = item.get("link") or item.get("jobUrl") or item.get("url") or "https://www.linkedin.com"

            match_score = score_job(f"{title} {desc}")
            normalized_jobs.append({
                "title": title,
                "company": company,
                "source": "LinkedIn",
                "ats": item.get("ats", "Direct"),
                "match": match_score,
                "tags": [location, "PMP / Agile", "Full-Time"],
                "desc": desc[:240] + "..." if len(desc) > 240 else desc,
                "url": url
            })

    if not normalized_jobs:
        print("No new jobs returned from API; keeping existing board state.")
        return

    try:
        with open("index.html", "r", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        print("Error: index.html not found.")
        return

    START_MARKER = "// <!-- JOBS_DATA_START -->"
    END_MARKER = "// <!-- JOBS_DATA_END -->"

    if START_MARKER not in html or END_MARKER not in html:
        print(f"Error: Markers '{START_MARKER}' and '{END_MARKER}' not found in index.html.")
        return
    # Extract existing array safely between markers
    
    before_marker = html.split(START_MARKER)[0]
    after_start = html.split(START_MARKER)[1]
    middle_content = after_start.split(END_MARKER)[0]
    after_marker = after_start.split(END_MARKER)[1]
    
    # Find the JSON array inside the middle section

    array_match = re.search(r"const initialJobs\s*=\s*(\[.*?\]);", middle_content, flags=re.DOTALL)
    existing_jobs = []
    if array_match:
        try:
            existing_jobs = json.loads(array_match.group(1))
        except Exception:
            existing_jobs = []
            
    # Merge and deduplicate by Title + Company
    
    seen = {f"{job.get('title')}{job.get('company')}" for job in existing_jobs}
    added_count = 0

    for job in normalized_jobs:
        key = f"{job.get('title')}{job.get('company')}"
        if key not in seen:
            existing_jobs.insert(0, job)
            seen.add(key)
            added_count += 1

    print(f"Added {added_count} new jobs. Total jobs on board: {len(existing_jobs)}")
 
    # Format JSON cleanly without regex escaping issues
    
    updated_jobs_json = json.dumps(existing_jobs, indent=2)
    replacement_block = f"\n  const initialJobs = {updated_jobs_json};\n  "

    new_html = f"{before_marker}{START_MARKER}{replacement_block}{END_MARKER}{after_marker}"

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(new_html)
    print("Successfully updated index.html with new jobs.")

if __name__ == "__main__":
    main()
