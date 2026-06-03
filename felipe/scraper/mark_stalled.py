"""Mark a job as stalled when the re-dispatch cap is reached."""

import argparse
from pathlib import Path

from sheets import mark_job_status

STATUS_FILE = Path("/tmp/scrape_status")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--job-id", required=True)
    p.add_argument("--sheets-id", required=True)
    p.add_argument("--gcp-credentials", required=True)
    args = p.parse_args()

    mark_job_status(args.sheets_id, args.job_id, "stalled", args.gcp_credentials)
    STATUS_FILE.write_text("stalled")
    print(f"Job {args.job_id} marked as stalled.")


if __name__ == "__main__":
    main()
