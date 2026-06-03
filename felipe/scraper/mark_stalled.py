"""Mark a job as stalled when the re-dispatch cap is reached."""

import argparse
from pathlib import Path

from checkpoint import mark_job_status

STATUS_FILE = Path("/tmp/scrape_status")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--job-id", required=True)
    p.add_argument("--supabase-url", required=True)
    p.add_argument("--supabase-key", required=True)
    args = p.parse_args()

    mark_job_status(args.supabase_url, args.supabase_key, args.job_id, "stalled")
    STATUS_FILE.write_text("stalled")
    print(f"Job {args.job_id} marked as stalled.")


if __name__ == "__main__":
    main()
