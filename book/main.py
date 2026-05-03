import argparse
import asyncio
import shutil
import sys
import time
import typing as ty
from multiprocessing import TimeoutError as MPTimeoutError
from multiprocessing.pool import AsyncResult, Pool
from pathlib import Path

import aiohttp
import pypdf
import pypdf.errors
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from rich.progress import Progress
from rich.rule import Rule

from book.config import Config
from book.errors import (
    ConvertionError,
    CorruptedPDFError,
    DownloadError,
    FileMissingError,
    MergingError,
    MissingDependencyError,
    PDFNotFoundError,
)
from book.web_layout import OutLinePage, Post


type SrcDstPairs = list[tuple[Path, Path]]
type ConversionResult = tuple[Exception | None, Path, Path]


class _Sentinel:
    ...


SENTINEL = _Sentinel()


DEFAULT_PDF_OPTIONS: dict[str, ty.Any] = {
    "base_url": "https://www.learncpp.com",
    "format": "A4",
    "scale": 1.0,
    "timeout_ms": 120_000,
    "margin": {
        "top": "13mm",
        "right": "12mm",
        "bottom": "15mm",
        "left": "12mm",
    },
}


def namesort(name: str) -> tuple[int, int | str]:
    """Used to sort filenames: 0 -> 9 -> a -> z."""
    return (0, int(name)) if name.isdigit() else (1, name)


def _check_dependencies() -> None:
    try:
        import playwright  # noqa: F401
    except ImportError as exc:
        raise MissingDependencyError(dep="playwright") from exc


def _html_to_pdf(
    html: Path,
    dst_f: Path,
    options: dict[str, ty.Any] | None = None,
) -> ConversionResult:
    render_options = DEFAULT_PDF_OPTIONS | (options or {})
    dst_f.parent.mkdir(parents=True, exist_ok=True)

    try:
        post = Post.parse_html(name=html.stem, text=html.read_text(encoding="utf-8"))
        post.remove_elements()
        document = post.to_pdf_html(base_url=str(render_options["base_url"]))

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--font-render-hinting=none",
                ],
            )

            page = browser.new_page(
                java_script_enabled=False,
                viewport={"width": 1240, "height": 1754},
                device_scale_factor=1,
            )

            timeout_ms = int(render_options["timeout_ms"])
            page.set_default_timeout(timeout_ms)

            page.set_content(
                document,
                wait_until="domcontentloaded",
                timeout=timeout_ms,
            )

            try:
                page.wait_for_load_state("networkidle", timeout=8_000)
            except PlaywrightTimeoutError:
                pass

            page.emulate_media(media="print")
            page.pdf(
                path=str(dst_f),
                format=str(render_options["format"]),
                scale=float(render_options["scale"]),
                print_background=True,
                prefer_css_page_size=True,
                display_header_footer=False,
                margin=render_options["margin"],
            )

            browser.close()

    except Exception as exc:
        return (exc, html, dst_f)

    return (None, html, dst_f)


def _merge_chapters(pdfs: list[Path], out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)

    merger = pypdf.PdfWriter()

    for file in pdfs:
        try:
            merger.append(file)
        except FileNotFoundError as exc:
            raise PDFNotFoundError(file) from exc
        except pypdf.errors.PdfStreamError as exc:
            file.unlink(missing_ok=True)
            raise CorruptedPDFError(file) from exc

    merger.write(out)
    merger.close()
    return out


