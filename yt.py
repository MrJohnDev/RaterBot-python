import asyncio
import os
import sys
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout)


CACHE_LOC = './cache/Video/'
ATTEMPTS = 3

def clean_filename(filename: str):
    for c in ['<', '>', ':', '"', '/', '\\', '|', '?', '*']:
        filename = filename.replace(c, '')
    return filename

async def run_yt_dlp(video_url: str, simulate=False) -> str:
    """
    Downloads a YouTube video using yt-dlp.
    Args:
        video_url: The URL of the video to download.
        simulate: (Optional) Whether to simulate the download without actually downloading the video.
        dir: (Optional) The directory to download the video to.

    Returns:
        A subprocess.CompletedProcess instance containing the process results.
    """
    if not os.path.exists(CACHE_LOC):
        try:
            os.makedirs(CACHE_LOC)
        except Exception as e:
            logging.exception(f"Exception during directory creation: {e}")

    base_filename = clean_filename(video_url)
    base_file_loc = CACHE_LOC + base_filename

    expected_filename = base_filename + '.mp4'

    # Define yt-dlp arguments
    args = [
        # format conversion is failing: https://github.com/yt-dlp/yt-dlp/issues/6866
        # "--write-thumbnail",
        # "--convert-thumbnails",
        # "jpg",
        # "--format",
        # "bestvideo*[filesize<?30M]+bestaudio*/best[filesize<?40M]",
        "--format-sort",
        "filesize:40M",
        "--merge-output-format",
        "mp4",
        "--recode-video",
        "mp4",
        "--max-filesize",
        "50M",
        "--output",
        f"'{base_file_loc}.%(ext)s'",
        video_url,
    ]
    if simulate:
        args.append("--simulate")

    success = False
    for i in range(ATTEMPTS):
        shell = f"yt-dlp {' '.join(args)}"
        logging.info(shell)
        r = await asyncio.create_subprocess_shell(shell)
        await r.wait()
        if r.returncode == 0:
            success = True
            break

    if not success:
        return ''
    

    matching_files = [
        f for f in os.listdir(CACHE_LOC)
        if f.startswith(base_filename)
    ]

    if expected_filename not in matching_files:
        return ''
    
    return CACHE_LOC + expected_filename
    

    