# -*- coding: utf-8 -*-

from pathlib import Path
import json
import traceback

from visual_analyzer import DeepVisualAnalyzer


TEST_LIBRARY = Path("test_library")
PREVIOUS_RESULTS = Path("test_visual_results.json")

OUTPUT_FILE = Path("test_visual_results_v04.json")
DEBUG_DIR = Path("test_debug_v04")


def main():

    if not TEST_LIBRARY.exists():
        raise FileNotFoundError(
            f"Test library not found: {TEST_LIBRARY}"
        )

    if not PREVIOUS_RESULTS.exists():
        raise FileNotFoundError(
            f"Previous results not found: {PREVIOUS_RESULTS}"
        )

    # ----------------------------------------------------
    # خواندن دقیقاً همان 20 فایل تست قبلی
    # ----------------------------------------------------

    with open(
        PREVIOUS_RESULTS,
        "r",
        encoding="utf-8",
    ) as file:

        previous = json.load(file)

    previous_results = previous.get(
        "results",
        [],
    )

    filenames = [
        item["filename"]
        for item in previous_results
        if item.get("filename")
    ]

    if len(filenames) != 20:
        raise RuntimeError(
            f"Expected exactly 20 previous samples, "
            f"but found {len(filenames)}"
        )

    # ----------------------------------------------------
    # پیدا کردن همان 20 فایل
    # ----------------------------------------------------

    files = []

    for filename in filenames:

        path = TEST_LIBRARY / filename

        if not path.exists():

            # fallback برای filenameهایی که ممکن است
            # در subfolder باشند
            matches = list(
                TEST_LIBRARY.rglob(
                    Path(filename).name
                )
            )

            if len(matches) == 1:
                path = matches[0]

            elif len(matches) == 0:
                raise FileNotFoundError(
                    f"Sample not found: {filename}"
                )

            else:
                raise RuntimeError(
                    f"Multiple files found for: {filename}"
                )

        files.append(path)

    # ----------------------------------------------------
    # Analyzer
    # ----------------------------------------------------

    analyzer = DeepVisualAnalyzer(
        debug=True,
        debug_dir=DEBUG_DIR,
    )

    print()
    print("=" * 70)
    print("VISUAL ANALYZER V0.4")
    print("CONTROLLED 20-SAMPLE TEST")
    print("=" * 70)
    print()

    print(
        "Previous test samples:",
        len(files),
    )

    print(
        "Source:",
        TEST_LIBRARY,
    )

    print(
        "Knowledge update:",
        "DISABLED",
    )

    print()

    results = []
    failed = []

    # ----------------------------------------------------
    # فقط همان 20 فایل
    # ----------------------------------------------------

    for index, path in enumerate(
        files,
        start=1,
    ):

        print(
            f"[{index:02d}/20] "
            f"{path.name}"
        )

        try:

            result = analyzer.analyze_image(
                path
            )

            results.append(
                result
            )

            extraction = result.get(
                "signature_extraction",
                {},
            )

            print(
                "      panels:",
                extraction.get(
                    "panel_count",
                    0,
                ),
            )

            print(
                "      frame ROIs:",
                extraction.get(
                    "frame_roi_count",
                    0,
                ),
            )

            print(
                "      signature ratio:",
                extraction.get(
                    "signature_ratio",
                    0.0,
                ),
            )

            print()

        except Exception as exc:

            print()
            print("ERROR")
            print(
                "File:",
                path,
            )
            print(
                "Type:",
                type(exc).__name__,
            )
            print(
                "Message:",
                exc,
            )

            traceback.print_exc()

            failed.append(
                {
                    "filename": str(path),
                    "error": str(exc),
                    "type": type(exc).__name__,
                }
            )

            print()

    # ----------------------------------------------------
    # ذخیره نتیجه
    # ----------------------------------------------------

    output = {
        "test_library": str(
            TEST_LIBRARY
        ),
        "analyzer_version": (
            analyzer.VERSION
        ),
        "pipeline_version": (
            analyzer.PIPELINE_VERSION
        ),
        "total": len(files),
        "successful": len(results),
        "failed": failed,
        "results": results,
    }

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            output,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print()
    print("=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)
    print()
    print(
        f"Expected:   20"
    )
    print(
        f"Successful: {len(results)}"
    )
    print(
        f"Failed:     {len(failed)}"
    )
    print()
    print(
        f"Results: {OUTPUT_FILE}"
    )
    print(
        f"Debug:   {DEBUG_DIR}"
    )
    print()


if __name__ == "__main__":
    main()