class DownloadService:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        sems: asyncio.Semaphore,
        home_url: str,
        progress: Progress,
        max_retries: int,
    ):
        self._session = session
        self._sems = sems
        self._home_url = home_url
        self._progress = progress
        self._initial_timeout = 10
        self._retry_timeout = 30
        self._max_retries = max_retries
        self.__download_task: int | None = None

    async def get_content(self, url: str = "/") -> str:
        retry_count = 0
        timeout = self._initial_timeout
        last_exception: Exception | None = None

        while retry_count < self._max_retries:
            try:
                async with self._sems:
                    async with self._session.get(url, timeout=timeout) as response:
                        response.raise_for_status()
                        return await response.text()
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                self._progress.log(
                    f"Download error: attempt {retry_count + 1} failed: {url}: {exc}"
                )
                retry_count += 1
                timeout = self._retry_timeout
                last_exception = exc

        if last_exception:
            raise DownloadError(code=400, detail=str(last_exception))

        raise DownloadError(code=400, detail="unknown download error")

    async def download_outline(self) -> OutLinePage:
        html = await self.get_content(self._home_url)
        return OutLinePage.parse_html(html)

    async def download_chapter(self, link: str, dst_f: Path) -> None:
        res = await self.get_content(link)
        dst_f.parent.mkdir(parents=True, exist_ok=True)
        dst_f.write_text(res, encoding="utf-8")

        if self.__download_task is not None:
            self._progress.update(self.__download_task, advance=1)

    async def download_chapters(self, chapters_folder: Path, use_cache: bool) -> None:
        outline = await self.download_outline()
        todo: set[asyncio.Task[None]] = set()

        for table in outline.content_tables():
            table_folder = chapters_folder / table.name
            table_folder.mkdir(parents=True, exist_ok=True)

            for chapter in table.chapters:
                dst_f = table_folder / chapter.filename
                if use_cache and dst_f.exists():
                    continue

                task = asyncio.create_task(self.download_chapter(chapter.link, dst_f))
                todo.add(task)

        if not todo:
            self._progress.log("Using cached HTMLs, skip download")
            return

        self.__download_task = self._progress.add_task("[red]Downloading HTMLs...")
        self._progress.update(self.__download_task, total=len(todo))

        done, _ = await asyncio.wait(todo, timeout=None)

        for task in done:
            if (exc := task.exception()) is not None:
                raise exc

        self._progress.log(f"Finished downloading {len(todo)} HTMLs")

    async def __aenter__(self) -> "DownloadService":
        await self._session.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tbx) -> None:
        await self._session.__aexit__(exc_type, exc, tbx)


class FileManager:
    def __init__(
        self,
        cache_folder: Path,
        html_folder: Path,
        html_chapter: Path,
        pdf_folder: Path,
        pdf_chapter: Path,
        pdf_merged_chapter_folder: Path,
        error_log: Path,
    ):
        self.cache_folder = cache_folder
        self.html_folder = html_folder
        self.html_chapter = html_chapter
        self.pdf_folder = pdf_folder
        self.pdf_chapter = pdf_chapter
        self.pdf_merged_chapter_folder = pdf_merged_chapter_folder
        self.error_log = error_log
        self.__setup()

    def __setup(self) -> None:
        self.cache_folder.mkdir(parents=True, exist_ok=True)
        self.html_folder.mkdir(parents=True, exist_ok=True)
        self.html_chapter.mkdir(parents=True, exist_ok=True)
        self.pdf_folder.mkdir(parents=True, exist_ok=True)
        self.pdf_chapter.mkdir(parents=True, exist_ok=True)
        self.pdf_merged_chapter_folder.mkdir(parents=True, exist_ok=True)
        self.error_log.parent.mkdir(parents=True, exist_ok=True)
        self.error_log.touch()

    @property
    def chapter_folders(self) -> list[Path]:
        chapter_folders = sorted(
            self.html_chapter.iterdir(),
            key=lambda f: namesort(f.stem.split("Chapter")[1]),
        )
        return chapter_folders

    def sorted_dst_dirs(self) -> list[list[Path]]:
        dst_dirs: list[list[Path]] = []

        for chapter_folder in self.chapter_folders:
            pdf_chapter = self.pdf_chapter / chapter_folder.name
            pdf_chapter.mkdir(parents=True, exist_ok=True)

            htmls = sorted(
                chapter_folder.iterdir(),
                key=lambda h: namesort(h.stem.split("_")[1]),
            )
            pdf_files = [pdf_chapter / f"{src_f.stem}.pdf" for src_f in htmls]
            dst_dirs.append(pdf_files)

        return dst_dirs

    def sorted_dir_pairs(self, use_cache: bool) -> SrcDstPairs:
        res: SrcDstPairs = []

        if not self.chapter_folders:
            raise FileMissingError(
                "Missing HTMLs of every chapter, please download them first"
            )

        for chapter_folder in self.chapter_folders:
            pdf_chapter = self.pdf_chapter / chapter_folder.name
            pdf_chapter.mkdir(parents=True, exist_ok=True)

            htmls = sorted(
                chapter_folder.iterdir(),
                key=lambda h: namesort(h.stem.split("_")[1]),
            )

            for src_f in htmls:
                dst_f = pdf_chapter / f"{src_f.stem}.pdf"
                if use_cache and dst_f.exists():
                    continue
                res.append((src_f, dst_f))

        return res

    def remove_cache(self) -> None:
        shutil.rmtree(self.cache_folder, ignore_errors=True)

    def clear_errors(self) -> None:
        self.error_log.write_text("", encoding="utf-8")

    def append_error(self, error_info: str) -> None:
        with self.error_log.open(mode="a", encoding="utf-8") as file:
            file.write(f"{error_info}\n")

    def read_errors(self) -> str:
        return self.error_log.read_text(encoding="utf-8")


