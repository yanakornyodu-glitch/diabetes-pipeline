"""Run the whole pipeline with one command:  python run_pipeline.py

Options:
  --skip-publish   run ingest + transform only (no Google Sheets upload)
"""
import argparse
import time

import ingest
import publish
import transform


def run_step(name: str, func) -> None:
    print(f"\n=== {name} ===")
    start = time.time()
    func()
    print(f"=== {name} finished in {time.time() - start:.1f}s ===")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-publish", action="store_true")
    args = parser.parse_args()

    run_step("1/3 INGEST (CSV -> PostgreSQL raw_data)", ingest.main)
    run_step("2/3 TRANSFORM (raw_data -> production)", transform.main)
    if args.skip_publish:
        print("\n[skip] publish skipped (--skip-publish)")
    else:
        run_step("3/3 PUBLISH (production -> Google Sheets)", publish.main)
    print("\nPipeline finished successfully")


if __name__ == "__main__":
    main()
