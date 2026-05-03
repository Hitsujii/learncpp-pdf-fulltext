# LearnCpp PDF Full Text Generator

A fork of [`raceychan/learncpp_pdf`](https://github.com/raceychan/learncpp_pdf) focused on generating a LearnCpp PDF with embedded, selectable, copyable, and searchable text.

The original project uses `wkhtmltopdf`/`pdfkit`. Its output is visually correct, but the generated PDF is not a text PDF: text cannot be selected, copied, or searched.

This fork uses Playwright/Chromium with a custom print layout to generate a PDF that behaves like a regular text document.

## Disclaimer

All lesson content comes directly from [learncpp.com](https://learncpp.com). The lesson text is not modified. Decorative elements, navigation elements, and comments are removed for readability.

Please consider supporting LearnCpp through their [About page](https://www.learncpp.com/about/).

LearnCpp asks users not to redistribute PDF versions of the site. This repository only provides a generator so users can build a local copy for personal use. Generated PDFs are not committed to this repository and should not be redistributed.

## Why this fork exists

This fork solves two practical problems:

1. It replaces the original `wkhtmltopdf`/`pdfkit` rendering path with Playwright/Chromium and a dedicated print stylesheet. This produces a PDF with embedded text instead of a visually correct but non-selectable output.

2. It provides a [GitHub Actions workflow](#build-with-github-actions) for builds affected by Cloudflare `520` errors. When local access to LearnCpp fails before rendering starts, users can build the PDF from GitHub-hosted infrastructure instead.

## Changes compared to the original project

- Replaces `wkhtmltopdf`/`pdfkit` with Playwright/Chromium
- Adds a print-focused HTML/CSS layout
- Generates PDFs with embedded text
- Adds a [GitHub Actions workflow](#build-with-github-actions) for building the PDF as an artifact

## Requirements

This project uses [pixi](https://pixi.sh/) to manage the Python environment and dependencies.

Required:

- `pixi`
- Chromium installed through Playwright

Optional:

- `make`, only needed for `make run`

## Build locally

Install dependencies:

```bash
pixi install
```

Install Chromium for Playwright:

```bash
pixi run python -m playwright install chromium
```

Build the PDF:

```bash
pixi run python -m book
```

You can also use:

```bash
make run
```

See [Output](#output) for the generated file location.

## Build with GitHub Actions

Use the GitHub Actions workflow when LearnCpp returns Cloudflare `520` errors from your local network, or when you prefer to build the PDF from GitHub-hosted infrastructure.

To build the PDF from GitHub:

1. Fork this repository.
2. Open the `Actions` tab in your fork.
3. Select `Build LearnCpp PDF`.
4. Click `Run workflow`.
5. Wait for the workflow run to finish.
6. Download the generated PDF from the workflow run's artifacts section.

## Configuration

You can override defaults with a `.env` file in the project root.

| key                      | type  | default        |
| ------------------------ | ----- | -------------- |
| DOWNLOAD_CONCURRENT_MAX  | int   | 200            |
| COMPUTE_PROCESS_MAX      | int   | os.cpu_count() |
| COMPUTE_PROCESS_TIMEOUT  | int   | 300            |
| DOWNLOAD_CONTENT_RETRY   | int   | 6              |
| PDF_CONVERTION_MAX_RETRY | int   | 3              |
| BOOK_NAME                | str   | learncpp.pdf   |
| REMOVE_CACHE_ON_SUCCESS  | bool  | False          |
| PLAYWRIGHT_TIMEOUT_MS    | int   | 120000         |
| PDF_FORMAT               | str   | A4             |
| PDF_SCALE                | float | 1.0            |

`PDF_CONVERTION_MAX_RETRY` intentionally keeps the original misspelled option name for compatibility.

The default value of `DOWNLOAD_CONCURRENT_MAX` is kept for compatibility with the original project. If you override it, consider using a lower value to avoid putting unnecessary pressure on LearnCpp.

Example:

```env
DOWNLOAD_CONCURRENT_MAX=3
DOWNLOAD_CONTENT_RETRY=10
COMPUTE_PROCESS_MAX=2
COMPUTE_PROCESS_TIMEOUT=300
PDF_CONVERTION_MAX_RETRY=5
PLAYWRIGHT_TIMEOUT_MS=120000
BOOK_NAME=learncpp.pdf
REMOVE_CACHE_ON_SUCCESS=False
```

## CLI

Show available options:

```bash
pixi run python -m book --help
```

```text
options:
  -h, --help        show this help message and exit
  -D, --download    Download articles from learncpp.com, ignore cache
  -C, --convert     Convert downloaded HTMLs to PDFs, ignore cache
  -M, --merge       Merge chapters into a single book, ignore cache
  -R, --rmcache     Remove the cache folder
  -A, --all         Download, convert, and merge
  -S, --showerrors  Show error log in the console
```

Example:

```bash
pixi run python -m book --all
```

If no command is specified, all actions are executed. Cached files are reused when possible.

## Cache and retries

Downloaded pages and intermediate files are cached. Re-running the command usually resumes from the last successful step instead of starting from scratch.

If a download or conversion step fails temporarily, run the command again. Cached files are reused when possible.

To remove the cache manually:

```bash
pixi run python -m book --rmcache
```

## Output

By default, the generated PDF is written to:

```text
learncpp.pdf
```

You can change the output filename with `BOOK_NAME` in `.env`.

## Upstream project

This fork is based on [`raceychan/learncpp_pdf`](https://github.com/raceychan/learncpp_pdf).

It is not intended to replace the original project. It provides an alternative build path for users who need a LearnCpp PDF with embedded text or cannot access LearnCpp reliably from their local network.

## Alternatives

- [Original LearnCPP-PDF](https://github.com/raceychan/learncpp_pdf)
- [LearnCPP Downloader](https://github.com/amalrajan/learncpp-download)