class Application:
    def __init__(
        self,
        *,
        bookfile: Path,
        cvt_max_retries: int,
        dl_service: DownloadService,
        file_mgr: FileManager,
        progress: Progress,
        worker_pool: Pool,
        worker_timeout: int,
        pdf_options: dict[str, ty.Any],
        remove_cache_on_success: bool = False,
    ):
        self._bookfile = bookfile
        self._cvt_max_retries = cvt_max_retries
        self._dl_service = dl_service
        self._file_mgr = file_mgr
        self._progress = progress
        self._worker_pool = worker_pool
        self._worker_timeout = worker_timeout
        self._pdf_options = pdf_options
        self._remove_cache_on_success = remove_cache_on_success
        self.__task_succeed = False

    async def __aenter__(self) -> ty.Self:
        self._progress.__enter__()
        self._worker_pool.__enter__()
        await self._dl_service.__aenter__()
        return self

    async def __aexit__(
        self,
        exctype: type[Exception] | None,
        exc: Exception | None,
        traceback,
    ) -> None:
        self.__exit_log()
        self._worker_pool.__exit__(exctype, exc, traceback)
        await self._dl_service.__aexit__(exctype, exc, traceback)
        self._progress.__exit__(exctype, exc, traceback)

    def __exit_log(self) -> None:
        self._progress.log("Cleaning up ...")

        if self.__task_succeed:
            self._progress.console.rule("[green]Application succeeded")
        else:
            self._progress.console.rule("[red]Application failed")
            self._progress.console.log(
                f"[red]See details in [bold]{self._file_mgr.error_log}[/bold]"
            )

    def succeed(self) -> None:
        self.__task_succeed = True

    async def download_chapters(self, use_cache: bool = True) -> None:
        await self._dl_service.download_chapters(
            self._file_mgr.html_chapter,
            use_cache=use_cache,
        )

    def _convert_to_pdf(self, dir_pairs: SrcDstPairs) -> list[ConversionResult]:
        results: list[ConversionResult] = []

        if not dir_pairs:
            self._progress.log("Using cached PDFs, skip converting")
            return results

        tasks: list[tuple[AsyncResult, Path, Path]] = [
            (
                self._worker_pool.apply_async(
                    _html_to_pdf,
                    args=(src_f, dst_f, self._pdf_options),
                ),
                src_f,
                dst_f,
            )
            for src_f, dst_f in dir_pairs
        ]

        convert_task = self._progress.add_task("[green]Converting HTMLs...")
        self._progress.update(convert_task, total=len(tasks))

        for task, src_path, dst_path in tasks:
            try:
                result = task.get(timeout=self._worker_timeout)
            except MPTimeoutError as exc:
                result = (exc, src_path, dst_path)
            except Exception as exc:
                result = (exc, src_path, dst_path)

            error, src_path, dst_path = result

            if error and not dst_path.exists():
                self._progress.log(f"Convert failed for {src_path}: {error}")

            results.append(result)
            self._progress.update(convert_task, advance=1)

        return results

    def _failed_cvt_filter(self, results: list[ConversionResult]) -> SrcDstPairs:
        return [(src_f, dst_f) for _, src_f, dst_f in results if not dst_f.exists()]

    def _log_failed_conversions(self, results: list[ConversionResult]) -> None:
        for error, src_f, dst_f in results:
            if dst_f.exists():
                continue

            if error is None:
                self._file_mgr.append_error(f"{src_f} -> {dst_f}: missing output PDF")
            else:
                self._file_mgr.append_error(f"{src_f} -> {dst_f}: {error}")

    def convert_and_retry(self, use_cache: bool = True) -> None:
        self._file_mgr.clear_errors()

        results = self._convert_to_pdf(self._file_mgr.sorted_dir_pairs(use_cache))
        all_results = list(results)
        failed_dirs = self._failed_cvt_filter(results)
        retries = 0

        while failed_dirs and retries < self._cvt_max_retries:
            retries += 1
            self._progress.log(
                f"{len(failed_dirs)} HTMLs could not be converted, retrying "
                f"({self._cvt_max_retries - retries} retries left)"
            )

            new_results = self._convert_to_pdf(failed_dirs)
            all_results.extend(new_results)
            failed_dirs = self._failed_cvt_filter(new_results)

        if failed_dirs:
            self._log_failed_conversions(all_results)
            raise ConvertionError(len(failed_dirs), self._file_mgr.error_log)

    def _merging_pdfs(self, merging_folder: Path, use_cache: bool = True) -> list[Path]:
        dst_dirs = self._file_mgr.sorted_dst_dirs()

        if not dst_dirs:
            raise FileMissingError("Missing HTMLs to convert, download them first")

        merging_task = self._progress.add_task("[cyan]Merging PDFs...")
        tasks: list[tuple[AsyncResult, Path]] = []
        merged: list[Path] = []

        for pdf_dirs in dst_dirs:
            if not pdf_dirs:
                continue

            chapter_idx = pdf_dirs[0].parent.stem.split("Chapter")[1]
            dst_f = merging_folder / f"chapter_{chapter_idx}.pdf"

            if use_cache and dst_f.exists():
                merged.append(dst_f)
                continue

            if dst_f.exists():
                dst_f.unlink()

            task = self._worker_pool.apply_async(_merge_chapters, args=(pdf_dirs, dst_f))
            tasks.append((task, dst_f))

        if not tasks:
            self._progress.log("Using cached chapters, skip merging")
            self._progress.remove_task(merging_task)
            return merged

        self._progress.update(merging_task, total=len(tasks))

        for task, dst_f in tasks:
            try:
                res = task.get(timeout=self._worker_timeout)
            except Exception as exc:
                raise MergingError(f"{dst_f}: {exc}") from exc

            merged.append(res)
            self._progress.update(merging_task, advance=1)

        return sorted(merged, key=lambda path: namesort(path.stem.split("_")[1]))

    def merge_chapters(self, use_cache: bool = True) -> Path:
        bookfile = self._bookfile

        if use_cache and bookfile.exists():
            self._progress.log(f"Book '{bookfile.name}' already exists, skip merging")
            return bookfile

        merged = self._merging_pdfs(
            self._file_mgr.pdf_merged_chapter_folder,
            use_cache=use_cache,
        )

        return _merge_chapters(merged, bookfile)

    def show_errors(self) -> None:
        error_logs = self._file_mgr.error_log.read_text(encoding="utf-8")

        if not error_logs:
            self._progress.log("No errors found in the error log")
            return

        for error_log in error_logs.split("\n"):
            if error_log.strip():
                self._progress.log(error_log)

    def application_succeeded(self) -> bool:
        return not self._file_mgr.error_log.exists() or self._file_mgr.read_errors() == ""

    async def run(self, args: argparse.Namespace | _Sentinel = SENTINEL) -> None:
        pre = time.perf_counter()

        if isinstance(args, _Sentinel):
            await self.download_chapters()
            self.convert_and_retry()
            self.merge_chapters()

        elif args.all:
            await self.download_chapters(use_cache=False)
            self.convert_and_retry(use_cache=False)
            self.merge_chapters(use_cache=False)

        else:
            if args.download:
                await self.download_chapters(use_cache=False)
                self._progress.log("Chapters downloaded")

            if args.convert:
                self.convert_and_retry(use_cache=False)
                self._progress.log("HTMLs converted")

            if args.merge:
                self.merge_chapters(use_cache=False)
                self._progress.log("PDFs merged")

            if args.rmcache:
                self._file_mgr.remove_cache()
                self._progress.log("Cache removed")

            if args.showerrors:
                self.show_errors()

        aft = time.perf_counter()

        if self.application_succeeded():
            self.succeed()
            if self._remove_cache_on_success:
                self._file_mgr.remove_cache()

        self._progress.log(Rule("Complete"))
        self._progress.log(f"cost {round(aft - pre, 3)}s")


def session_factory(timeout: int = 120) -> aiohttp.ClientSession:
    client_timeout = aiohttp.ClientTimeout(total=timeout, connect=timeout // 4)
    return aiohttp.ClientSession(timeout=client_timeout)


def app_factory(config: Config) -> Application:
    sems = asyncio.Semaphore(value=config.DOWNLOAD_CONCURRENT_MAX)
    progress = Progress()

    dl_service = DownloadService(
        session=session_factory(),
        sems=sems,
        home_url=config.LEARNCPP,
        progress=progress,
        max_retries=config.DOWNLOAD_CONTENT_RETRY,
    )

    file_mgr = FileManager(
        cache_folder=config.CACHE_FOLDER,
        html_folder=config.HTML_FOLDER,
        html_chapter=config.HTML_CHAPTER,
        pdf_folder=config.PDF_FOLDER,
        pdf_chapter=config.PDF_CHAPTER,
        pdf_merged_chapter_folder=config.PDF_MERGED_CHAPTER_FOLDER,
        error_log=config.ERROR_LOG,
    )

    pool = Pool(processes=config.COMPUTE_PROCESS_MAX)

    pdf_options = DEFAULT_PDF_OPTIONS | {
        "base_url": config.LEARNCPP,
        "format": config.PDF_FORMAT,
        "scale": config.PDF_SCALE,
        "timeout_ms": config.PLAYWRIGHT_TIMEOUT_MS,
    }

    return Application(
        bookfile=config.BOOK_PATH,
        cvt_max_retries=config.PDF_CONVERTION_MAX_RETRY,
        dl_service=dl_service,
        file_mgr=file_mgr,
        progress=progress,
        worker_pool=pool,
        worker_timeout=config.COMPUTE_PROCESS_TIMEOUT,
        pdf_options=pdf_options,
        remove_cache_on_success=config.REMOVE_CACHE_ON_SUCCESS,
    )


def parser_factory() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(__name__)

    parser.add_argument(
        "-D",
        "--download",
        dest="download",
        help="Download articles from learncpp.com",
        action="store_true",
    )
    parser.add_argument(
        "-C",
        "--convert",
        dest="convert",
        help="Convert downloaded HTMLs to PDFs",
        action="store_true",
    )
    parser.add_argument(
        "-M",
        "--merge",
        help="Merge chapters into a single book",
        action="store_true",
    )
    parser.add_argument(
        "-A",
        "--all",
        help="Download, convert, and merge",
        action="store_true",
    )
    parser.add_argument(
        "-R",
        "--rmcache",
        help="Remove cache",
        action="store_true",
    )
    parser.add_argument(
        "-S",
        "--showerrors",
        help="Show error log in the console",
        action="store_true",
    )

    return parser


async def main() -> None:
    _check_dependencies()

    config = Config.from_env()
    parser = parser_factory()
    args = parser.parse_args() if len(sys.argv) > 1 else SENTINEL

    async with app_factory(config) as app:
        await app.run(args)


if __name__ == "__main__":
    asyncio.run(main())